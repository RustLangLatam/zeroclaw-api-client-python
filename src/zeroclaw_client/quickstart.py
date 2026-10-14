"""The quickstart: setting up a first agent in one submission.

Model provider, risk and runtime profiles, memory, channels and
personality. Gateway handler: ``crates/zeroclaw-gateway/src/api_quickstart.rs``;
submission type ``BuilderSubmission`` in
``crates/zeroclaw-config/src/presets.rs``. Validation problems come back in a
successful answer (``{"kind": "errors", …}``), not as HTTP errors.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["QuickstartAPI"]


class QuickstartAPI:
    """The quickstart endpoints (``/api/quickstart``), from :attr:`Client.quickstart`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def state(self) -> Any:
        """Return what exists and what can be chosen (GET /api/quickstart/state).

        Provider and channel types, presets, memory kinds, …
        """
        return await self._c._json("GET", ["api", "quickstart", "state"])

    async def fields(self, section: str, type_key: str) -> Any:
        """Return the fields a section of type ``type_key`` needs (POST /api/quickstart/fields).

        ``section`` is ``model_provider``, ``channel`` or ``peer_group``.
        """
        return await self._c._json(
            "POST",
            ["api", "quickstart", "fields"],
            json_body={"section": section, "type_key": type_key},
        )

    async def validate(self, submission: Any) -> Any:
        """Check a submission, encoded as JSON (POST /api/quickstart/validate).

        Answers ``{"kind": "ok"}`` or ``{"kind": "errors", "errors": […]}``.
        """
        return await self._c._json("POST", ["api", "quickstart", "validate"], json_body=submission)

    async def apply(self, submission: Any) -> Any:
        """Save a submission (POST /api/quickstart/apply).

        On ``{"kind": "applied", …, "daemon_restarted": true}`` the gateway
        drops connections briefly while it reloads.
        """
        return await self._c._json("POST", ["api", "quickstart", "apply"], json_body=submission)

    async def dismiss(self, run_id: str, surface: str, last_step: str | None = None) -> None:
        """Record that the quickstart was closed (POST /api/quickstart/dismiss).

        ``surface`` is ``web``, ``tui``, ``cli`` or ``test``.
        """
        await self._c._request(
            "POST",
            ["api", "quickstart", "dismiss"],
            json_body={"run_id": run_id, "surface": surface, "last_step": last_step or None},
        )
