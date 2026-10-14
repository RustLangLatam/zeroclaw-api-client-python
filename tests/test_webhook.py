from __future__ import annotations

import httpx
import pytest

from zeroclaw_client import APIError, Client
from zeroclaw_client.webhook import AgentReply, WebhookAPI, WebhookReply

from .conftest import Gateway, body, reply


async def test_webhook_sends_headers_and_detects_duplicates(
    gateway: Gateway, client: Client
) -> None:
    def webhook(request: httpx.Request) -> httpx.Response:
        if request.headers.get("X-Idempotency-Key") == "k2":
            assert not request.url.params
            assert "X-Webhook-Secret" not in request.headers
            assert "X-Session-Id" not in request.headers
            return reply({"status": "duplicate", "idempotent": True, "message": ""})(request)
        assert dict(request.url.params) == {"agent": "helper"}
        assert request.headers["X-Webhook-Secret"] == "s3"
        assert request.headers["X-Idempotency-Key"] == "k1"
        assert request.headers["X-Session-Id"] == "s.1"
        assert body(request) == {"message": "Ping"}
        return reply({"response": "Pong", "model": "m"})(request)

    gateway.on("POST", "/webhook", webhook)
    hook = WebhookAPI(client)
    got = await hook.send(
        "Ping", agent="helper", secret="s3", idempotency_key="k1", session_id="s.1"
    )
    assert got == WebhookReply(reply=AgentReply(response="Pong", model="m"))
    assert await hook.send("Ping", idempotency_key="k2") == WebhookReply(duplicate=True)


async def test_a2a_returns_the_answer_text_or_the_rpc_error(
    gateway: Gateway, client: Client
) -> None:
    def a2a(request: httpx.Request) -> httpx.Response:
        assert body(request) == {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": {"parts": [{"kind": "text", "text": "Hi"}]}},
        }
        return reply(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "result": {
                    "id": "t",
                    "kind": "task",
                    "status": {"state": "completed"},
                    "artifacts": [
                        {"artifactId": "a", "parts": [{"kind": "text", "text": "Hello"}]},
                        {"artifactId": "b", "parts": [{"kind": "data"}, {"text": "again"}]},
                    ],
                },
            }
        )(request)

    gateway.on("POST", "/a2a/helper", a2a)
    gateway.on(
        "POST",
        "/a2a/other",
        {"jsonrpc": "2.0", "id": 1, "error": {"code": -32000, "message": "agent failed"}},
    )
    gateway.on("GET", "/a2a/helper/.well-known/agent-card.json", {"name": "helper"}, public=True)

    hook = WebhookAPI(client)
    assert await hook.a2a_send("helper", "Hi") == "Hello\nagain"
    with pytest.raises(APIError, match="agent failed") as err:
        await hook.a2a_send("other", "Hi")
    assert err.value.status == 200
    assert err.value.body["error"]["code"] == -32000
    assert await hook.agent_card("helper") == {"name": "helper"}
