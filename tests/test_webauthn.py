from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.webauthn import WebAuthnAPI

from .conftest import Gateway, body, reply


async def test_webauthn_carries_ceremonies(gateway: Gateway, client: Client) -> None:
    def expect(want: object, answer: object) -> object:
        def handle(request: httpx.Request) -> httpx.Response:
            assert body(request) == want
            return reply(answer)(request)

        return handle

    def credentials(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"user_id": "u"}
        return reply({"credentials": []})(request)

    def delete(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"user_id": "u"}
        return reply({"status": "deleted"})(request)

    gateway.on(
        "POST",
        "/api/webauthn/register/start",
        expect({"user_id": "u", "user_name": "Ana"}, {"challenge": "c"}),
    )
    gateway.on(
        "POST", "/api/webauthn/register/finish", expect({"id": "k1"}, {"credential_id": "k1"})
    )
    gateway.on("POST", "/api/webauthn/auth/start", expect({"user_id": "u"}, {"challenge": "c2"}))
    gateway.on("POST", "/api/webauthn/auth/finish", expect({"id": "k1"}, {"status": "ok"}))
    gateway.on("GET", "/api/webauthn/credentials", credentials)
    gateway.on("DELETE", "/api/webauthn/credentials/k%2F1", delete)

    webauthn = WebAuthnAPI(client)
    assert (await webauthn.register_start("u", "Ana"))["challenge"] == "c"
    assert (await webauthn.register_finish({"id": "k1"}))["credential_id"] == "k1"
    assert (await webauthn.auth_start("u"))["challenge"] == "c2"
    assert (await webauthn.auth_finish({"id": "k1"}))["status"] == "ok"
    assert (await webauthn.credentials("u"))["credentials"] == []
    await webauthn.delete_credential("u", "k/1")
