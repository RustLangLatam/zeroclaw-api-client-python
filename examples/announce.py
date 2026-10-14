"""Post a message on a channel through a one-off cron job.

python examples/announce.py <agent> <channel> <to> <text>
"""

import asyncio
import os
import shlex
import sys

from zeroclaw_client import Client, Delivery, NewCronJob


async def main(agent: str, channel: str, to: str, text: str) -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(url, token=os.environ.get("ZEROCLAW_TOKEN")) as client:
        cron = client.cron
        job = await cron.create(
            NewCronJob(
                agent=agent,
                name="announce-example",
                # Never due on its own: it is run by hand right below.
                schedule="0 0 1 1 *",
                job_type="shell",
                # echo is what an agent's shell policy allows; quote for the shell.
                command=f"echo {shlex.quote(text)}",
                shell_output_format="raw",
                delivery=Delivery.announce(channel, to),
            )
        )
        try:
            run = await cron.run(job.id)
        finally:
            await cron.delete(job.id)
        print(f"{'sent' if run.success else 'failed'} in {run.duration_ms} ms")


if len(sys.argv) != 5:
    sys.exit("usage: announce.py <agent> <channel> <to> <text>")
asyncio.run(main(*sys.argv[1:5]))
