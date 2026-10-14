"""Canvases: HTML, SVG, Markdown or text frames an agent (or a client) publishes for display.

Gateway handler: ``crates/zeroclaw-gateway/src/canvas.rs``. Limits: 100
canvases, 50 frames of history each, 256 KiB per frame (the gateway's
64 KiB request limit applies first).
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client
    from .chat import Feed

__all__ = ["CanvasAPI", "CanvasFrame"]


class CanvasFrame(Model):
    """A canvas frame."""

    #: The frame id.
    frame_id: str
    #: ``html``, ``svg``, ``markdown`` or ``text``.
    content_type: str
    #: The content.
    content: str
    #: When it was published.
    timestamp: str


class CanvasAPI:
    """The canvas endpoints (``/api/canvas``), from :attr:`Client.canvas`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def list(self) -> builtins.list[str]:
        """Return the canvas ids (GET /api/canvas)."""
        return await self._c._field("GET", ["api", "canvas"], "canvases", list[str])

    async def current(self, id: str) -> CanvasFrame:
        """Return the current frame (GET /api/canvas/{id})."""
        return await self._c._field("GET", ["api", "canvas", id], "frame", CanvasFrame)

    async def publish(self, id: str, content_type: str, content: str) -> CanvasFrame:
        """Publish a frame, creating the canvas (POST /api/canvas/{id}).

        ``content_type`` is ``html``, ``svg``, ``markdown`` or ``text``.
        """
        return await self._c._field(
            "POST",
            ["api", "canvas", id],
            "frame",
            CanvasFrame,
            json_body={"content_type": content_type, "content": content},
        )

    async def history(self, id: str) -> builtins.list[CanvasFrame]:
        """Return past frames, oldest first (GET /api/canvas/{id}/history)."""
        return await self._c._field(
            "GET", ["api", "canvas", id, "history"], "frames", list[CanvasFrame]
        )

    async def watch(self, id: str) -> Feed:
        """Follow a canvas live (GET /ws/canvas/{id}).

        Frames are ``{"type": "connected" | "frame" | "lagged" | "error", …}``;
        a ``frame`` carries the published frame.
        """
        return await self._c._feed("ws", "canvas", id)

    async def clear(self, id: str) -> None:
        """Clear a canvas (DELETE /api/canvas/{id})."""
        await self._c._request("DELETE", ["api", "canvas", id])
