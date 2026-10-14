"""Talking to an agent over the gateway's chat WebSocket (``/ws/chat``), and live feeds.

Gateway handler: ``crates/zeroclaw-gateway/src/ws.rs``. A connection is one
session (``gw_<session_id>`` in :attr:`Client.sessions`); reconnecting with
the same session id resumes it. Each message starts a turn that streams
frames (text chunks, tool calls, approval requests, …) and ends with
``done``, ``aborted`` or ``error``. A message sent during a turn steers it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from types import TracebackType
from typing import TYPE_CHECKING, Any, Final, Self
from urllib.parse import urlencode

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidStatus
from websockets.typing import Subprotocol

from ._errors import APIError, DecodeError, RequestTimeoutError, TurnError, WebSocketError
from ._model import Model, decode
from ._version import __version__

if TYPE_CHECKING:
    from ._client import Client

__all__ = [
    "FRAME_ABORTED",
    "FRAME_APPROVAL_REQUEST",
    "FRAME_CHUNK",
    "FRAME_CONNECTED",
    "FRAME_DONE",
    "FRAME_ERROR",
    "FRAME_SESSION_START",
    "FRAME_THINKING",
    "FRAME_TOOL_CALL",
    "FRAME_TOOL_RESULT",
    "ChatFrame",
    "ChatSession",
    "Feed",
    "TurnResult",
]

#: The WebSocket subprotocol ZeroClaw's chat speaks.
SUBPROTOCOL: Final = Subprotocol("zeroclaw.v1")

#: Bounds one WebSocket message (a long reply arrives in one done frame).
MAX_FRAME: Final = 64 << 20

# Chat frame types. Frames of any other type ("plan", "history_trimmed",
# "cron_result", session events, …) keep their type and only ``raw`` is set.
FRAME_SESSION_START: Final = "session_start"  #: the session is open
FRAME_CONNECTED: Final = "connected"  #: answer to a "connect" frame
FRAME_CHUNK: Final = "chunk"  #: a piece of the reply, in ``content``
FRAME_THINKING: Final = "thinking"  #: a piece of the model's reasoning, in ``content``
FRAME_TOOL_CALL: Final = "tool_call"  #: the agent calls a tool
FRAME_TOOL_RESULT: Final = "tool_result"  #: a tool's result
FRAME_APPROVAL_REQUEST: Final = "approval_request"  #: the agent needs approval to run a tool
FRAME_DONE: Final = "done"  #: the turn ended; see ``done``
FRAME_ABORTED: Final = "aborted"  #: the turn was cancelled
FRAME_ERROR: Final = "error"  #: the turn (or the session) failed


class TurnResult(Model):
    """The end of a turn."""

    #: The whole reply.
    full_response: str = ""
    #: Input tokens used.
    input_tokens: int | None = None
    #: Output tokens used.
    output_tokens: int | None = None
    #: Tokens used in all.
    tokens_used: int | None = None
    #: Cost of the turn, in USD.
    cost_usd: float | None = None
    #: The model used.
    model: str = ""
    #: The provider used.
    provider: str = ""
    #: The model's context size.
    max_context_tokens: int | None = None
    #: The input tokens of the last model call.
    last_input_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class ChatFrame:
    """A frame the gateway sends on the chat. ``type`` says which fields are set."""

    #: The frame type, one of the ``FRAME_*`` constants or another.
    type: str
    #: Content of a chunk or thinking frame.
    content: str = ""
    #: Session id of a session_start frame.
    session_id: str = ""
    #: Whether the session existed (session_start).
    resumed: bool = False
    #: Messages the session holds (session_start).
    message_count: int = 0
    #: Name of the session (session_start) or of the tool (tool_call, tool_result).
    name: str = ""
    #: Id of a tool_call or tool_result.
    id: str = ""
    #: Arguments of a tool_call.
    args: Any = None
    #: Output of a tool_result.
    output: Any = None
    #: Request id of an approval_request; answer it with :meth:`ChatSession.answer_approval`.
    request_id: str = ""
    #: Tool of an approval_request.
    tool: str = ""
    #: What the tool would do (approval_request).
    arguments_summary: str = ""
    #: Seconds before the approval_request is denied.
    timeout_secs: int = 0
    #: The end of the turn, for a done frame.
    done: TurnResult | None = None
    #: Message of an error frame.
    message: str = ""
    #: Code of an error frame (``PROVIDER_ERROR``, ``SESSION_QUEUE_FULL``, …).
    code: str = ""
    #: The frame as sent.
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def parse(cls, data: str | bytes) -> ChatFrame:
        """Parse a frame; :class:`DecodeError` when it is not a JSON object."""
        try:
            raw = json.loads(data)
        except ValueError as exc:
            raise DecodeError(f"chat frame is not JSON: {exc}") from exc
        if not isinstance(raw, dict):
            raise DecodeError("chat frame is not a JSON object")
        kind = _str(raw, "type")
        if kind == FRAME_SESSION_START:
            return cls(
                kind,
                session_id=_str(raw, "session_id"),
                resumed=raw.get("resumed") is True,
                message_count=_int(raw, "message_count"),
                name=_str(raw, "name"),
                raw=raw,
            )
        if kind in (FRAME_CHUNK, FRAME_THINKING):
            return cls(kind, content=_str(raw, "content"), raw=raw)
        if kind == FRAME_TOOL_CALL:
            return cls(
                kind, id=_str(raw, "id"), name=_str(raw, "name"), args=raw.get("args"), raw=raw
            )
        if kind == FRAME_TOOL_RESULT:
            return cls(
                kind, id=_str(raw, "id"), name=_str(raw, "name"), output=raw.get("output"), raw=raw
            )
        if kind == FRAME_APPROVAL_REQUEST:
            return cls(
                kind,
                request_id=_str(raw, "request_id"),
                tool=_str(raw, "tool"),
                arguments_summary=_str(raw, "arguments_summary"),
                timeout_secs=_int(raw, "timeout_secs"),
                raw=raw,
            )
        if kind == FRAME_DONE:
            return cls(kind, done=decode(raw, TurnResult), raw=raw)
        if kind == FRAME_ERROR:
            message = _str(raw, "message") or _str(raw, "error") or "unknown error"
            return cls(kind, message=message, code=_str(raw, "code"), raw=raw)
        return cls(kind, raw=raw)


def _str(raw: Mapping[str, Any], key: str) -> str:
    value = raw.get(key)
    return value if isinstance(value, str) else ""


def _int(raw: Mapping[str, Any], key: str) -> int:
    value = raw.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


class _Socket:
    """An open WebSocket that reads text messages."""

    def __init__(self, conn: ClientConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def _read(self) -> str | None:
        """Return the next text message, skipping others, or ``None`` once the socket closed."""
        while True:
            try:
                message = await self._conn.recv()
            except ConnectionClosed:
                return None
            except Exception as exc:
                raise WebSocketError(f"websocket error: {exc}") from exc
            if isinstance(message, str):
                return message

    async def _write(self, frame: Mapping[str, Any]) -> None:
        try:
            await self._conn.send(json.dumps(frame))
        except ConnectionClosed as exc:
            raise WebSocketError(f"websocket error: {exc}") from exc

    async def aclose(self) -> None:
        """Close the connection."""
        await self._conn.close()


class ChatSession(_Socket):
    """An open chat with an agent, from :meth:`Client.chat`.

    Frames are read by one task at a time; iterate it with ``async for``
    (it ends once the socket closed). Closing during a turn cancels it.
    """

    def __init__(self, conn: ClientConnection, start: ChatFrame) -> None:
        super().__init__(conn)
        #: The session id (its key is ``gw_<id>``).
        self.session_id = start.session_id
        #: Whether an existing session was resumed.
        self.resumed = start.resumed
        #: The number of messages the session held when it was opened.
        self.message_count = start.message_count

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> ChatFrame:
        frame = await self.next_frame()
        if frame is None:
            raise StopAsyncIteration
        return frame

    async def send(self, content: str) -> None:
        """Send a message: it starts a turn, or steers the running one."""
        await self._write({"type": "message", "content": content})

    async def answer_approval(self, request_id: str, decision: str) -> None:
        """Answer an approval_request with ``approve``, ``deny`` or ``always``."""
        await self._write(
            {"type": "approval_response", "request_id": request_id, "decision": decision}
        )

    async def next_frame(self) -> ChatFrame | None:
        """Return the next frame from the gateway, or ``None`` once the socket closed."""
        data = await self._read()
        return None if data is None else ChatFrame.parse(data)

    async def ask(self, content: str) -> TurnResult:
        """Send ``content`` and wait for the turn to end, ignoring the frames in between.

        An error frame raises :class:`TurnError`; an aborted turn too, with
        code ``ABORTED``. Tool approvals are not answered here: iterate the
        session for agents that ask for them.
        """
        await self.send(content)
        while True:
            frame = await self.next_frame()
            if frame is None:
                raise WebSocketError("the gateway closed the chat before the turn ended")
            if frame.type == FRAME_DONE:
                assert frame.done is not None
                return frame.done
            if frame.type == FRAME_ERROR:
                raise TurnError(frame.code, frame.message)
            if frame.type == FRAME_ABORTED:
                raise TurnError("ABORTED", "the turn was aborted")


class Feed(_Socket):
    """A live WebSocket feed of JSON frames the gateway pushes (canvas, SOP runs).

    Iterate it with ``async for``; it ends once the gateway closed the feed.
    A frame that is not JSON raises :class:`DecodeError` from :meth:`next`;
    the feed goes on after it.
    """

    def __aiter__(self) -> Self:
        return self

    async def __anext__(self) -> Any:
        data = await self._read()
        if data is None:
            raise StopAsyncIteration
        return _json(data)

    async def next(self) -> Any:
        """Return the next frame, or ``None`` once the gateway closed the feed."""
        data = await self._read()
        return None if data is None else _json(data)


def _json(data: str) -> Any:
    try:
        return json.loads(data)
    except ValueError as exc:
        raise DecodeError(f"frame is not JSON: {exc}") from exc


async def open_socket(
    client: Client, segments: Sequence[str], query: Mapping[str, str | None] | None = None
) -> ClientConnection:
    """Open a WebSocket to ``segments`` on the gateway (ws for http, wss for https).

    Offers ZeroClaw's subprotocol and the bearer token. The client's timeout
    bounds the handshake. A refusal over HTTP (401 without a valid token, 400
    for an unknown agent) is an :class:`APIError`.
    """
    base = "ws" + client.base_url.removeprefix("http")
    url = client._url(segments, base)
    params = {k: v for k, v in (query or {}).items() if v}
    if params:
        url += "?" + urlencode(params)
    try:
        return await connect(
            url,
            subprotocols=[SUBPROTOCOL],
            additional_headers=client._headers(),
            user_agent_header=f"zeroclaw-api-client-python/{__version__}",
            compression=None,
            max_size=MAX_FRAME,
            open_timeout=client.timeout,
        )
    except InvalidStatus as exc:
        raise APIError.from_response(
            exc.response.status_code, bytes(exc.response.body or b"")
        ) from exc
    except TimeoutError as exc:
        raise RequestTimeoutError() from exc
    except (InvalidHandshake, OSError) as exc:
        raise WebSocketError(f"websocket error: {exc}") from exc


async def open_chat(
    client: Client, alias: str, session_id: str | None, name: str | None, cwd: str | None
) -> ChatSession:
    """Open a chat and wait for the gateway to confirm the session."""
    conn = await open_socket(
        client,
        ["ws", "chat"],
        {"agent": alias, "session_id": session_id, "name": name, "cwd": cwd},
    )
    try:
        socket = _Socket(conn)
        data = await socket._read()
        if data is None:
            raise WebSocketError("the gateway closed the chat before the session started")
        frame = ChatFrame.parse(data)
        if frame.type == FRAME_SESSION_START:
            return ChatSession(conn, frame)
        if frame.type == FRAME_ERROR:
            raise TurnError(frame.code, frame.message)
        raise WebSocketError(f"expected session_start, got {data}")
    except BaseException:
        await conn.close()
        raise
