"""Standard operating procedures (SOPs): authoring, graphs, runs, approvals and cancellation.

Gateway handlers: ``crates/zeroclaw-gateway/src/api_sop_author.rs`` and
``api_sop.rs``. An SOP definition (name, description, version, priority,
execution_mode, triggers, steps, …) is large and versioned with ZeroClaw, so
it travels as decoded JSON (``Any``); so do graphs and run overlays. Every
route answers 503 while the SOP subsystem is disabled.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from pydantic import model_serializer

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client
    from .chat import Feed

__all__ = ["Decision", "PendingApproval", "SopRun", "SopsAPI"]


class Decision(Model):
    """An answer to a waiting SOP run.

    Built with :meth:`approve`, :meth:`deny`, :meth:`amend` or
    :meth:`revise`. It encodes externally tagged: ``"approve"``,
    ``{"deny": {"reason": …}}``, ``{"amend": {"text": …}}`` or
    ``{"revise": {"guidance": …}}``.
    """

    #: ``approve``, ``deny``, ``amend`` or ``revise``.
    kind: str
    #: Why, for ``deny`` (empty for none).
    reason: str = ""
    #: The checkpoint's new text, for ``amend``.
    text: str = ""
    #: How to redo the step, for ``revise``.
    guidance: str = ""

    @classmethod
    def approve(cls) -> Decision:
        """Go on."""
        return cls(kind="approve")

    @classmethod
    def deny(cls, reason: str = "") -> Decision:
        """Stop the run; ``reason`` may be empty."""
        return cls(kind="deny", reason=reason)

    @classmethod
    def amend(cls, text: str) -> Decision:
        """Change the checkpoint's text and go on."""
        return cls(kind="amend", text=text)

    @classmethod
    def revise(cls, guidance: str) -> Decision:
        """Redo the step with ``guidance``."""
        return cls(kind="revise", guidance=guidance)

    @model_serializer
    def _tagged(self) -> Any:
        if self.kind == "deny":
            return {"deny": {"reason": self.reason} if self.reason else {}}
        if self.kind == "amend":
            return {"amend": {"text": self.text}}
        if self.kind == "revise":
            return {"revise": {"guidance": self.guidance}}
        return self.kind


class SopRun(Model):
    """A run in a listing."""

    #: The run id.
    run_id: str
    #: The SOP.
    sop_name: str
    #: ``pending``, ``running``, ``cancel_requested``, ``waiting_approval``,
    #: ``paused_checkpoint``, ``completed``, ``failed`` or ``cancelled``.
    status: str
    #: The current step.
    current_step: int
    #: The number of steps in all.
    total_steps: int
    #: The start (RFC 3339).
    started_at: str
    #: The end.
    completed_at: str | None = None
    #: What started it.
    trigger_source: str
    #: Whether it is still running.
    active: bool


class PendingApproval(Model):
    """A run waiting for an operator."""

    #: The run id.
    run_id: str
    #: The SOP.
    sop_name: str
    #: The step waiting.
    step: int
    #: The number of steps in all.
    total_steps: int
    #: Since when.
    waiting_since: str | None = None
    #: ``approval`` or ``checkpoint``.
    kind: str


class SopsAPI:
    """The standard operating procedure endpoints (``/api/sops``), from :attr:`Client.sops`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def list(self) -> builtins.list[Any]:
        """Return every SOP definition that loads (GET /api/sops)."""
        return await self._c._field("GET", ["api", "sops"], "sops", list[Any])

    async def get(self, name: str) -> Any:
        """Return one SOP definition (GET /api/sops/{name}/full)."""
        return await self._c._json("GET", ["api", "sops", name, "full"])

    async def create(self, sop: Any) -> None:
        """Create an SOP, 409 when the name exists (POST /api/sops)."""
        await self._c._request("POST", ["api", "sops"], json_body=sop)

    async def save(self, name: str, sop: Any) -> None:
        """Save an SOP; steps are renumbered 1..N (PUT /api/sops/{name})."""
        await self._c._request("PUT", ["api", "sops", name], json_body=sop)

    async def delete(self, name: str) -> None:
        """Delete an SOP (DELETE /api/sops/{name})."""
        await self._c._request("DELETE", ["api", "sops", name])

    async def graph(self, name: str) -> Any:
        """Return the SOP as a node graph, with layout and diagnostics.

        GET /api/sops/{name}/graph.
        """
        return await self._c._json("GET", ["api", "sops", name, "graph"])

    async def graph_draft(self, sop: Any) -> Any:
        """Return the graph of an unsaved definition (POST /api/sops/graph-draft)."""
        return await self._c._json("POST", ["api", "sops", "graph-draft"], json_body={"sop": sop})

    async def wire_draft(self, sop: Any, edit: Any) -> Any:
        """Apply a wiring edit to an unsaved definition (POST /api/sops/wire-draft).

        ``edit`` is ``{op: "connect" | "disconnect", from, to, role, port?}``.
        Returns ``{sop, graph}``.
        """
        return await self._c._json(
            "POST", ["api", "sops", "wire-draft"], json_body={"sop": sop, "edit": edit}
        )

    async def graph_legend(self) -> Any:
        """Say what the graph's roles, pins and run states mean (GET /api/sops/graph-legend)."""
        return await self._c._json("GET", ["api", "sops", "graph-legend"])

    async def trigger_sources(self) -> Any:
        """Return the trigger sources, their fields and the channels that can start an SOP.

        GET /api/sops/trigger-sources.
        """
        return await self._c._json("GET", ["api", "sops", "trigger-sources"])

    async def run(self, name: str, payload: str | None = None) -> str:
        """Start the SOP through its manual trigger (POST /api/sops/{name}/run).

        ``payload`` is JSON text handed to the run. Returns the run id (an
        existing run's when the SOP coalesces).
        """
        return await self._c._field(
            "POST",
            ["api", "sops", name, "run"],
            "run_id",
            str,
            json_body={"payload": payload or None},
        )

    async def runs(self, sop: str | None = None) -> builtins.list[SopRun]:
        """Return active and recent runs, newest first, of one SOP when ``sop`` is set.

        GET /api/sops/runs.
        """
        return await self._c._field(
            "GET", ["api", "sops", "runs"], "runs", list[SopRun], query={"sop": sop or None}
        )

    async def watch_runs(self) -> Feed:
        """Follow SOP runs live (GET /ws/sops/runs).

        A ``{"type": "snapshot", "runs": […]}`` first, then
        ``{"type": "run", "run": …}`` on every change (lagged, disabled and
        error frames too).
        """
        return await self._c._feed("ws", "sops", "runs")

    async def run_overlay(self, name: str, run_id: str) -> Any:
        """Return a run's state per step, with its tool calls.

        GET /api/sops/{name}/runs/{run_id}/overlay.
        """
        return await self._c._json("GET", ["api", "sops", name, "runs", run_id, "overlay"])

    async def decide(self, name: str, run_id: str, decision: Decision) -> Any:
        """Answer a run waiting for approval or at a checkpoint; returns the run overlay.

        POST /api/sops/{name}/runs/{run_id}/decide.
        """
        return await self._c._json(
            "POST", ["api", "sops", name, "runs", run_id, "decide"], json_body=decision
        )

    async def cancel(self, name: str, run_id: str, reason: str | None = None) -> Any:
        """Cancel a run at its next step boundary (POST /api/sops/{name}/runs/{run_id}/cancel)."""
        return await self._c._json(
            "POST",
            ["api", "sops", name, "runs", run_id, "cancel"],
            json_body={"reason": reason or None},
        )

    async def pending(self) -> builtins.list[PendingApproval]:
        """Return the runs waiting for an approval or a checkpoint (GET /admin/sop/pending).

        Loopback, or remote admin with pairing.
        """
        return await self._c._field(
            "GET", ["admin", "sop", "pending"], "pending", list[PendingApproval]
        )

    async def approve(self, run_id: str) -> str:
        """Approve a waiting run (POST /admin/sop/approve).

        Returns the outcome (``resumed``, ``already_resolved``,
        ``pending_quorum (…)``, …).
        """
        return await self._resolve("approve", run_id, None)

    async def deny(self, run_id: str, reason: str | None = None) -> str:
        """Deny a waiting run (POST /admin/sop/deny); returns the outcome."""
        return await self._resolve("deny", run_id, reason)

    async def _resolve(self, action: str, run_id: str, reason: str | None) -> str:
        return await self._c._field(
            "POST",
            ["admin", "sop", action],
            "outcome",
            str,
            json_body={"run_id": run_id, "reason": reason or None},
        )
