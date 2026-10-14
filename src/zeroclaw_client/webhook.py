"""One-shot messages to an agent: the generic webhook and the A2A JSON-RPC endpoint.

Gateway handlers: ``crates/zeroclaw-gateway/src/lib.rs`` (``handle_webhook``)
and ``a2a.rs`` (agent-to-agent). Both run a whole agent turn and answer with its reply; for
streaming, tool approvals or a lasting conversation use :meth:`Client.chat`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._errors import APIError, DecodeError
from ._model import Model, decode

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["AgentReply", "WebhookAPI", "WebhookReply"]


class AgentReply(Model):
    """An agent's reply to a webhook."""

    #: The reply.
    response: str
    #: The model that answered.
    model: str


class WebhookReply(Model):
    """The answer of :meth:`WebhookAPI.send`.

    The agent's reply, or ``duplicate`` when the idempotency key was already
    used and nothing ran.
    """

    #: The agent's reply; ``None`` when ``duplicate``.
    reply: AgentReply | None = None
    #: Whether the idempotency key was already used.
    duplicate: bool = False


class WebhookAPI:
    """The webhook and A2A endpoints, from :attr:`Client.webhook`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def send(
        self,
        message: str,
        *,
        agent: str | None = None,
        secret: str | None = None,
        idempotency_key: str | None = None,
        session_id: str | None = None,
    ) -> WebhookReply:
        """Send ``message`` and return the agent's reply (POST /webhook).

        Args:
            message: The message.
            agent: The agent to answer (the default agent when ``None``).
            secret: Sent as ``X-Webhook-Secret``, when the gateway sets
                ``webhook_secret``.
            idempotency_key: Sent as ``X-Idempotency-Key``: a repeat within
                the gateway's window is not run again, and answers a reply
                with ``duplicate`` set.
            session_id: Sent as ``X-Session-Id``: it keeps calls in one
                conversation (``[A-Za-z0-9._-]``, at most 128 characters).
        """
        headers = {
            name: value
            for name, value in (
                ("X-Webhook-Secret", secret),
                ("X-Idempotency-Key", idempotency_key),
                ("X-Session-Id", session_id),
            )
            if value
        }
        raw = await self._c._json(
            "POST",
            ["webhook"],
            query={"agent": agent or None},
            json_body={"message": message},
            headers=headers,
        )
        if isinstance(raw, dict) and raw.get("status") == "duplicate":
            return WebhookReply(duplicate=True)
        return WebhookReply(reply=decode(raw, AgentReply))

    async def a2a_send(self, alias: str, text: str) -> str:
        """Send ``text`` to a published agent with ``message/send`` (POST /a2a/{alias}).

        Returns the text of its answer. Needs the ``a2a`` feature and
        ``a2a.server.enabled`` on the gateway.

        Raises:
            APIError: With status 200, for a JSON-RPC error.
        """
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": {"parts": [{"kind": "text", "text": text}]}},
        }
        raw = await self._c._json("POST", ["a2a", alias], json_body=payload)
        if not isinstance(raw, dict):
            raise DecodeError("unexpected gateway response: not a JSON-RPC object")
        error = raw.get("error")
        if error is not None:
            message = error.get("message") if isinstance(error, dict) else None
            raise APIError(200, message if isinstance(message, str) else "A2A error", raw)
        result = raw.get("result") or {}
        texts = [
            part["text"]
            for artifact in result.get("artifacts") or []
            for part in artifact.get("parts") or []
            if isinstance(part.get("text"), str)
        ]
        return "\n".join(texts)

    async def agent_card(self, alias: str) -> Any:
        """Return a published agent's A2A card. Public.

        GET /a2a/{alias}/.well-known/agent-card.json.
        """
        return await self._c._json("GET", ["a2a", alias, ".well-known", "agent-card.json"])
