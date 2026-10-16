from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.channels import ChannelsAPI

from .conftest import Gateway, body, reply

CHANNEL = "whatsapp.main"


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
