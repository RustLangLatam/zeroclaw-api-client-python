from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.sessions import SessionsAPI

from .conftest import Gateway, body, reply


async def test_read_and_manage(gateway: Gateway, client: Client) -> None:
    gateway.on(
        "GET",
        "/api/sessions",
        {
            "sessions": [
                {
                    "session_id": "abc",
                    "session_key": "gw_abc",
                    "created_at": "t",
                    "last_activity": "t",
                    "message_count": 2,
                    "agent_alias": "helper",
                    "channel_id": None,
                }
            ]
        },
    )
    gateway.on(
        "GET",
        "/api/sessions/running",
        {
            "sessions": [
                {"session_id": "abc", "created_at": "t", "last_activity": "t", "message_count": 2}
            ]
        },
    )
    gateway.on(
        "GET",
        "/api/sessions/gw_abc/messages",
        {
            "session_id": "gw_abc",
            "session_persistence": True,
            "messages": [{"role": "user", "content": "hi", "created_at": "t"}],
        },
    )

    def add(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"content": "Reminder"}
        return reply({"status": "ok"})(request)

    def rename(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"name": "Support"}
        return reply({"session_id": "gw_abc", "name": "Support"})(request)

    gateway.on("POST", "/api/sessions/gw_abc/messages", add)
    gateway.on(
        "GET",
        "/api/sessions/gw_abc/state",
        {"session_id": "gw_abc", "state": "running", "turn_id": "t1"},
    )
    gateway.on("PUT", "/api/sessions/gw_abc", rename)
    gateway.on("POST", "/api/sessions/gw_abc/abort", {"status": "no_active_response"})
    gateway.on("DELETE", "/api/sessions/gw_abc", {"deleted": True, "session_id": "gw_abc"})

    sessions = SessionsAPI(client)
    assert (await sessions.list())[0].session_key == "gw_abc"
    assert len(await sessions.running()) == 1
    assert (await sessions.messages("gw_abc"))[0].role == "user"
    await sessions.add_message("gw_abc", "Reminder")
    state = await sessions.state("gw_abc")
    assert state.state == "running"
    assert state.turn_id == "t1"
    await sessions.rename("gw_abc", "Support")
    assert not await sessions.abort("gw_abc")
    await sessions.delete("gw_abc")


async def test_abort_reports_a_running_turn(gateway: Gateway, client: Client) -> None:
    gateway.on("POST", "/api/sessions/gw_abc/abort", {"status": "aborted"})
    assert await SessionsAPI(client).abort("gw_abc")
