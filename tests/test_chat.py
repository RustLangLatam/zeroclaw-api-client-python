from __future__ import annotations

import dataclasses
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

import pytest
from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from zeroclaw_client import APIError, ChatFrame, Client, DecodeError, TurnError, WebSocketError
from zeroclaw_client.chat import FRAME_DONE, FRAME_SESSION_START, SUBPROTOCOL, TurnResult

from .conftest import TOKEN

Session = Callable[[ServerConnection], Awaitable[None]]


@asynccontextmanager
async def chat_gateway(session: Session) -> AsyncIterator[tuple[Client, list[Request]]]:
    """A WebSocket gateway that refuses requests without the token and runs ``session``."""
    seen: list[Request] = []

    def check(conn: ServerConnection, request: Request) -> Response | None:
        seen.append(request)
        if request.headers.get("Authorization") != f"Bearer {TOKEN}":
            body = b'{"error":"unauthorized"}'
            return Response(401, "Unauthorized", Headers({"Content-Length": str(len(body))}), body)
        return None

    async with serve(
        session, "127.0.0.1", 0, process_request=check, subprotocols=[SUBPROTOCOL]
    ) as server:
        port = server.sockets[0].getsockname()[1]
        async with Client(f"http://127.0.0.1:{port}", token=TOKEN, timeout=5) as client:
            yield client, seen


def start(session_id: str = "s1", resumed: bool = False, count: int = 0) -> str:
    return json.dumps(
        {
            "type": "session_start",
            "session_id": session_id,
            "resumed": resumed,
            "message_count": count,
            "name": "work",
        }
    )


DONE = json.dumps(
    {
        "type": "done",
        "full_response": "Hello!",
        "input_tokens": 10,
        "output_tokens": 2,
        "model": "m",
        "provider": "p",
    }
)


async def test_a_question_gets_the_turns_reply() -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send(start("s1", True, 4))
        message = json.loads(await ws.recv())
        assert message == {"type": "message", "content": "hi"}
        await ws.send(json.dumps({"type": "chunk", "content": "Hel"}))
        await ws.send(b"binary frames are skipped")
        await ws.send(DONE)

    async with (
        chat_gateway(session) as (client, seen),
        await client.chat("helper", session_id="s1", name="work") as chat,
    ):
        assert (chat.session_id, chat.resumed, chat.message_count) == ("s1", True, 4)
        result = await chat.ask("hi")
    assert result.full_response == "Hello!"
    assert result.input_tokens == 10
    request = seen[0]
    assert request.path == "/ws/chat?agent=helper&session_id=s1&name=work"
    assert request.headers["Sec-WebSocket-Protocol"] == "zeroclaw.v1"
    assert request.headers["User-Agent"].startswith("zeroclaw-api-client-python/")


async def test_frames_can_be_read_one_by_one() -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send(start())
        await ws.recv()
        await ws.send(
            json.dumps(
                {
                    "type": "approval_request",
                    "request_id": "r1",
                    "tool": "shell",
                    "arguments_summary": "ls",
                    "timeout_secs": 30,
                }
            )
        )
        answer = json.loads(await ws.recv())
        assert answer == {"type": "approval_response", "request_id": "r1", "decision": "approve"}
        await ws.send(DONE)

    async with chat_gateway(session) as (client, _), await client.chat("helper") as chat:
        await chat.send("list files")
        kinds = []
        async for frame in chat:
            kinds.append(frame.type)
            if frame.type == "approval_request":
                assert frame.timeout_secs == 30
                await chat.answer_approval(frame.request_id, "approve")
        assert kinds == ["approval_request", "done"]


@pytest.mark.parametrize(
    ("frame", "code", "message"),
    [
        ({"type": "error", "code": "PROVIDER_ERROR", "message": "boom"}, "PROVIDER_ERROR", "boom"),
        ({"type": "error", "error": "legacy"}, "", "legacy"),
        ({"type": "aborted"}, "ABORTED", "the turn was aborted"),
    ],
)
async def test_a_failed_turn_is_an_error_with_its_code(
    frame: dict[str, Any], code: str, message: str
) -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send(start())
        await ws.recv()
        await ws.send(json.dumps(frame))

    async with chat_gateway(session) as (client, _), await client.chat("helper") as chat:
        with pytest.raises(TurnError) as err:
            await chat.ask("hi")
    assert (err.value.code, err.value.message) == (code, message)


async def test_a_turn_cut_by_a_close_is_a_websocket_error() -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send(start())
        await ws.recv()

    async with chat_gateway(session) as (client, _), await client.chat("helper") as chat:
        with pytest.raises(WebSocketError):
            await chat.ask("hi")


async def test_a_session_refused_before_it_starts_is_a_turn_error() -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send(json.dumps({"type": "error", "code": "SESSION_LIMIT", "message": "full"}))

    async with chat_gateway(session) as (client, _):
        with pytest.raises(TurnError) as err:
            await client.chat("helper")
    assert err.value.code == "SESSION_LIMIT"


async def test_a_refused_handshake_keeps_its_status() -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send(start())

    async with chat_gateway(session) as (client, _):
        with pytest.raises(APIError) as err:
            await client.with_token("zc_wrong").chat("helper")
    assert err.value.status == 401
    assert err.value.message == "unauthorized"


async def test_feeds_stream_their_frames() -> None:
    async def session(ws: ServerConnection) -> None:
        await ws.send('{"n":1}')
        await ws.send("not json")
        await ws.send('{"n":2}')

    async with chat_gateway(session) as (client, seen):
        feed = await client._feed("ws", "canvas", "c/1")
        async with feed:
            assert await feed.next() == {"n": 1}
            with pytest.raises(DecodeError):
                await feed.next()
            assert [f async for f in feed] == [{"n": 2}]
        assert seen[0].path == "/ws/canvas/c%2F1"


@pytest.mark.parametrize(
    ("wire", "want"),
    [
        ({"type": "chunk", "content": "a"}, ChatFrame("chunk", content="a")),
        ({"type": "thinking", "content": "b"}, ChatFrame("thinking", content="b")),
        (
            {"type": "tool_call", "id": "t1", "name": "shell", "args": {"cmd": "ls"}},
            ChatFrame("tool_call", id="t1", name="shell", args={"cmd": "ls"}),
        ),
        (
            {"type": "tool_result", "id": "t1", "name": "shell", "output": "ok"},
            ChatFrame("tool_result", id="t1", name="shell", output="ok"),
        ),
        (
            {"type": "session_start", "session_id": "s", "resumed": True, "message_count": 2},
            ChatFrame(FRAME_SESSION_START, session_id="s", resumed=True, message_count=2),
        ),
        ({"type": "error"}, ChatFrame("error", message="unknown error")),
        ({"type": "plan", "steps": [1]}, ChatFrame("plan")),
        ({"type": "chunk", "content": 5}, ChatFrame("chunk")),
        ({"content": "x"}, ChatFrame("")),
    ],
)
def test_chat_frame_vectors(wire: dict[str, Any], want: ChatFrame) -> None:
    got = ChatFrame.parse(json.dumps(wire))
    assert got == dataclasses.replace(want, raw=wire)


@pytest.mark.parametrize("wire", ["not json", "[1]", '"x"'])
def test_frames_that_are_not_objects_are_decode_errors(wire: str) -> None:
    with pytest.raises(DecodeError):
        ChatFrame.parse(wire)


def test_done_frames_carry_the_turn() -> None:
    frame = ChatFrame.parse(DONE)
    assert frame.type == FRAME_DONE
    assert frame.done == TurnResult(
        full_response="Hello!", input_tokens=10, output_tokens=2, model="m", provider="p"
    )
