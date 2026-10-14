"""Hardware-key (WebAuthn) registration and assertion, an extra check on top of the bearer token.

Gateway handler: ``crates/zeroclaw-gateway/src/api_webauthn.rs`` (built with
the ``webauthn`` feature; 404 when it is off). The ceremony itself runs in the
authenticator (a browser or a security-key library): this API only carries
its JSON, with ZeroClaw's snake_case field names and base64url binary fields.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["WebAuthnAPI"]


class WebAuthnAPI:
    """The WebAuthn endpoints (``/api/webauthn``), from :attr:`Client.webauthn`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def register_start(self, user_id: str, user_name: str) -> Any:
        """Return the creation challenge for a new key of ``user_id``.

        POST /api/webauthn/register/start.
        """
        return await self._post({"user_id": user_id, "user_name": user_name}, "register", "start")

    async def register_finish(self, credential: Any) -> Any:
        """Send the authenticator's answer and return the registered key.

        POST /api/webauthn/register/finish. ``credential`` holds
        ``challenge``, ``id``, ``attestation_object``, ``client_data_json`` and
        an optional ``label``; the answer is ``{credential_id, label,
        registered_at}``.
        """
        return await self._post(credential, "register", "finish")

    async def auth_start(self, user_id: str) -> Any:
        """Return the assertion challenge for ``user_id`` (POST /api/webauthn/auth/start)."""
        return await self._post({"user_id": user_id}, "auth", "start")

    async def auth_finish(self, assertion: Any) -> Any:
        """Send the authenticator's assertion (POST /api/webauthn/auth/finish).

        ``assertion`` holds ``challenge``, ``id``, ``authenticator_data``,
        ``client_data_json`` and ``signature``. Refused with 401 when it does
        not verify.
        """
        return await self._post(assertion, "auth", "finish")

    async def credentials(self, user_id: str) -> Any:
        """Return the keys of ``user_id`` (GET /api/webauthn/credentials)."""
        return await self._c._json(
            "GET", ["api", "webauthn", "credentials"], query={"user_id": user_id}
        )

    async def delete_credential(self, user_id: str, credential_id: str) -> None:
        """Remove key ``credential_id`` of ``user_id`` (DELETE /api/webauthn/credentials/{id})."""
        await self._c._request(
            "DELETE",
            ["api", "webauthn", "credentials", credential_id],
            query={"user_id": user_id},
        )

    async def _post(self, payload: Any, *action: str) -> Any:
        """Post ``payload`` to /api/webauthn/{action...}."""
        return await self._c._json("POST", ["api", "webauthn", *action], json_body=payload)
