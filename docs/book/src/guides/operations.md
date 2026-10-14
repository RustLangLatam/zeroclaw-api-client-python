# Cron, memory and cost

## Cron jobs

A job runs a shell command or an agent prompt on a schedule and can deliver
its output to a channel:

```python
from zeroclaw_client import Delivery, NewCronJob

job = await client.cron.create(
    NewCronJob(
        agent="helper",
        schedule="0 9 * * 1-5",
        tz="Europe/Madrid",
        prompt="Summarize yesterday's orders",
        delivery=Delivery.announce("whatsapp.main", "+34600000000"),
    )
)
result = await client.cron.run(job.id)  # runs it now and waits
print(result.success, result.output)
```

`update` changes a job (pause with `CronJobPatch(enabled=False)`), `runs`
lists its history, and `settings` / `update_settings` cover the scheduler.
Fields left as `None` are not sent.

A shell job with `shell_output_format="raw"` and a `delivery` announces its
output verbatim: a way to post a fixed message (or a `[DOCUMENT:…]` marker)
on a channel through an agent's channel binding (`examples/announce.py`).

## Memory

`client.memory.search(query=..., category=..., since=..., until=...)`
recalls entries by text or time (at most 50), or lists a category; `store`
and `forget` write. Each agent can have its own memory (`agent=`) besides
the shared one.

## Cost

`client.cost.summary(from_, to)` returns tokens, calls and USD in a window,
by model and by agent; `client.cost.agent(alias)` an agent's session and
daily figures. Models without known rates count as free unless their prices
are configured.

## The gateway itself

`client.system` covers health (`health`, public), `status`, Prometheus
`metrics`, `doctor`, `tools`, `integrations`, host `cli_tools`, connected
terminal clients (`tuis`), paged structured `logs`, version checks
(`version_check`) and self-upgrades (`upgrade`, `upgrade_status`), and the
daemon's `reload` and `shutdown`.
