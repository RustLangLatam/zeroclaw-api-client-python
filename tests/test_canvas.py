from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from zeroclaw_client import Client
from zeroclaw_client.canvas import CanvasAPI

from .conftest import Gateway, body, reply

FRAME = {"frame_id": "f1", "content_type": "markdown", "content": "# Hi", "timestamp": "t"}


async def test_publishes_frames(gateway: Gateway, client: Client) -> None:
    def publish(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"content_type": "markdown", "content": "# Hi"}
        return reply({"canvas_id": "board", "frame": FRAME}, 201)(request)

    gateway.on("GET", "/api/canvas", {"canvases": ["board"]})
    gateway.on("POST", "/api/canvas/board", publish)
    gateway.on("GET", "/api/canvas/board", {"canvas_id": "board", "frame": FRAME})
    gateway.on("GET", "/api/canvas/board/history", {"canvas_id": "board", "frames": [FRAME]})
    gateway.on("DELETE", "/api/canvas/board", {"canvas_id": "board", "status": "cleared"})

    canvas = CanvasAPI(client)
    assert await canvas.list() == ["board"]
    assert (await canvas.publish("board", "markdown", "# Hi")).frame_id == "f1"
    assert (await canvas.current("board")).content == "# Hi"
    assert len(await canvas.history("board")) == 1
    await canvas.clear("board")


async def test_watch_opens_the_canvas_feed(client: Client, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Sequence[str]] = []

    async def open_socket(_: Client, segments: Sequence[str], query: Any = None) -> object:
        opened.append(segments)
        return object()

    monkeypatch.setattr("zeroclaw_client._client.open_socket", open_socket)
    await CanvasAPI(client).watch("my board")
    assert list(opened[0]) == ["ws", "canvas", "my board"]
