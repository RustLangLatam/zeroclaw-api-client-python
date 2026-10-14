# First calls

```python
import asyncio
import os

from zeroclaw_client import Client


async def main() -> None:
    async with Client("http://127.0.0.1:42617", token=os.environ.get("ZEROCLAW_TOKEN")) as client:
        # Public: no token needed.
        health = await client.system.health()
        print(health.status)

        # Version, model, channels and process figures.
        status = await client.system.status()
        print(status.version, status.model)

        # Every configured channel and its state.
        for channel in await client.channels.list():
            print(channel.name, channel.status, channel.health)

        # One configuration field.
        port = await client.config.get("gateway.port")
        print(port.value)


asyncio.run(main())
```

Use the client as an async context manager, or call `await client.aclose()`
when done: it owns a connection pool. One client is meant to be shared by
every task of an application.

## Timeouts and retries

A request waits 60 seconds for the gateway's answer unless `timeout=` says
otherwise; a manual cron run waits up to 660, as the gateway allows it 600.
The timeout bounds the answer's headers only, so the live event stream is
never cut, and an `asyncio.timeout` of your own bounds the whole call.
Failed idempotent requests are retried three times with backoff. See
[Resilience](../guides/resilience.md).

## Examples

The repository ships runnable scripts under `examples/`:

| Example | Shows |
|---|---|
| `status.py` | version, model and channels |
| `pairing.py` | exchanging a pairing code for a token |
| `config.py` | reading fields, listing agents, an atomic patch |
| `group_chats.py` | channels, their group chats and members |
| `events.py` | following the live event stream, reconnecting |
| `chat.py` | streaming an agent's reply over the WebSocket |
| `announce.py` | posting on a channel through a one-off cron job |
| `resilient.py` | timeouts, retries, rate limit, circuit breaker, concurrency limit and a custom middleware |

```sh
ZEROCLAW_URL=http://127.0.0.1:42617 ZEROCLAW_TOKEN=zc_… \
  python examples/status.py
ZEROCLAW_URL=… ZEROCLAW_TOKEN=… python examples/chat.py helper "Hello"
```
