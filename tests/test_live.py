"""Read-only calls against a real gateway, to check that every type decodes what it sends.

Selected only with the live marker::

    ZEROCLAW_URL=http://127.0.0.1:42617 ZEROCLAW_TOKEN=zc_… \\
      pytest -m live tests/test_live.py

Optional: ZEROCLAW_AGENT (an agent alias) adds the per-agent reads. Nothing
is written. Calls a build may not offer (features off, SOPs disabled, a
channel not running) are reported, not failed.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from functools import partial

import pytest

from zeroclaw_client import APIError, Client, LogQuery

pytestmark = pytest.mark.live


@pytest.fixture
async def live_client() -> AsyncIterator[Client]:
    url, token = os.environ.get("ZEROCLAW_URL", ""), os.environ.get("ZEROCLAW_TOKEN", "")
    if not url or not token:
        pytest.skip("set ZEROCLAW_URL and ZEROCLAW_TOKEN")
    async with Client(url, token=token) as c:
        yield c


async def test_live_every_read_decodes(live_client: Client) -> None:
    client = live_client
    failures: list[str] = []

    async def check(what: str, call: Callable[[], Awaitable[object]]) -> None:
        # A decode or transport error fails; a refusal by the gateway (a route
        # or feature it does not offer) is only reported.
        try:
            await call()
        except APIError as exc:
            print(f"refused {what}: {exc.status} {exc}")
        except Exception as exc:
            failures.append(f"{what}: {exc!r}")
        else:
            print(f"ok      {what}")

    system, config = client.system, client.config
    await check("health", system.health)
    await check("runtime_health", system.runtime_health)
    await check("metrics", system.metrics)
    await check("status", system.status)
    await check("tools", system.tools)
    await check("integrations", system.integrations)
    await check("integration_settings", system.integration_settings)
    await check("tuis", system.tuis)
    await check("logs", lambda: system.logs(LogQuery()))
    await check("upgrade_status", system.upgrade_status)

    await check("config.snapshot", config.snapshot)
    await check("config.get", lambda: config.get("gateway.port"))
    await check("config.list", lambda: config.list("gateway"))
    await check("config.drift", config.drift)
    await check("config.pending_reload", config.pending_reload)
    await check("config.templates", config.templates)
    await check("config.map_keys", lambda: config.map_keys("agents"))
    await check("config.catalog", config.catalog)
    await check("config.status", config.status)
    await check("config.agent_options", config.agent_options)
    await check("config.sections", config.sections)

    await check("pairing.devices", client.pairing.devices)
    await check("cron.list", client.cron.list)
    await check("cron.settings", client.cron.settings)
    await check("memory.search", client.memory.search)
    await check("cost.summary", client.cost.summary)
    await check("sessions.running", client.sessions.running)
    await check("events.history", client.events.history)
    await check("files.list", client.files.list)
    await check("skills.bundles", client.skills.bundles)
    await check("skills.slash_option_kinds", client.skills.slash_option_kinds)
    await check("sops.list", client.sops.list)
    await check("sops.runs", client.sops.runs)
    await check("canvas.list", client.canvas.list)
    await check("quickstart.state", client.quickstart.state)

    for ch in await client.channels.list():
        try:
            rooms = await client.channels.rooms(ch.name)
        except Exception:
            continue
        print(f"ok      rooms of {ch.name}: {len(rooms)}")
        if rooms:
            members = partial(client.channels.room_members, ch.name, rooms[0].id)
            await check("room_members", members)

    sessions = await client.sessions.list()
    if sessions:
        first = sessions[0]
        sid = first.session_key if first.session_key is not None else first.session_id
        await check("sessions.messages", lambda: client.sessions.messages(sid))
        await check("sessions.state", lambda: client.sessions.state(sid))

    alias = os.environ.get("ZEROCLAW_AGENT", "")
    if alias:
        agent = client.agent(alias)
        await check("agent.list_files", agent.list_files)
        await check("agent.personality_files", agent.personality_files)
        await check("agent.personality", lambda: agent.personality("SOUL.md"))
        await check("agent.skills", agent.skills)
        await check("system.tools(agent)", lambda: system.tools(alias))
        await check("cost.agent", lambda: client.cost.agent(alias))

    assert not failures, failures
