from __future__ import annotations

import httpx
import pytest

from zeroclaw_client import APIError, Client, is_unauthorized
from zeroclaw_client.channels import ChannelsAPI

from .conftest import Gateway, body, reply

CHANNEL = "whatsapp.main"
ROOM = "120363000000000000@g.us"


async def test_list_bind_and_relink(gateway: Gateway, client: Client) -> None:
    gateway.on(
        "GET",
        "/api/channels",
        {
            "channels": [
                {
                    "name": "whatsapp.main",
                    "type": "whatsapp",
                    "alias": "main",
                    "owning_agent": "helper",
                    "enabled": True,
                    "compiled": True,
                    "status": "active",
                    "message_count": 0,
                    "last_message_at": None,
                    "health": "healthy",
                    "readiness": {
                        "enabled": "ready",
                        "bound_to_agent": "ready",
                        "authenticated": "ready",
                        "listening": "ready",
                        "requirements": [],
                        "notes": [],
                    },
                }
            ]
        },
    )

    def bind(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"channel_type": "telegram", "alias": "bot", "identity": "42"}
        return reply(
            {
                "saved": True,
                "already_bound": False,
                "group": "telegram_bot",
                "channel": "telegram.bot",
            }
        )(request)

    gateway.on("POST", "/api/channels/bind", bind)
    gateway.on(
        "POST",
        "/api/channels/whatsapp.main/relink",
        {
            "channel": "whatsapp.main",
            "outcome": "cleared",
            "removed": ["/wa/session.db"],
            "restart_required": True,
            "note": "reload",
        },
    )

    channels = ChannelsAPI(client)
    listed = await channels.list()
    assert listed[0].type == "whatsapp"
    assert listed[0].health == "healthy"
    assert listed[0].readiness["enabled"] == "ready"
    assert (await channels.bind("telegram", "bot", "42")).group == "telegram_bot"
    assert (await channels.relink(CHANNEL)).restart_required


async def test_send_and_manage_group_chats(gateway: Gateway, client: Client) -> None:
    def send(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"to": "+34600000000", "content": "Hola", "thread_id": None}
        return reply({"channel": CHANNEL, "to": "+34600000000", "outcome": "sent"})(request)

    def create(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"name": "Team", "topic": None, "invites": ["+34600000000"]}
        return reply(
            {
                "channel": CHANNEL,
                "room": ROOM,
                "outcome": "created",
                "participants": [{"user": "+34600000000", "outcome": "added", "detail": None}],
            }
        )(request)

    def invite(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"user": "+34611111111"}
        return reply(
            {
                "channel": CHANNEL,
                "room": ROOM,
                "user": "+34611111111",
                "outcome": "invited",
                "detail": None,
            }
        )(request)

    base = "/api/channels/whatsapp.main"
    gateway.on("POST", f"{base}/send", send)
    gateway.on(
        "GET",
        f"{base}/rooms",
        {"channel": CHANNEL, "rooms": [{"id": ROOM, "name": "Team", "participants": 3}]},
    )
    gateway.on("POST", f"{base}/rooms", create)
    gateway.on(
        "GET",
        f"{base}/rooms/{ROOM}/members",
        {"channel": CHANNEL, "room": ROOM, "members": [{"id": "+34600000000", "admin": True}]},
    )
    gateway.on("POST", f"{base}/rooms/{ROOM}/invites", invite)
    gateway.on(
        "DELETE",
        f"{base}/rooms/{ROOM}/members/+34611111111",
        {"channel": CHANNEL, "room": ROOM, "user": "+34611111111", "outcome": "removed"},
    )

    channels = ChannelsAPI(client)
    await channels.send(CHANNEL, "+34600000000", "Hola")
    assert (await channels.rooms(CHANNEL))[0].participants == 3
    created = await channels.create_room(CHANNEL, "Team", invites=["+34600000000"])
    assert created.participants is not None
    assert created.participants[0].outcome == "added"
    assert (await channels.room_members(CHANNEL, ROOM))[0].admin
    assert (await channels.invite(CHANNEL, ROOM, "+34611111111")).outcome == "invited"
    await channels.remove_member(CHANNEL, ROOM, "+34611111111")


async def test_create_room_sends_empty_invites(gateway: Gateway, client: Client) -> None:
    def create(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"name": "Team", "topic": "Plans", "invites": []}
        return reply({"channel": CHANNEL, "room": ROOM, "outcome": "created"})(request)

    gateway.on("POST", "/api/channels/whatsapp.main/rooms", create)
    created = await ChannelsAPI(client).create_room(CHANNEL, "Team", "Plans")
    assert created.participants is None


async def test_refusals_keep_their_reason(gateway: Gateway, client: Client) -> None:
    gateway.on(
        "POST",
        "/api/channels/whatsapp.main/send",
        reply(
            {
                "channel": CHANNEL,
                "error": "channel whatsapp.main is not in [gateway] send_channels",
            },
            status=403,
        ),
    )
    with pytest.raises(APIError) as caught:
        await ChannelsAPI(client).send(CHANNEL, "x", "y")
    assert is_unauthorized(caught.value)
    assert "send_channels" in str(caught.value)
