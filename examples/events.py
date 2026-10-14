"""Follow the live event stream, reconnecting when the gateway restarts. Stop with Ctrl-C."""

import asyncio
import contextlib
import json
import os

from zeroclaw_client import Client, DecodeError, EventStream, is_transient


async def follow(events: EventStream) -> None:
    while True:
        try:
            event = await events.next()
        except DecodeError:
            continue  # one bad frame; the stream goes on
        if event is None:
            return
        kind = event.kind
        if kind == "agent_end":
            print(f"turn    {event.get('agent_alias')} {event.get('tokens_used')} tokens")
        elif kind == "tool_call":
            print(
                f"tool    {event.get('agent_alias')} {event.get('tool')} ok={event.get('success')}"
            )
        elif kind == "cron_result":
            print(f"cron    {event.get('job_id')} ok={event.get('success')}")
        elif kind:
            print(f"{kind:<7} {json.dumps(event)}")
        elif event.is_log:
            print(f"log     {event.get('message')}")


async def main() -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(url, token=os.environ.get("ZEROCLAW_TOKEN")) as client:
        while True:
            try:
                events = await client.events.subscribe()
            except Exception as err:
                if not is_transient(err):
                    raise
                print(f"gateway unavailable ({err}); retrying")
                await asyncio.sleep(5)
                continue
            async with events:
                await follow(events)
            print("stream closed; reconnecting")


with contextlib.suppress(KeyboardInterrupt):
    asyncio.run(main())
