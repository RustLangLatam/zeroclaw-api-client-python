"""Print the gateway's version, model and channels.

ZEROCLAW_URL=http://127.0.0.1:42617 ZEROCLAW_TOKEN=zc_… python examples/status.py
"""

import asyncio
import os

from zeroclaw_client import Client


async def main() -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(url, token=os.environ.get("ZEROCLAW_TOKEN")) as client:
        status = await client.system.status()
        print(f"ZeroClaw {status.version} — model {status.model}")
        for ch in await client.channels.list():
            print(f"  {ch.name:<40} {ch.status:<10} {ch.health}")


asyncio.run(main())
