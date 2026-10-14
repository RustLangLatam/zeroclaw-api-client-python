from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx
import pytest

from zeroclaw_client import Client
from zeroclaw_client._model import encode
from zeroclaw_client.sops import Decision, SopsAPI

from .conftest import Gateway, Handler, body, reply

SOP = {
    "name": "restock",
    "description": "d",
    "version": "1",
    "priority": "normal",
    "execution_mode": "auto",
    "triggers": [{"type": "manual"}],
    "steps": [],
}


@pytest.mark.parametrize(
    ("decision", "want"),
    [
        (Decision.approve(), "approve"),
        (Decision.deny("no"), {"deny": {"reason": "no"}}),
        (Decision.deny(), {"deny": {}}),
        (Decision.amend("t"), {"amend": {"text": "t"}}),
        (Decision.revise("shorter"), {"revise": {"guidance": "shorter"}}),
    ],
)
def test_decisions_are_externally_tagged(decision: Decision, want: object) -> None:
    assert encode(decision) == want


def expect(want: object, answer: object, status: int = 200) -> Handler:
    def handle(request: httpx.Request) -> httpx.Response:
        assert body(request) == want
        return reply(answer, status)(request)

    return handle


async def test_authors_sops(gateway: Gateway, client: Client) -> None:
    gateway.on("GET", "/api/sops", {"sops": [SOP]})
    gateway.on("GET", "/api/sops/restock/full", SOP)
    gateway.on("POST", "/api/sops", expect(SOP, {"created": "restock"}))
    gateway.on("PUT", "/api/sops/restock", expect(SOP, {"saved": "restock"}))
    gateway.on("DELETE", "/api/sops/restock", {"deleted": "restock"})
    for route in ["/api/sops/restock/graph", "/api/sops/graph-legend", "/api/sops/trigger-sources"]:
        gateway.on("GET", route, {"ok": route})
    gateway.on("POST", "/api/sops/graph-draft", expect({"sop": SOP}, {"nodes": []}))
    edit = {"op": "connect", "from": 1, "to": 2, "role": "sequence"}
    gateway.on(
        "POST",
        "/api/sops/wire-draft",
        expect({"sop": SOP, "edit": edit}, {"sop": SOP, "graph": {}}),
    )

    sops = SopsAPI(client)
    assert len(await sops.list()) == 1
    assert (await sops.get("restock"))["name"] == "restock"
    await sops.create(SOP)
    await sops.save("restock", SOP)
    await sops.delete("restock")
    assert await sops.graph("restock") == {"ok": "/api/sops/restock/graph"}
    assert await sops.graph_legend() == {"ok": "/api/sops/graph-legend"}
    assert await sops.trigger_sources() == {"ok": "/api/sops/trigger-sources"}
    assert await sops.graph_draft(SOP) == {"nodes": []}
    assert (await sops.wire_draft(SOP, edit))["graph"] == {}


async def test_follows_and_decides_runs(gateway: Gateway, client: Client) -> None:
    def runs(request: httpx.Request) -> httpx.Response:
        assert request.url.params["sop"] == "restock"
        return reply(
            {
                "runs": [
                    {
                        "run_id": "r1",
                        "sop_name": "restock",
                        "status": "waiting_approval",
                        "current_step": 1,
                        "total_steps": 2,
                        "started_at": "t",
                        "completed_at": None,
                        "trigger_source": "manual",
                        "active": True,
                    }
                ]
            }
        )(request)

    base = "/api/sops/restock"
    gateway.on("POST", f"{base}/run", expect({"payload": '{"sku":1}'}, {"run_id": "r1"}))
    gateway.on("GET", "/api/sops/runs", runs)
    gateway.on("GET", f"{base}/runs/r1/overlay", {"run_id": "r1", "waiting": True})
    gateway.on(
        "POST",
        f"{base}/runs/r1/decide",
        expect({"deny": {"reason": "not now"}}, {"run_id": "r1", "status": "failed"}),
    )
    gateway.on(
        "POST",
        f"{base}/runs/r1/cancel",
        expect({"reason": None}, {"run_id": "r1", "status": "cancel_requested"}, 202),
    )
    gateway.on(
        "GET",
        "/admin/sop/pending",
        {
            "pending": [
                {
                    "run_id": "r1",
                    "sop_name": "restock",
                    "step": 1,
                    "total_steps": 2,
                    "waiting_since": "t",
                    "kind": "approval",
                }
            ]
        },
    )
    gateway.on(
        "POST",
        "/admin/sop/approve",
        expect({"run_id": "r1", "reason": None}, {"outcome": "resumed", "run_id": "r1"}),
    )
    gateway.on(
        "POST",
        "/admin/sop/deny",
        expect({"run_id": "r1", "reason": "no"}, {"outcome": "denied", "run_id": "r1"}),
    )

    sops = SopsAPI(client)
    assert await sops.run("restock", '{"sku":1}') == "r1"
    listed = await sops.runs("restock")
    assert listed[0].active
    assert listed[0].completed_at is None
    assert await sops.run_overlay("restock", "r1") == {"run_id": "r1", "waiting": True}
    decided = await sops.decide("restock", "r1", Decision.deny("not now"))
    assert decided["status"] == "failed"
    assert (await sops.cancel("restock", "r1"))["status"] == "cancel_requested"
    assert (await sops.pending())[0].kind == "approval"
    assert await sops.approve("r1") == "resumed"
    assert await sops.deny("r1", "no") == "denied"


async def test_run_without_payload_sends_null(gateway: Gateway, client: Client) -> None:
    gateway.on("POST", "/api/sops/restock/run", expect({"payload": None}, {"run_id": "r2"}))
    assert await SopsAPI(client).run("restock") == "r2"


async def test_watch_runs_opens_the_runs_feed(
    client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened: list[Sequence[str]] = []

    async def open_socket(_: Client, segments: Sequence[str], query: Any = None) -> object:
        opened.append(segments)
        return object()

    monkeypatch.setattr("zeroclaw_client._client.open_socket", open_socket)
    await SopsAPI(client).watch_runs()
    assert list(opened[0]) == ["ws", "sops", "runs"]
