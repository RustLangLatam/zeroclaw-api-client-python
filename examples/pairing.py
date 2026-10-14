"""Exchange a pairing code for a token, then list the paired devices.

python examples/pairing.py <code> [device name]
"""

import asyncio
import os
import sys

from zeroclaw_client import Client


async def main(code: str, name: str | None) -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(url) as anonymous:
        paired = await anonymous.pairing.pair(code, name, "service")
        client = anonymous.with_token(paired.token)
        print(f"Paired. Keep this token secret:\n{paired.token}\n")
        for d in await client.pairing.devices():
            print(f"{d.id}  {d.name or '':<20} paired {d.paired_at}")


if len(sys.argv) < 2:
    sys.exit("usage: pairing.py <code> [device name]")
asyncio.run(main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None))
