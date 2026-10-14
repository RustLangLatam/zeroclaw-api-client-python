from __future__ import annotations

from typing import Any

import httpx
import pytest

from zeroclaw_client import Client
from zeroclaw_client.system import LogQuery, SystemAPI

from .conftest import Gateway, body, reply

SNAPSHOT = {
    "pid": 7,
    "updated_at": "t",
    "uptime_seconds": 60,
    "components": {
        "gateway": {
            "status": "ok",
            "updated_at": "t",
            "last_ok": "t",
            "last_error": None,
            "restart_count": 0,
        }
    },
}


async def test_health_and_metrics_are_public(gateway: Gateway, client: Client) -> None:
    gateway.on(
        "GET",
        "/health",
        {"status": "ok", "paired": True, "require_pairing": True, "runtime": SNAPSHOT},
        public=True,
    )
    gateway.on("GET", "/metrics", reply("# HELP x\nx 1\n"), public=True)
    gateway.on("GET", "/api/health", {"health": SNAPSHOT})

    system = SystemAPI(client)
    assert (await system.health()).require_pairing
    assert "x 1" in await system.metrics()
    assert (await system.runtime_health()).components["gateway"].status == "ok"


async def test_status_asks_about_one_agent(gateway: Gateway, client: Client) -> None:
    def status(request: httpx.Request) -> httpx.Response:
        assert request.url.params["agent"] == "helper"
        return reply(
            {
                "version": "0.8.5",
                "model_provider": "openai.default",
                "model": "m",
                "temperature": 0.7,
                "uptime_seconds": 1,
                "daemon_started_at": "t",
                "gateway_port": 42617,
                "locale": "en",
                "memory_backend": "sqlite",
                "paired": True,
                "channels": {"whatsapp.main": True},
                "nodes": {"connected": [], "mdns_peers": []},
                "health": SNAPSHOT,
                "agent_alias": "helper",
                "process": {
                    "rss_bytes": 1,
                    "system_ram_total_bytes": 2,
                    "cpu_percent": None,
                    "num_cpus": 4,
                },
                "check_updates": True,
                "allow_self_upgrade": False,
                "restart_mode": "manual",
                "restart_hint": "",
                "live_channel_config": ["sender_routes"],
            }
        )(request)

    gateway.on("GET", "/api/status", status)
    got = await SystemAPI(client).status("helper")
    assert got.agent_alias == "helper"
    assert got.live_channel_config == ["sender_routes"]
    assert got.process is not None
    assert got.process.num_cpus == 4


async def test_diagnoses_and_lists_tools_and_integrations(gateway: Gateway, client: Client) -> None:
    def tools(request: httpx.Request) -> httpx.Response:
        assert "agent" not in request.url.params
        return reply(
            {"tools": [{"name": "shell", "description": "d", "parameters": {"type": "object"}}]}
        )(request)

    def options(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"domain": "channel_refs", "agent": None, "args": None}
        return reply({"options": [{"value": "whatsapp.main"}]})(request)

    gateway.on(
        "POST",
        "/api/doctor",
        {
            "results": [{"severity": "warn", "category": "memory", "message": "m"}],
            "summary": {"ok": 0, "warnings": 1, "errors": 0},
        },
    )
    gateway.on("GET", "/api/tools", tools)
    gateway.on("POST", "/api/tools/param-options", options)
    gateway.on(
        "GET",
        "/api/integrations",
        {
            "integrations": [
                {
                    "name": "WhatsApp",
                    "description": "d",
                    "category": "Chat",
                    "category_label": "Chat Providers",
                    "status": "Active",
                }
            ]
        },
    )
    gateway.on(
        "GET",
        "/api/integrations/settings",
        {"settings": {"WhatsApp": {"enabled": True, "category": "Chat", "status": "Active"}}},
    )
    gateway.on(
        "GET",
        "/api/cli-tools",
        {
            "cli_tools": [
                {
                    "name": "git",
                    "path": "/usr/bin/git",
                    "version": "2",
                    "category": "VersionControl",
                }
            ]
        },
    )
    gateway.on("GET", "/api/tuis", {"tuis": []})

    system = SystemAPI(client)
    assert (await system.doctor()).summary.warnings == 1
    assert (await system.tools())[0].name == "shell"
    assert (await system.tool_param_options("channel_refs"))[0].value == "whatsapp.main"
    assert (await system.integrations())[0].status == "Active"
    assert (await system.integration_settings())["WhatsApp"].enabled
    assert (await system.cli_tools())[0].name == "git"
    assert await system.tuis() == []


async def test_tool_param_options_sends_agent_and_args(gateway: Gateway, client: Client) -> None:
    def options(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"domain": "peer_targets", "agent": "helper", "args": {"c": 1}}
        return reply({"options": [{"value": "v", "label": "L", "hint": "h"}]})(request)

    gateway.on("POST", "/api/tools/param-options", options)
    got = await SystemAPI(client).tool_param_options("peer_targets", "helper", {"c": 1})
    assert got[0].label == "L"


@pytest.mark.parametrize(
    ("filter", "want"),
    [
        (LogQuery(), {}),
        (LogQuery(since_ts="", limit=0, severity_min=0, hide_internal=False), {}),
        (LogQuery(until_line_offset=0), {"until_line_offset": "0"}),
        (
            LogQuery(
                until_line_offset=40,
                limit=10,
                hide_internal=True,
                attributes={"agent_alias": "helper"},
            ),
            {
                "until_line_offset": "40",
                "limit": "10",
                "hide_internal": "true",
                "agent_alias": "helper",
            },
        ),
        (
            LogQuery(
                since_ts="a",
                until_ts="b",
                action="c",
                category="d",
                outcome="e",
                severity_min=9,
                trace_id="f",
                q="g",
            ),
            {
                "since_ts": "a",
                "until_ts": "b",
                "action": "c",
                "category": "d",
                "outcome": "e",
                "severity_min": "9",
                "trace_id": "f",
                "q": "g",
            },
        ),
    ],
)
async def test_log_filters_become_query_parameters(
    gateway: Gateway, client: Client, filter: LogQuery, want: dict[str, str]
) -> None:
    def logs(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == want
        return reply(
            {
                "events": [{"@timestamp": "t"}],
                "next_cursor": None,
                "next_cursor_line_offset": 30,
                "at_end": False,
                "daemon_started_at": "t",
                "attribution_keys": ["agent_alias"],
            }
        )(request)

    gateway.on("GET", "/api/logs", logs)
    page = await SystemAPI(client).logs(filter)
    assert page.next_cursor_line_offset == 30
    assert page.events == [{"@timestamp": "t"}]


async def test_checks_and_runs_upgrades(gateway: Gateway, client: Client) -> None:
    def check(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"force": "true"}
        return reply({"current_version": "0.8.5", "latest_version": "0.8.6", "is_newer": True})(
            request
        )

    def upgrade(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"version": None, "auto_restart": True}
        return reply({"handoff_id": "h1"}, status=202)(request)

    def status(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"handoff_id": "h1"}
        return reply({"state": "running", "phase": 2})(request)

    gateway.on("GET", "/api/version/check", check)
    gateway.on("POST", "/api/version/upgrade", upgrade)
    gateway.on("GET", "/api/version/upgrade/status", status)

    system = SystemAPI(client)
    assert (await system.version_check(force=True)).is_newer
    assert await system.upgrade(auto_restart=True) == "h1"
    assert (await system.upgrade_status("h1")).phase == 2


async def test_upgrade_to_a_version_sends_it(gateway: Gateway, client: Client) -> None:
    def check(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"version": "v0.9.0"}
        return reply({"current_version": "0.8.5", "is_newer": False})(request)

    def upgrade(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"version": "v0.9.0", "auto_restart": False}
        return reply({"handoff_id": "h2"})(request)

    def status(request: httpx.Request) -> httpx.Response:
        assert not request.url.params
        return reply({"state": "idle"})(request)

    gateway.on("GET", "/api/version/check", check)
    gateway.on("POST", "/api/version/upgrade", upgrade)
    gateway.on("GET", "/api/version/upgrade/status", status)

    system = SystemAPI(client)
    assert (await system.version_check(version="v0.9.0")).latest_version is None
    assert await system.upgrade("v0.9.0") == "h2"
    assert (await system.upgrade_status()).state == "idle"


async def test_administers_the_daemon(gateway: Gateway, client: Client) -> None:
    gateway.on("POST", "/admin/reload", {"success": True, "message": "Daemon reload initiated"})
    gateway.on(
        "POST", "/admin/shutdown", {"success": True, "message": "Gateway shutdown initiated"}
    )
    gateway.on("GET", "/api/openapi.json", {"openapi": "3.1.0"}, public=True)

    system = SystemAPI(client)
    assert (await system.reload()).success
    assert (await system.shutdown()).success
    doc: Any = await system.openapi()
    assert doc == {"openapi": "3.1.0"}
