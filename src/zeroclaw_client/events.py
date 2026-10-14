"""The gateway's live event stream (Server-Sent Events) and its recent history.

Gateway handler: ``crates/zeroclaw-gateway/src/sse.rs``. Every frame is
``data: <one JSON object>`` with no event name, so frames are told apart by
their content: observer events and cron results carry a ``type``
(``llm_request``, ``tool_call``, ``tool_call_start``, ``agent_start``,
``agent_end``, ``error``, ``history_trimmed``, ``cron_result``, …);
structured log events carry ``@timestamp`` instead. Frames missed while
lagging are not replayed.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

import httpx

from ._errors import DecodeError, TransportError

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["Event", "EventStream", "EventsAPI"]


class Event(dict[str, Any]):
    """One event, as the gateway sent it: its top-level fields."""

    @property
    def kind(self) -> str:
        """The event's ``type`` (``agent_end``, ``cron_result``, …); empty for log events."""
        value = self.get("type")
        return value if isinstance(value, str) else ""

    @property
    def is_log(self) -> bool:
        """Whether it is a structured log event (``@timestamp``, ``event``, ``service``, …)."""
        return "@timestamp" in self


class EventsAPI:
    """The live event stream endpoints (``/api/events``), from :attr:`Client.events`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def subscribe(self) -> EventStream:
        """Open the live stream (GET /api/events).

        The stream ends when the gateway closes the connection (e.g. on
        reload); subscribe again to resume. The client's timeout bounds only
        the wait for the stream to open, never the stream itself. Close the
        stream when done, or use it as an async context manager.
        """
        request = self._c._build("GET", ["api", "events"], headers={"Accept": "text/event-stream"})
        return EventStream(await self._c._send(request, stream=True))

    async def history(self) -> list[Event]:
        """Return the latest observer events, oldest first (GET /api/events/history).

        Up to 500, kept in memory by the gateway.
        """
        events = await self._c._field(
            "GET", ["api", "events", "history"], "events", list[dict[str, Any]]
        )
        return [Event(e) for e in events]


class EventStream:
    """The live stream of :meth:`EventsAPI.subscribe`.

    Iterate it with ``async for``; it ends once the gateway closed the
    stream. A frame that is not JSON raises :class:`DecodeError` from
    :meth:`next`; the stream goes on after it. Any other error ends the
    stream.
    """

    def __init__(self, response: httpx.Response) -> None:
        self._response = response
        self._lines: AsyncIterator[str] = response.aiter_lines()
        self._done = False

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Event:
        event = await self.next()
        if event is None:
            raise StopAsyncIteration
        return event

    async def next(self) -> Event | None:
        """Return the next event, or ``None`` once the gateway closed the stream."""
        data: list[str] = []
        while not self._done:
            # "data:" lines are joined until a blank line ends the frame;
            # comments (keep-alives) and other fields are skipped.
            try:
                line: str | None = await anext(self._lines)
            except StopAsyncIteration:
                # A last frame without its blank line still counts.
                self._done, line = True, ""
            except httpx.HTTPError as exc:
                self._done = True
                raise TransportError(
                    f"request to the gateway failed: reading the event stream: {exc}"
                ) from exc
            assert line is not None
            if line.startswith("data:"):
                value = line[5:]
                data.append(value[1:] if value.startswith(" ") else value)
                continue
            if line or not data:
                continue
            try:
                event = json.loads("\n".join(data))
            except ValueError as exc:
                raise DecodeError(f"event is not JSON: {exc}") from exc
            if not isinstance(event, dict):
                raise DecodeError("event is not a JSON object")
            return Event(event)
        return None

    async def aclose(self) -> None:
        """Close the stream."""
        self._done = True
        await self._response.aclose()
