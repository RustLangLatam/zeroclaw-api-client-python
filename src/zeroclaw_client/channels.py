"""Channels (WhatsApp, Telegram, …): their state, identities and logins.

Gateway handlers: ``crates/zeroclaw-gateway/src/api.rs`` and ``api_config.rs``
(bind). A channel is named ``type.alias``, as :meth:`ChannelsAPI.list`
returns it.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = [
    "Bound",
    "Channel",
    "ChannelsAPI",
    "Relinked",
]


class Channel(Model):
    """A configured channel."""

    #: ``type.alias``, the name the other calls take.
    name: str
    #: The channel type (``whatsapp``, ``telegram``, …).
    type: str
    #: The alias.
    alias: str
    #: The agent it belongs to.
    owning_agent: str | None = None
    #: Whether it is enabled.
    enabled: bool
    #: Whether this build includes its type.
    compiled: bool
    #: ``active``, ``inactive``, ``error``, ``unknown`` or ``not_compiled``.
    status: str
    #: ``healthy``, ``degraded``, ``down`` or ``unavailable``.
    health: str
    #: What it still needs (``enabled``, ``bound_to_agent``, ``authenticated``,
    #: ``listening``, each ``ready``/``missing``/``unknown``, plus notes).
    readiness: Any = None
    #: The number of messages the channel has carried.
    message_count: int
    #: When the last one went through (RFC 3339).
    last_message_at: str | None = None


class Bound(Model):
    """The result of :meth:`ChannelsAPI.bind`."""

    #: Whether the configuration was saved.
    saved: bool
    #: Whether the identity was already allowed.
    already_bound: bool
    #: The peer group it was added to.
    group: str
    #: The channel.
    channel: str


class Relinked(Model):
    """The result of :meth:`ChannelsAPI.relink`."""

    #: The channel.
    channel: str
    #: ``cleared`` or ``nothing_to_clear``.
    outcome: str
    #: The files removed.
    removed: list[str] | None = None
    #: Whether a reload is needed for the channel to pair again.
    restart_required: bool = False
    #: The gateway's note.
    note: str | None = None


class ChannelsAPI:
    """The channel endpoints (``/api/channels``), from :attr:`Client.channels`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def list(self) -> builtins.list[Channel]:
        """Return every configured channel and its state (GET /api/channels)."""
        return await self._c._field("GET", ["api", "channels"], "channels", list[Channel])

    async def bind(self, channel_type: str, alias: str, identity: str) -> Bound:
        """Let ``identity`` talk to the channel (Telegram, WeChat and LINE).

        Adds it to the channel's peer group (POST /api/channels/bind).
        """
        body = {"channel_type": channel_type, "alias": alias, "identity": identity}
        return await self._c._call("POST", ["api", "channels", "bind"], Bound, json_body=body)

    async def relink(self, channel: str) -> Relinked:
        """Clear a QR-paired channel's saved login so it pairs again after a reload.

        POST /api/channels/{channel}/relink.
        """
        return await self._c._call("POST", ["api", "channels", channel, "relink"], Relinked)
