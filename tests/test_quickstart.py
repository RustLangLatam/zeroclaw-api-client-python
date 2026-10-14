from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.quickstart import QuickstartAPI

from .conftest import Gateway, Handler, body, reply


async def test_walks_through(gateway: Gateway, client: Client) -> None:
    submission = {"agent": {"name": "helper"}}

    def fields(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"section": "channel", "type_key": "whatsapp"}
        return reply({"fields": []})(request)

    def check(answer: dict[str, object]) -> Handler:
        def handle(request: httpx.Request) -> httpx.Response:
            assert body(request) == submission
            return reply(answer)(request)

        return handle

    def dismiss(request: httpx.Request) -> httpx.Response:
        # An empty last step goes as an explicit null.
        assert body(request) == {"run_id": "q1", "surface": "test", "last_step": None}
        return httpx.Response(204)

    gateway.on("GET", "/api/quickstart/state", {"quickstart_completed": False})
    gateway.on("POST", "/api/quickstart/fields", fields)
    gateway.on("POST", "/api/quickstart/validate", check({"kind": "ok"}))
    gateway.on(
        "POST", "/api/quickstart/apply", check({"kind": "applied", "daemon_restarted": True})
    )
    gateway.on("POST", "/api/quickstart/dismiss", dismiss)

    quickstart = QuickstartAPI(client)
    assert await quickstart.state() == {"quickstart_completed": False}
    assert (await quickstart.fields("channel", "whatsapp"))["fields"] == []
    assert (await quickstart.validate(submission))["kind"] == "ok"
    assert (await quickstart.apply(submission))["kind"] == "applied"
    await quickstart.dismiss("q1", "test", "")
