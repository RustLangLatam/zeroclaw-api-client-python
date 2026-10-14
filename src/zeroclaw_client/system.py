"""The gateway itself: health, status, metrics, diagnostics, tools, integrations and logs.

Also version upgrades and daemon administration.

Gateway handlers: ``crates/zeroclaw-gateway/src/lib.rs`` (``/health``,
``/metrics``, ``/admin/*``), ``api.rs``, ``api_logs.rs``, ``version.rs`` and
``api_sop_author.rs`` (tool parameter options).
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client, Query

__all__ = [
    "AdminResponse",
    "CLITool",
    "ComponentHealth",
    "Diagnostic",
    "DoctorReport",
    "DoctorSummary",
    "Health",
    "HealthSnapshot",
    "Integration",
    "IntegrationSetting",
    "LogPage",
    "LogQuery",
    "ProcessStats",
    "Status",
    "SystemAPI",
    "ToolOption",
    "ToolSpec",
    "Tui",
    "UpgradeStatus",
    "VersionCheck",
]


class Health(Model):
    """The answer of GET /health."""

    #: Always ``ok`` while the gateway answers.
    status: str
    #: Whether at least one client is paired.
    paired: bool
    #: Whether requests need a bearer token.
    require_pairing: bool
    #: The component health (raw when the gateway could not serialize it).
    runtime: Any = None


class ComponentHealth(Model):
    """One component's health."""

    #: ``ok``, ``error``, …
    status: str
    #: The last update (RFC 3339).
    updated_at: str
    #: The last time it was healthy.
    last_ok: str | None = None
    #: The last error.
    last_error: str | None = None
    #: How many times it was restarted.
    restart_count: int


class HealthSnapshot(Model):
    """The runtime's component health."""

    #: The daemon process id.
    pid: int
    #: When it was computed (RFC 3339).
    updated_at: str
    #: The time since the daemon started, in seconds.
    uptime_seconds: int
    #: The health per component (``gateway``, ``channel:whatsapp.x``, …).
    components: dict[str, ComponentHealth]


class ProcessStats(Model):
    """The daemon's resource use."""

    #: The resident memory, in bytes.
    rss_bytes: int
    #: The host memory, in bytes.
    system_ram_total_bytes: int
    #: The CPU use.
    cpu_percent: float | None = None
    #: The number of host CPUs.
    num_cpus: int


class Status(Model):
    """The answer of GET /api/status."""

    #: The ZeroClaw version.
    version: str
    #: The model provider in use, as ``type.alias``.
    model_provider: str | None = None
    #: The model in use.
    model: str
    #: The sampling temperature.
    temperature: float | None = None
    #: The time since the daemon started, in seconds.
    uptime_seconds: int
    #: When the daemon started (RFC 3339).
    daemon_started_at: str
    #: The gateway port.
    gateway_port: int
    #: The UI locale.
    locale: str
    #: The memory backend.
    memory_backend: str
    #: Whether a client is paired.
    paired: bool
    #: The configured channels, as ``type.alias``.
    channels: dict[str, bool]
    #: The connected nodes and peers found on the network.
    nodes: Any = None
    #: The component health.
    health: HealthSnapshot
    #: The agent asked about, if any.
    agent_alias: str | None = None
    #: The process figures.
    process: ProcessStats | None = None
    #: Whether the daemon checks for updates.
    check_updates: bool
    #: Whether self-upgrade is allowed.
    allow_self_upgrade: bool
    #: ``supervised``, ``self_respawn`` or ``manual``.
    restart_mode: str | None = None
    #: How to restart the daemon.
    restart_hint: str | None = None
    #: The configuration a running channel picks up without a restart.
    live_channel_config: list[str] | None = None


class Diagnostic(Model):
    """One diagnostic."""

    #: ``ok``, ``warn`` or ``error``.
    severity: str
    #: The area checked.
    category: str
    #: The finding.
    message: str


class DoctorSummary(Model):
    """The counts of a doctor run."""

    #: The number of checks passed.
    ok: int
    #: The number of warnings.
    warnings: int
    #: The number of errors.
    errors: int


class DoctorReport(Model):
    """The result of :meth:`SystemAPI.doctor`."""

    #: Each check.
    results: list[Diagnostic]
    #: The results counted by severity.
    summary: DoctorSummary


class ToolSpec(Model):
    """A tool an agent can call."""

    #: The tool name.
    name: str
    #: What it does.
    description: str
    #: The JSON Schema of its arguments.
    parameters: Any = None
    #: The JSON Schema of its output, when declared.
    output: Any = None
    #: The option domain of the parameters that take known values.
    param_domains: dict[str, str] | None = None


class ToolOption(Model):
    """A value a tool parameter accepts."""

    #: The value.
    value: str
    #: The label to show.
    label: str | None = None
    #: An extra hint.
    hint: str | None = None


class Integration(Model):
    """An integration."""

    #: The integration's name.
    name: str
    #: What it does.
    description: str
    #: ``Chat``, ``AiModel``, ``ToolsAutomation`` or ``Platform``.
    category: str
    #: The category in words.
    category_label: str
    #: ``Available`` or ``Active``.
    status: str


class IntegrationSetting(Model):
    """An integration's state."""

    #: Whether it is active.
    enabled: bool
    #: Its category.
    category: str
    #: Its status.
    status: str


class CLITool(Model):
    """A command-line tool on the host."""

    #: The command name.
    name: str
    #: The full path.
    path: str
    #: The reported version.
    version: str | None = None
    #: The kind of tool (``VersionControl``, ``Language``, …).
    category: str


class Tui(Model):
    """A terminal client connected to the daemon."""

    #: The client id.
    tui_id: str
    #: When it connected (RFC 3339).
    connected_at: str
    #: Who it is.
    peer_label: str
    #: ``unix`` or ``wss``.
    transport: str


class LogQuery(Model):
    """The filters of :meth:`SystemAPI.logs`; ``None``, empty and zero values are not sent."""

    #: Keep events at or after (RFC 3339).
    since_ts: str | None = None
    #: Keep events before (RFC 3339).
    until_ts: str | None = None
    #: The paging cursor: the previous page's ``next_cursor_line_offset``.
    until_line_offset: int | None = None
    #: The event action.
    action: str | None = None
    #: The event category.
    category: str | None = None
    #: The event outcome.
    outcome: str | None = None
    #: The minimum severity number.
    severity_min: int | None = None
    #: The trace id.
    trace_id: str | None = None
    #: Free text.
    q: str | None = None
    #: Leave out the daemon's internal events.
    hide_internal: bool = False
    #: The page size (gateway default 200).
    limit: int | None = None
    #: Exact matches on attribution fields (``agent_alias``, ``channel``,
    #: ``session_key``, ``tool``, …).
    attributes: dict[str, str] | None = None

    def _query(self) -> Query:
        """Return the query string of the filters that are set."""
        query: dict[str, str | int | bool | None] = {
            "since_ts": self.since_ts or None,
            "until_ts": self.until_ts or None,
            "action": self.action or None,
            "category": self.category or None,
            "outcome": self.outcome or None,
            "trace_id": self.trace_id or None,
            "q": self.q or None,
            "until_line_offset": self.until_line_offset,
            "severity_min": self.severity_min or None,
            "limit": self.limit or None,
            "hide_internal": True if self.hide_internal else None,
        }
        query.update(self.attributes or {})
        return query


class LogPage(Model):
    """A page of :meth:`SystemAPI.logs`."""

    #: The log events (OpenTelemetry-like JSON, see ZeroClaw's ``LogEvent``).
    events: list[Any]
    #: The cursor for the next (older) page.
    next_cursor_line_offset: int | None = None
    #: Whether this is the oldest page.
    at_end: bool
    #: When the daemon started.
    daemon_started_at: str
    #: The attribution fields that can be filtered on.
    attribution_keys: list[str] | None = None


class VersionCheck(Model):
    """The answer of :meth:`SystemAPI.version_check`."""

    #: The running version.
    current_version: str
    #: The latest release (``None`` when the check failed).
    latest_version: str | None = None
    #: Whether the latest is newer.
    is_newer: bool
    #: The release page.
    release_url: str | None = None
    #: The release notes (Markdown).
    release_notes: str | None = None
    #: The release date.
    published_at: str | None = None
    #: Why the check failed.
    error: str | None = None


class UpgradeStatus(Model):
    """The progress of a self-upgrade."""

    #: ``idle``, ``running``, ``done``, ``restarting`` or ``failed``.
    state: str
    #: The upgrade id.
    handoff_id: str | None = None
    #: The step, 0 to 6.
    phase: int | None = None
    #: The last log lines.
    log_tail: list[str] | None = None
    #: The version before.
    previous_version: str | None = None
    #: The version being installed.
    target_version: str | None = None
    #: How the daemon restarts.
    restart_mode: str | None = None
    #: How to restart it by hand.
    restart_hint: str | None = None
    #: Why it failed.
    error: str | None = None


class AdminResponse(Model):
    """The answer of the ``/admin`` actions."""

    #: Whether it was accepted.
    success: bool
    #: What happens next.
    message: str


class SystemAPI:
    """The gateway-wide endpoints, from :attr:`Client.system`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def health(self) -> Health:
        """Return liveness and component health (GET /health). Public."""
        return await self._c._call("GET", ["health"], Health)

    async def runtime_health(self) -> HealthSnapshot:
        """Return the runtime's component health (GET /api/health)."""
        return await self._c._field("GET", ["api", "health"], "health", HealthSnapshot)

    async def metrics(self) -> str:
        """Return the Prometheus text exposition (GET /metrics). Public."""
        return await self._c._text("GET", ["metrics"])

    async def status(self, agent: str | None = None) -> Status:
        """Return the version, model, channels, nodes and process figures (GET /api/status).

        With ``agent``, that agent's model.
        """
        return await self._c._call("GET", ["api", "status"], Status, query={"agent": agent or None})

    async def doctor(self) -> DoctorReport:
        """Run the configuration diagnostics (POST /api/doctor)."""
        return await self._c._call("POST", ["api", "doctor"], DoctorReport)

    async def tools(self, agent: str | None = None) -> builtins.list[ToolSpec]:
        """Return the tools ``agent`` (all of them when ``None``) can call (GET /api/tools)."""
        return await self._c._field(
            "GET", ["api", "tools"], "tools", list[ToolSpec], query={"agent": agent or None}
        )

    async def tool_param_options(
        self, domain: str, agent: str | None = None, args: Any = None
    ) -> builtins.list[ToolOption]:
        """Return the values a tool parameter of ``domain`` accepts.

        POST /api/tools/param-options. ``domain`` is ``channel_refs``,
        ``peer_targets``, ``peer_groups``, ``agent_aliases``, ``tool_names``
        or ``memory_categories``; ``args`` holds the sibling arguments the
        options depend on. A missing ``agent`` or ``args`` is sent as null.
        """
        payload = {"domain": domain, "agent": agent or None, "args": args}
        return await self._c._field(
            "POST",
            ["api", "tools", "param-options"],
            "options",
            list[ToolOption],
            json_body=payload,
        )

    async def integrations(self) -> builtins.list[Integration]:
        """Return the integrations this build offers (GET /api/integrations)."""
        return await self._c._field(
            "GET", ["api", "integrations"], "integrations", list[Integration]
        )

    async def integration_settings(self) -> dict[str, IntegrationSetting]:
        """Return each integration's state, by name (GET /api/integrations/settings)."""
        return await self._c._field(
            "GET",
            ["api", "integrations", "settings"],
            "settings",
            dict[str, IntegrationSetting],
        )

    async def cli_tools(self) -> builtins.list[CLITool]:
        """Return the command-line tools found on the host's PATH (GET /api/cli-tools).

        Slow: the gateway runs each with ``--version``.
        """
        return await self._c._field("GET", ["api", "cli-tools"], "cli_tools", list[CLITool])

    async def tuis(self) -> builtins.list[Tui]:
        """Return the terminal clients connected to the daemon (GET /api/tuis)."""
        return await self._c._field("GET", ["api", "tuis"], "tuis", list[Tui])

    async def logs(self, filter: LogQuery | None = None) -> LogPage:
        """Return a page of structured log events, newest first (GET /api/logs).

        Continue with ``until_line_offset`` set to the page's
        ``next_cursor_line_offset``.
        """
        query = (filter or LogQuery())._query()
        return await self._c._call("GET", ["api", "logs"], LogPage, query=query)

    async def version_check(self, force: bool = False, version: str | None = None) -> VersionCheck:
        """Report whether a newer release exists (GET /api/version/check).

        ``force`` skips the gateway's one-hour cache; ``version`` checks that
        one tag.
        """
        query = {"force": True if force else None, "version": version or None}
        return await self._c._call("GET", ["api", "version", "check"], VersionCheck, query=query)

    async def upgrade(self, version: str | None = None, auto_restart: bool = False) -> str:
        """Start a self-upgrade and return the handoff id (POST /api/version/upgrade).

        Installs ``version``, or the latest release when ``None``; follow it
        with :meth:`upgrade_status`. Needs ``gateway.allow_self_upgrade``.
        """
        payload = {"version": version or None, "auto_restart": auto_restart}
        return await self._c._field(
            "POST", ["api", "version", "upgrade"], "handoff_id", str, json_body=payload
        )

    async def upgrade_status(self, handoff_id: str | None = None) -> UpgradeStatus:
        """Return the progress of an upgrade, the latest when ``handoff_id`` is ``None``.

        GET /api/version/upgrade/status.
        """
        return await self._c._call(
            "GET",
            ["api", "version", "upgrade", "status"],
            UpgradeStatus,
            query={"handoff_id": handoff_id or None},
        )

    async def reload(self) -> AdminResponse:
        """Restart the daemon's subsystems from the configuration on disk (POST /admin/reload).

        The connection drops shortly after; reconnect. Allowed from loopback,
        or remotely with ``gateway.allow_remote_admin``.
        """
        return await self._c._call("POST", ["admin", "reload"], AdminResponse)

    async def shutdown(self) -> AdminResponse:
        """Stop the gateway (POST /admin/shutdown). Loopback only."""
        return await self._c._call("POST", ["admin", "shutdown"], AdminResponse)

    async def openapi(self) -> Any:
        """Return the gateway's OpenAPI document (GET /api/openapi.json). Public.

        It covers the configuration, version, SOP and skill routes.
        """
        return await self._c._json("GET", ["api", "openapi.json"])
