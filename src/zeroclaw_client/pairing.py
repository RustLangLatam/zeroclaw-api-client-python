"""Pairing (how a client gets its bearer token) and the paired devices.

Gateway handlers: ``crates/zeroclaw-gateway/src/lib.rs`` (``/pair``,
``/pair/code``, ``/admin/paircode*``) and ``api_pairing.rs``. A pairing code
is six digits, single use, valid ten minutes; the token it buys is ``zc_`` +
64 hex characters. Exchange a code for a token with :meth:`PairingAPI.pair`,
then get a client that uses it with :meth:`Client.with_token`.
"""

from __future__ import annotations

import builtins
from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import Field

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["Device", "Paired", "PairingAPI", "PairingCode"]


class Paired(Model):
    """A successful pairing. Its ``repr`` and ``str`` hide the token."""

    #: Always true.
    paired: bool
    #: Whether the token was saved in the gateway's configuration.
    persisted: bool = False
    #: The bearer token. Keep it secret.
    token: str = Field(repr=False)
    #: The gateway's note.
    message: str | None = None


class PairingCode(Model):
    """A pairing code and whether pairing is required."""

    #: Whether the request succeeded.
    success: bool = False
    #: Whether the gateway requires pairing.
    pairing_required: bool
    #: The six-digit code, when one is pending and may be shown.
    pairing_code: str | None = None
    #: The gateway's note.
    message: str | None = None


class Device(Model):
    """A paired device."""

    #: The device id.
    id: str
    #: The name given at pairing.
    name: str | None = None
    #: The type given at pairing (``legacy`` for tokens older than the registry).
    device_type: str | None = None
    #: When it paired (RFC 3339).
    paired_at: str
    #: When it was last seen (RFC 3339).
    last_seen: str
    #: The address it paired from.
    ip_address: str | None = None
    #: The advertised capabilities.
    capabilities: list[str] | None = None


class PairingAPI:
    """The pairing and paired devices endpoints, from :attr:`Client.pairing`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def pair(
        self, code: str, device_name: str | None = None, device_type: str | None = None
    ) -> Paired:
        """Exchange a pairing code for a bearer token, registering this client as a device.

        POST /api/pair. Unset ``device_name`` and ``device_type`` are sent as
        null. Public.
        """
        body = {
            "code": code,
            "device_name": device_name or None,
            "device_type": device_type or None,
        }
        return await self._c._call("POST", ["api", "pair"], Paired, json_body=body)

    async def pair_legacy(self, code: str) -> Paired:
        """Pair the original way, with the code in the ``X-Pairing-Code`` header.

        POST /pair. Public.
        """
        return await self._c._call("POST", ["pair"], Paired, headers={"X-Pairing-Code": code})

    async def initial_code(self) -> PairingCode:
        """Return the first-run pairing code, shown only while no client is paired yet.

        GET /pair/code. Public.
        """
        return await self._c._call("GET", ["pair", "code"], PairingCode)

    async def new_code(self) -> str:
        """Mint a new pairing code (replacing a pending one) so another device can pair.

        POST /api/pairing/initiate.
        """
        return await self._c._field("POST", ["api", "pairing", "initiate"], "pairing_code", str)

    async def admin_code(self) -> PairingCode:
        """Return the pending pairing code (GET /admin/paircode). Loopback only."""
        return await self._c._call("GET", ["admin", "paircode"], PairingCode)

    async def admin_new_code(self, rotate: str | None = None) -> PairingCode:
        """Mint a pairing code (POST /admin/paircode/new). Loopback only.

        ``rotate`` revokes first: ``all`` every token and device, otherwise
        the device with that id.
        """
        return await self._c._call(
            "POST", ["admin", "paircode", "new"], PairingCode, query={"rotate": rotate or None}
        )

    async def devices(self) -> builtins.list[Device]:
        """Return the paired devices (GET /api/devices)."""
        return await self._c._field("GET", ["api", "devices"], "devices", list[Device])

    async def revoke_device(self, id: str) -> None:
        """Revoke a device and its token; it may be this client's own (DELETE /api/devices/{id})."""
        await self._c._request("DELETE", ["api", "devices", id])

    async def rotate_device_token(self, id: str) -> str | None:
        """Revoke a device's token and mint a pairing code for it to pair again.

        The code is ``None`` when one was already pending or pairing is off
        (POST /api/devices/{id}/token/rotate).
        """
        envelope = await self._c._json("POST", ["api", "devices", id, "token", "rotate"])
        code = envelope.get("pairing_code") if isinstance(envelope, dict) else None
        return code if isinstance(code, str) else None

    async def set_capabilities(self, capabilities: Sequence[str]) -> builtins.list[str]:
        """Replace the capabilities this client's device advertises and return them.

        POST /api/devices/me/capabilities.
        """
        return await self._c._field(
            "POST",
            ["api", "devices", "me", "capabilities"],
            "capabilities",
            list[str],
            json_body={"capabilities": builtins.list(capabilities)},
        )
