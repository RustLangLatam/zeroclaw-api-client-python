from __future__ import annotations

import httpx
import pytest
from pydantic import TypeAdapter

from zeroclaw_client import (
    AtSchedule,
    Client,
    CronJob,
    CronJobPatch,
    CronSchedule,
    CronSettingsPatch,
    Delivery,
    EverySchedule,
    NewCronJob,
    Schedule,
)

from .conftest import Gateway, body, reply

SCHEDULES = TypeAdapter(Schedule)


@pytest.mark.parametrize(
    ("wire", "want"),
    [
        ({"kind": "cron", "expr": "0 9 * * *", "tz": None}, CronSchedule(expr="0 9 * * *")),
        (
            {"kind": "cron", "expr": "*/5 * * * *", "tz": "America/Bogota"},
            CronSchedule(expr="*/5 * * * *", tz="America/Bogota"),
        ),
        ({"kind": "at", "at": "2026-10-14T08:00:00Z"}, AtSchedule(at="2026-10-14T08:00:00Z")),
        ({"kind": "every", "every_ms": 60000}, EverySchedule(every_ms=60_000)),
    ],
)
def test_schedule_vectors(wire: dict[str, object], want: Schedule) -> None:
    assert SCHEDULES.validate_python(wire) == want
    # Encoding gives back the gateway's JSON.
    assert SCHEDULES.dump_python(want, mode="json") == wire


def test_unknown_schedule_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="kind"):
        SCHEDULES.validate_python({"kind": "weekly"})


def test_delivery_vectors() -> None:
    announce = Delivery.announce("whatsapp.main", "+34600000000")
    assert announce.model_dump(exclude_none=True) == {
        "mode": "announce",
        "channel": "whatsapp.main",
        "to": "+34600000000",
        "best_effort": True,
    }
    lean = Delivery.model_validate({"mode": "none"})
    assert lean.best_effort
    assert lean.channel is None


JOB = {
    "id": "j1",
    "expression": "0 9 * * *",
    "schedule": {"kind": "cron", "expr": "0 9 * * *", "tz": None},
    "command": "echo hi",
    "prompt": None,
    "name": None,
    "job_type": "shell",
    "session_target": "isolated",
    "model": None,
    "agent_alias": "helper",
    "enabled": True,
    "delivery": {
        "mode": "announce",
        "channel": "whatsapp.main",
        "to": "+34600000000",
        "best_effort": True,
    },
    "delete_after_run": False,
    "uses_memory": True,
    "source": "imperative",
    "shell_output_format": "raw",
    "created_at": "t",
    "next_run": "t",
    "last_run": None,
    "last_status": None,
    "last_output": None,
}


def test_jobs_decode_from_the_gateways_json() -> None:
    job = CronJob.model_validate(
        {
            **JOB,
            "schedule": {"kind": "cron", "expr": "0 9 * * 1-5", "tz": "Europe/Madrid"},
            "prompt": "Daily summary",
            "job_type": "agent",
        }
    )
    assert job.schedule == CronSchedule(expr="0 9 * * 1-5", tz="Europe/Madrid")
    assert job.delivery.channel == "whatsapp.main"


async def test_creates_runs_and_removes_a_job(gateway: Gateway, client: Client) -> None:
    def create(request: httpx.Request) -> httpx.Response:
        assert body(request) == {
            "agent": "helper",
            "schedule": "0 9 * * *",
            "command": "echo hi",
            "delivery": {
                "mode": "announce",
                "channel": "whatsapp.main",
                "to": "+34600000000",
                "best_effort": True,
            },
            "shell_output_format": "raw",
        }
        return httpx.Response(200, json={"status": "ok", "job": JOB})

    def runs(request: httpx.Request) -> httpx.Response:
        assert request.url.params["limit"] == "5"
        return httpx.Response(
            200,
            json={
                "runs": [
                    {
                        "id": 1,
                        "job_id": "j1",
                        "started_at": "t",
                        "finished_at": "t",
                        "status": "ok",
                        "output": "hi",
                        "duration_ms": 5,
                    }
                ]
            },
        )

    def patch(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"enabled": False}
        return httpx.Response(200, json={"status": "ok", "job": JOB})

    def run(request: httpx.Request) -> httpx.Response:
        # A manual run waits longer than the client's timeout.
        assert request.extensions["zeroclaw_timeout"] == 660.0
        return httpx.Response(
            200,
            json={
                "status": "ok",
                "job_id": "j1",
                "success": True,
                "output": "hi",
                "duration_ms": 5,
                "started_at": "t",
                "finished_at": "t",
            },
        )

    gateway.on("POST", "/api/cron", create)
    gateway.on("POST", "/api/cron/j1/run", run)
    gateway.on("GET", "/api/cron/j1/runs", runs)
    gateway.on("PATCH", "/api/cron/j1", patch)
    gateway.on("DELETE", "/api/cron/j1", {"status": "ok"})
    gateway.on("GET", "/api/cron", {"jobs": [JOB]})

    created = await client.cron.create(
        NewCronJob(
            agent="helper",
            schedule="0 9 * * *",
            command="echo hi",
            delivery=Delivery.announce("whatsapp.main", "+34600000000"),
            shell_output_format="raw",
        )
    )
    assert created.id == "j1"
    assert (await client.cron.run("j1")).output == "hi"
    assert len(await client.cron.runs("j1", 5)) == 1
    await client.cron.update("j1", CronJobPatch(enabled=False))
    await client.cron.delete("j1")
    assert len(await client.cron.list()) == 1


async def test_scheduler_settings(gateway: Gateway, client: Client) -> None:
    gateway.on(
        "GET",
        "/api/cron/settings",
        {"enabled": True, "catch_up_on_startup": False, "max_run_history": 50},
    )

    def update(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"max_run_history": 10}
        return reply(
            {"status": "ok", "enabled": True, "catch_up_on_startup": False, "max_run_history": 10}
        )(request)

    gateway.on("PATCH", "/api/cron/settings", update)
    assert (await client.cron.settings()).max_run_history == 50
    updated = await client.cron.update_settings(CronSettingsPatch(max_run_history=10))
    assert updated.max_run_history == 10
