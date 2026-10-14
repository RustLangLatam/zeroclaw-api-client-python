"""Model usage and its cost.

Gateway handler: ``crates/zeroclaw-gateway/src/api.rs`` (``/api/cost``); types
in ``crates/zeroclaw-config/src/cost/types.rs``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client, Query

__all__ = ["AgentCostStats", "CostAPI", "CostSummary", "ModelStats"]


class ModelStats(Model):
    """One model's usage."""

    #: The model.
    model: str
    #: The cost, USD.
    cost_usd: float
    #: The input tokens.
    input_tokens: int
    #: The cached input tokens.
    cached_input_tokens: int
    #: The output tokens.
    output_tokens: int
    #: All tokens.
    total_tokens: int
    #: The calls.
    request_count: int


class AgentCostStats(Model):
    """One agent's usage."""

    #: The agent.
    agent_alias: str
    #: The cost, USD.
    cost_usd: float
    #: All tokens.
    total_tokens: int
    #: The input tokens.
    input_tokens: int
    #: The output tokens.
    output_tokens: int
    #: The cached input tokens.
    cached_input_tokens: int
    #: The calls.
    request_count: int


class CostSummary(Model):
    """Usage totals."""

    #: The cost of the current session, USD.
    session_cost_usd: float
    #: The cost today, USD.
    daily_cost_usd: float
    #: The cost this month, USD.
    monthly_cost_usd: float
    #: The tokens in the window.
    total_tokens: int
    #: The model calls in the window.
    request_count: int
    #: The usage by model.
    by_model: dict[str, ModelStats] | None = None
    #: The usage by agent.
    by_agent: dict[str, AgentCostStats] | None = None


class CostAPI:
    """The usage and cost endpoint (``/api/cost``), from :attr:`Client.cost`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def summary(self, from_: str | None = None, to: str | None = None) -> CostSummary:
        """Return the usage in ``[from_, to)``, broken down by model and by agent.

        GET /api/cost. Bounds are RFC 3339; an unset one leaves the window
        open on that side.
        """
        return await self._fetch({"from": from_ or None, "to": to or None})

    async def agent(self, agent: str) -> CostSummary:
        """Return one agent's session and daily figures (GET /api/cost?agent=).

        The gateway ignores a time window here.
        """
        return await self._fetch({"agent": agent})

    async def _fetch(self, query: Query) -> CostSummary:
        return await self._c._field("GET", ["api", "cost"], "cost", CostSummary, query=query)
