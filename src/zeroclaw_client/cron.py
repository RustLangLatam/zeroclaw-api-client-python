"""Scheduled jobs: shell commands or agent prompts on a cron schedule.

Their results are delivered to a channel.

Gateway handlers: ``crates/zeroclaw-gateway/src/api.rs`` (``/api/cron*``);
types in ``crates/zeroclaw-runtime/src/cron/types.rs``.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = [
    "AtSchedule",
    "CronAPI",
    "CronJob",
    "CronJobPatch",
    "CronRun",
    "CronRunResult",
    "CronSchedule",
    "CronSettings",
    "CronSettingsPatch",
    "Delivery",
    "EverySchedule",
    "NewCronJob",
    "Schedule",
]

#: How long a manual run may take, in seconds: the gateway allows 600 s.
CRON_LONG_RUN = 660.0


class CronSchedule(Model):
    """Run on a cron expression, in a time zone (UTC when ``None``)."""

    kind: Literal["cron"] = "cron"
    #: The cron expression.
    expr: str
    #: The IANA time zone (``None``: UTC).
    tz: str | None = None


class AtSchedule(Model):
    """Run once, at a time (RFC 3339)."""

    kind: Literal["at"] = "at"
    #: The time (RFC 3339).
    at: str


class EverySchedule(Model):
    """Run every ``every_ms`` milliseconds."""

    kind: Literal["every"] = "every"
    #: The interval, in milliseconds.
    every_ms: int


#: When a job runs, told apart by ``kind``.
Schedule = Annotated[CronSchedule | AtSchedule | EverySchedule, Field(discriminator="kind")]


class Delivery(Model):
    """Where a job's output goes."""

    #: ``none`` or ``announce`` (post it on a channel).
    mode: str = "none"
    #: The channel, as ``type.alias``.
    channel: str | None = None
    #: The recipient on the channel.
    to: str | None = None
    #: The thread to post in.
    thread_id: str | None = None
    #: Whether a delivery failure leaves the run successful.
    best_effort: bool = True

    @classmethod
    def announce(cls, channel: str, to: str) -> Delivery:
        """Post the output to ``to`` on ``channel`` (``type.alias``)."""
        return cls(mode="announce", channel=channel, to=to)


class CronJob(Model):
    """A scheduled job."""

    #: The job id.
    id: str
    #: The schedule expression as written.
    expression: str
    #: The parsed schedule.
    schedule: Schedule
    #: The shell command (shell jobs).
    command: str = ""
    #: The prompt (agent jobs).
    prompt: str | None = None
    #: The name.
    name: str | None = None
    #: ``shell`` or ``agent``.
    job_type: str
    #: ``isolated`` or ``main``.
    session_target: str
    #: The model override (agent jobs).
    model: str | None = None
    #: The agent that owns it.
    agent_alias: str
    #: Whether it runs.
    enabled: bool
    #: Where its output goes.
    delivery: Delivery
    #: Whether it is deleted after one run.
    delete_after_run: bool
    #: The tools an agent job may use (``None``: no restriction).
    allowed_tools: list[str] | None = None
    #: Whether an agent job uses memory.
    uses_memory: bool = True
    #: ``imperative`` (API, CLI) or ``declarative`` (config file).
    source: str = ""
    #: ``wrapped`` or ``raw`` (shell jobs).
    shell_output_format: str | None = None
    #: The creation time (RFC 3339).
    created_at: str
    #: The next run (RFC 3339).
    next_run: str
    #: The last run (RFC 3339).
    last_run: str | None = None
    #: The last status.
    last_status: str | None = None
    #: The last output.
    last_output: str | None = None


class NewCronJob(Model):
    """A job to create.

    Shell jobs need ``command``; agent jobs ``prompt`` (and ``job_type``
    ``agent``, implied by a prompt). ``None`` fields are left out.
    """

    #: The owning agent (must be configured).
    agent: str
    #: The cron expression.
    schedule: str
    #: The name.
    name: str | None = None
    #: The IANA time zone of the schedule.
    tz: str | None = None
    #: The shell command.
    command: str | None = None
    #: ``shell`` or ``agent``.
    job_type: str | None = None
    #: The agent prompt.
    prompt: str | None = None
    #: Where the output goes.
    delivery: Delivery | None = None
    #: ``isolated`` (default) or ``main``.
    session_target: str | None = None
    #: The model override.
    model: str | None = None
    #: The tools an agent job may use (``None``: no restriction; ``[]``: none).
    allowed_tools: list[str] | None = None
    #: Delete the job after its first run.
    delete_after_run: bool | None = None
    #: Whether an agent job uses memory (default true).
    uses_memory: bool | None = None
    #: ``wrapped`` (default) or ``raw``: how a shell job's output is announced.
    shell_output_format: str | None = None


class CronJobPatch(Model):
    """Changes to a job; ``None`` leaves a field as it is."""

    #: The owning agent; required when changing a shell job's command.
    agent: str | None = None
    #: The name.
    name: str | None = None
    #: The cron expression.
    schedule: str | None = None
    #: The IANA time zone.
    tz: str | None = None
    #: Remove the time zone.
    clear_tz: bool | None = None
    #: The shell command (or an agent job's prompt).
    command: str | None = None
    #: The agent prompt.
    prompt: str | None = None
    #: Pause (false) or resume the job.
    enabled: bool | None = None
    #: Whether an agent job uses memory.
    uses_memory: bool | None = None
    #: ``wrapped`` or ``raw``.
    shell_output_format: str | None = None


class CronRunResult(Model):
    """The result of :meth:`CronAPI.run`."""

    #: The run status.
    status: str
    #: The job id.
    job_id: str
    #: Whether the job succeeded.
    success: bool
    #: Its output.
    output: str
    #: The duration, in milliseconds.
    duration_ms: int
    #: The start (RFC 3339).
    started_at: str
    #: The end (RFC 3339).
    finished_at: str


class CronRun(Model):
    """A recorded run."""

    #: The run id.
    id: int
    #: The job id.
    job_id: str
    #: The start (RFC 3339).
    started_at: str
    #: The end (RFC 3339).
    finished_at: str
    #: The status.
    status: str
    #: The output.
    output: str | None = None
    #: The duration, in milliseconds.
    duration_ms: int | None = None


class CronSettings(Model):
    """The scheduler settings."""

    #: Whether the scheduler runs jobs.
    enabled: bool
    #: Whether missed runs run at startup.
    catch_up_on_startup: bool
    #: The number of runs kept per job.
    max_run_history: int


class CronSettingsPatch(Model):
    """Changes to the scheduler settings; ``None`` leaves a setting as it is."""

    #: Whether the scheduler runs jobs.
    enabled: bool | None = None
    #: Whether missed runs run at startup.
    catch_up_on_startup: bool | None = None
    #: The number of runs kept per job.
    max_run_history: int | None = None


class CronAPI:
    """The scheduled jobs endpoints (``/api/cron``), from :attr:`Client.cron`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def list(self) -> builtins.list[CronJob]:
        """Return every job (GET /api/cron)."""
        return await self._c._field("GET", ["api", "cron"], "jobs", list[CronJob])

    async def create(self, job: NewCronJob) -> CronJob:
        """Create a job (POST /api/cron)."""
        return await self._c._field("POST", ["api", "cron"], "job", CronJob, json_body=job)

    async def update(self, id: str, patch: CronJobPatch) -> CronJob:
        """Change a job; unset fields stay as they are (PATCH /api/cron/{id})."""
        return await self._c._field("PATCH", ["api", "cron", id], "job", CronJob, json_body=patch)

    async def delete(self, id: str) -> None:
        """Delete a job (DELETE /api/cron/{id})."""
        await self._c._request("DELETE", ["api", "cron", id])

    async def run(self, id: str) -> CronRunResult:
        """Run a job now and wait for it (POST /api/cron/{id}/run).

        The gateway allows up to its long-running timeout, 600 s by default.
        A failed job still raises nothing, with ``success`` false.
        """
        return await self._c._call(
            "POST", ["api", "cron", id, "run"], CronRunResult, timeout=CRON_LONG_RUN
        )

    async def runs(self, id: str, limit: int | None = None) -> builtins.list[CronRun]:
        """Return the job's latest runs (GET /api/cron/{id}/runs).

        ``limit`` is 1 to 100, or ``None`` for the gateway's default, 20.
        """
        return await self._c._field(
            "GET", ["api", "cron", id, "runs"], "runs", list[CronRun], query={"limit": limit}
        )

    async def settings(self) -> CronSettings:
        """Return the scheduler settings (GET /api/cron/settings)."""
        return await self._c._call("GET", ["api", "cron", "settings"], CronSettings)

    async def update_settings(self, settings: CronSettingsPatch) -> CronSettings:
        """Change the scheduler settings that are set; saved to the configuration.

        PATCH /api/cron/settings.
        """
        return await self._c._call(
            "PATCH", ["api", "cron", "settings"], CronSettings, json_body=settings
        )
