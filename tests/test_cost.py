from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.cost import CostAPI

from .conftest import Gateway, reply

COST = {
    "cost": {
        "session_cost_usd": 0.0,
        "daily_cost_usd": 0.1,
        "monthly_cost_usd": 1.0,
        "total_tokens": 10,
        "request_count": 2,
        "by_model": {
            "m": {
                "model": "m",
                "cost_usd": 1.0,
                "input_tokens": 6,
                "cached_input_tokens": 0,
                "output_tokens": 4,
                "total_tokens": 10,
                "request_count": 2,
            }
        },
        "by_agent": {},
    }
}


async def test_reports_by_window_and_agent(gateway: Gateway, client: Client) -> None:
    # One route serves both calls; the query tells them apart.
    def cost(request: httpx.Request) -> httpx.Response:
        params = dict(request.url.params)
        if "agent" in params:
            assert params == {"agent": "helper"}
        else:
            assert params == {"from": "2026-10-01T00:00:00Z"}
        return reply(COST)(request)

    gateway.on("GET", "/api/cost", cost)
    api = CostAPI(client)
    window = await api.summary("2026-10-01T00:00:00Z")
    assert window.by_model is not None
    assert window.by_model["m"].total_tokens == 10
    assert window.by_agent == {}
    assert (await api.agent("helper")).request_count == 2
    assert gateway.calls("GET", "/api/cost") == 2
