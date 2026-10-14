from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from zeroclaw_client import Client, DecodeError, Event
from zeroclaw_client.events import EventStream

from .conftest import Gateway


async def chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


def stream(*parts: bytes) -> EventStream:
    return EventStream(httpx.Response(200, content=chunks(*parts)))


async def read_all(s: EventStream) -> list[Any]:
    out: list[Any] = []
    while True:
        try:
            event = await s.next()
        except DecodeError:
            out.append("decode error")
            continue
        if event is None:
            return out
        out.append(dict(event))


@pytest.mark.parametrize(
    ("wire", "want"),
    [
        (b'data: {"type":"agent_end"}\n\n', [{"type": "agent_end"}]),
        (b'data:{"a":1}\n\n', [{"a": 1}]),
        (b'data: {"a":1}\r\n\r\n', [{"a": 1}]),
        (b': keep-alive\n\ndata: {"a":1}\n\n', [{"a": 1}]),
        (b'event: x\nid: 1\nretry: 5\ndata: {"a":1}\n\n', [{"a": 1}]),
        (b"retry: 5\n\n", []),
        (b'data: {"a":1}\n\ndata: {"b":2}\n\n', [{"a": 1}, {"b": 2}]),
        (b'data: not json\n\ndata: {"b":2}\n\n', ["decode error", {"b": 2}]),
        (b"data: [1]\n\n", ["decode error"]),
        (b"", []),
    ],
)
async def test_sse_vectors(wire: bytes, want: list[Any]) -> None:
    assert await read_all(stream(wire)) == want


async def test_multi_line_data_is_joined() -> None:
    assert await read_all(stream(b'data: {"a":\ndata: 1}\n\n')) == [{"a": 1}]


async def test_frames_split_across_chunks_become_events() -> None:
    got = await read_all(stream(b"da", b'ta: {"a"', b":1}\n", b"\n", b'data: {"b":2}\n\n'))
    assert got == [{"a": 1}, {"b": 2}]


async def test_a_last_frame_without_its_blank_line_still_counts() -> None:
    assert await read_all(stream(b'data: {"a":1}\n')) == [{"a": 1}]


def test_events_tell_their_kind() -> None:
    assert Event({"type": "cron_result"}).kind == "cron_result"
    assert Event({"type": 3}).kind == ""
    log = Event({"@timestamp": "t", "event": "x"})
    assert log.is_log
    assert log.kind == ""
    assert not Event({"type": "x"}).is_log


async def test_events_stream_and_replay(gateway: Gateway, client: Client) -> None:
    def live(request: httpx.Request) -> httpx.Response:
        assert request.headers["Accept"] == "text/event-stream"
        return httpx.Response(
            200,
            content=chunks(b'data: {"type":"agent_start"}\n\n', b'data: {"type":"agent_end"}\n\n'),
            headers={"Content-Type": "text/event-stream"},
        )

    gateway.on("GET", "/api/events", live)
    gateway.on(
        "GET",
        "/api/events/history",
        {"events": [{"type": "llm_request"}, {"@timestamp": "t", "event": "boot"}]},
    )
    async with await client.events.subscribe() as s:
        assert [e.kind async for e in s] == ["agent_start", "agent_end"]
    history = await client.events.history()
    assert [e.kind for e in history] == ["llm_request", ""]
    assert history[1].is_log
