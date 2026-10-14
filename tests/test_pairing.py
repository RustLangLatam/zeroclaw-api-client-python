from __future__ import annotations

import httpx
import pytest

from zeroclaw_client import APIError, Client, RetryPolicy, is_rate_limited, status_code
from zeroclaw_client.pairing import Paired, PairingAPI

from .conftest import Gateway, body, reply


def test_pairing_never_shows_its_token() -> None:
    paired = Paired.model_validate(
        {"paired": True, "persisted": True, "token": "zc_secret", "message": "Pairing successful"}
    )
    for shown in (repr(paired), str(paired), f"{paired}", f"{paired!r}"):
        assert "zc_secret" not in shown


async def test_a_code_buys_a_token_that_later_calls_use(gateway: Gateway) -> None:
    def pair(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"code": "123456", "device_name": "sdk", "device_type": None}
        assert "Authorization" not in request.headers
        return reply(
            {"paired": True, "persisted": True, "token": "zc_new", "message": "Pairing successful"}
        )(request)

    def devices(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer zc_new"
        return reply(
            {
                "devices": [
                    {
                        "id": "d1",
                        "name": "sdk",
                        "device_type": None,
                        "paired_at": "t",
                        "last_seen": "t",
                        "ip_address": "127.0.0.1",
                    }
                ],
                "count": 1,
            }
        )(request)

    gateway.on("POST", "/api/pair", pair, public=True)
    gateway.on("GET", "/api/devices", devices, public=True)

    async with Client(
        "http://gateway.test",
        transport=httpx.MockTransport(gateway.handle),
        retry=RetryPolicy.none(),
    ) as anonymous:
        paired = await PairingAPI(anonymous).pair("123456", "sdk")
        client = anonymous.with_token(paired.token)
        assert (await PairingAPI(client).devices())[0].id == "d1"
    assert not gateway.unexpected, gateway.unexpected


async def test_wrong_codes_are_refused_with_the_gateways_reason(
    gateway: Gateway, client: Client
) -> None:
    def legacy(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Pairing-Code"] == "000000"
        return reply(
            {"error": "Too many pairing requests. Please retry later.", "retry_after": 60},
            status=429,
        )(request)

    gateway.on(
        "POST",
        "/api/pair",
        reply({"paired": False, "error": "Invalid or expired pairing code"}, status=400),
        public=True,
    )
    gateway.on("POST", "/pair", legacy, public=True)

    pairing = PairingAPI(client)
    with pytest.raises(APIError) as caught:
        await pairing.pair("1")
    assert status_code(caught.value) == 400
    assert "Invalid or expired" in str(caught.value)
    with pytest.raises(APIError) as caught:
        await pairing.pair_legacy("000000")
    assert is_rate_limited(caught.value)


async def test_codes_are_minted_and_devices_managed(gateway: Gateway, client: Client) -> None:
    def admin_new(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"rotate": "all"}
        return reply({"success": True, "pairing_required": True, "pairing_code": "222222"})(request)

    def capabilities(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"capabilities": ["chat"]}
        return reply({"message": "Capabilities updated", "capabilities": ["chat"]})(request)

    gateway.on(
        "GET",
        "/pair/code",
        {"success": True, "pairing_required": True, "pairing_code": None},
        public=True,
    )
    gateway.on(
        "POST",
        "/api/pairing/initiate",
        {"pairing_code": "654321", "message": "New pairing code generated"},
    )
    gateway.on(
        "GET",
        "/admin/paircode",
        {"success": True, "pairing_required": True, "pairing_code": "111111"},
    )
    gateway.on("POST", "/admin/paircode/new", admin_new)
    gateway.on("DELETE", "/api/devices/d1", {"message": "Device revoked", "device_id": "d1"})
    gateway.on(
        "POST",
        "/api/devices/d2/token/rotate",
        {"device_id": "d2", "pairing_code": "333333", "message": ""},
    )
    gateway.on(
        "POST",
        "/api/devices/d3/token/rotate",
        {"device_id": "d3", "pairing_code": None, "message": ""},
    )
    gateway.on("POST", "/api/devices/me/capabilities", capabilities)

    pairing = PairingAPI(client)
    assert (await pairing.initial_code()).pairing_code is None
    assert await pairing.new_code() == "654321"
    assert (await pairing.admin_code()).pairing_code == "111111"
    assert (await pairing.admin_new_code("all")).pairing_code == "222222"
    await pairing.revoke_device("d1")
    assert await pairing.rotate_device_token("d2") == "333333"
    assert await pairing.rotate_device_token("d3") is None
    assert await pairing.set_capabilities(["chat"]) == ["chat"]
