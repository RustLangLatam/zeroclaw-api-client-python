"""Channels (WhatsApp, Telegram, …): their state, sending through them, group chats and members.

Gateway handlers: ``crates/zeroclaw-gateway/src/api.rs`` and ``api_config.rs``
(bind). A channel is named ``type.alias``, as :meth:`ChannelsAPI.list`
returns it. Sending and managing rooms need pairing on and the channel listed
in ``[gateway] send_channels``; reading rooms needs pairing only. Errors on
these routes carry the channel: ``{"channel": …, "error": …}``.
"""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = [
    "Bound",
    "Channel",
    "ChannelsAPI",
    "CreatedRoom",
    "Participant",
    "Relinked",
    "RoomMember",
    "RoomSummary",
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


class RoomSummary(Model):
    """A group chat."""

    #: The id in the channel's addressing (``…@g.us`` on WhatsApp).
    id: str
    #: The name (the WhatsApp group subject).
    name: str
    #: The member count.
    participants: int


class RoomMember(Model):
    """A member of a group chat."""

    #: The member: ``+<digits>`` on WhatsApp when the number is known.
    id: str
    #: Whether they administer the group.
    admin: bool


class Participant(Model):
    """What happened to someone added to a group chat."""

    #: Who.
    user: str
    #: ``added``, ``invited``, ``refused`` or ``failed``.
    outcome: str
    #: Why, when it did not work.
    detail: str | None = None


class CreatedRoom(Model):
    """The result of :meth:`ChannelsAPI.create_room`."""

    #: The channel.
    channel: str
    #: The new room's id.
    room: str
    #: Always ``created``.
    outcome: str
    #: What happened to each invitee.
    participants: list[Participant] | None = None


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

    async def send(self, channel: str, to: str, content: str, thread_id: str | None = None) -> None:
        """Send plain text to ``to``, with no agent turn (POST /api/channels/{channel}/send).

        Without ``thread_id`` it is sent outside a thread.
        """
        body = {"to": to, "content": content, "thread_id": thread_id or None}
        await self._c._request("POST", ["api", "channels", channel, "send"], json_body=body)

    async def rooms(self, channel: str) -> builtins.list[RoomSummary]:
        """Return the group chats the running channel takes part in.

        GET /api/channels/{channel}/rooms.
        """
        return await self._c._field(
            "GET", ["api", "channels", channel, "rooms"], "rooms", list[RoomSummary]
        )

    async def create_room(
        self,
        channel: str,
        name: str,
        topic: str | None = None,
        invites: Sequence[str] = (),
    ) -> CreatedRoom:
        """Create a group chat and invite ``invites`` (POST /api/channels/{channel}/rooms).

        Invitees are phone numbers on WhatsApp, which are also allowed to
        talk to the channel. Without ``topic`` none is set.
        """
        body = {"name": name, "topic": topic or None, "invites": builtins.list(invites)}
        return await self._c._call(
            "POST", ["api", "channels", channel, "rooms"], CreatedRoom, json_body=body
        )

    async def room_members(self, channel: str, room: str) -> builtins.list[RoomMember]:
        """Return a group chat's members (GET /api/channels/{channel}/rooms/{room}/members)."""
        return await self._c._field(
            "GET",
            ["api", "channels", channel, "rooms", room, "members"],
            "members",
            list[RoomMember],
        )

    async def invite(self, channel: str, room: str, user: str) -> Participant:
        """Add or invite ``user`` to a group chat.

        POST /api/channels/{channel}/rooms/{room}/invites.
        """
        return await self._c._call(
            "POST",
            ["api", "channels", channel, "rooms", room, "invites"],
            Participant,
            json_body={"user": user},
        )

    async def remove_member(self, channel: str, room: str, user: str) -> None:
        """Remove a member from a group chat.

        DELETE /api/channels/{channel}/rooms/{room}/members/{user}.
        """
        await self._c._request(
            "DELETE", ["api", "channels", channel, "rooms", room, "members", user]
        )
