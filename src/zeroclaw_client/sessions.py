"""Conversation sessions: listing, transcripts, state, renaming, aborting and adding messages.

Gateway handlers: ``crates/zeroclaw-gateway/src/api.rs`` (``/api/sessions*``).
A session id is either the display id or the full session key (``gw_…``,
``whatsapp_…``); the gateway resolves both.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["Session", "SessionMessage", "SessionState", "SessionsAPI"]


class Session(Model):
    """A stored session."""

    #: The display id (``gw_`` removed).
    session_id: str
    #: The full key (``gw_…``, ``whatsapp_<channel>_<peer>…``).
    session_key: str | None = None
    #: The creation time (RFC 3339).
    created_at: str
    #: The last activity (RFC 3339).
    last_activity: str
    #: The number of messages in it.
    message_count: int
    #: The agent that answers it.
    agent_alias: str | None = None
    #: The channel it came through (``whatsapp.alias``).
    channel_id: str | None = None
    #: The name given to it.
    name: str | None = None


class SessionMessage(Model):
    """A message of a transcript."""

    #: ``user``, ``assistant``, ``tool``, …
    role: str
    #: The content (tool calls and results are JSON text).
    content: str
    #: When it was stored.
    created_at: str | None = None


class SessionState(Model):
    """Whether a session is busy."""

    #: The session id as asked.
    session_id: str
    #: ``idle``, ``running`` or ``error``.
    state: str
    #: The running turn.
    turn_id: str | None = None
    #: When it started.
    turn_started_at: str | None = None


class SessionsAPI:
    """The session endpoints (``/api/sessions``), from :attr:`Client.sessions`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def list(self) -> builtins.list[Session]:
        """Return every stored session, empty when the gateway keeps none (GET /api/sessions)."""
        return await self._c._field("GET", ["api", "sessions"], "sessions", list[Session])

    async def running(self) -> builtins.list[Session]:
        """Return the gateway (web chat) sessions (GET /api/sessions/running)."""
        return await self._c._field(
            "GET", ["api", "sessions", "running"], "sessions", list[Session]
        )

    async def messages(self, id: str) -> builtins.list[SessionMessage]:
        """Return the transcript, empty for an unknown session (GET /api/sessions/{id}/messages)."""
        return await self._c._field(
            "GET", ["api", "sessions", id, "messages"], "messages", list[SessionMessage]
        )

    async def add_message(self, id: str, content: str) -> None:
        """Append an assistant message to the session, shown to chat clients.

        No agent turn runs (POST /api/sessions/{id}/messages).
        """
        await self._c._request(
            "POST", ["api", "sessions", id, "messages"], json_body={"content": content}
        )

    async def state(self, id: str) -> SessionState:
        """Report whether a turn is running (GET /api/sessions/{id}/state)."""
        return await self._c._call("GET", ["api", "sessions", id, "state"], SessionState)

    async def rename(self, id: str, name: str) -> None:
        """Rename a session (PUT /api/sessions/{id})."""
        await self._c._request("PUT", ["api", "sessions", id], json_body={"name": name})

    async def delete(self, id: str) -> None:
        """Cancel its running turn and delete it (DELETE /api/sessions/{id})."""
        await self._c._request("DELETE", ["api", "sessions", id])

    async def abort(self, id: str) -> bool:
        """Cancel the running turn and report whether there was one.

        POST /api/sessions/{id}/abort.
        """
        status = await self._c._field("POST", ["api", "sessions", id, "abort"], "status", str)
        return status == "aborted"
