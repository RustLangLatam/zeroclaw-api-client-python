"""Read configuration fields, list the agents, and change a model atomically.

python examples/config.py                    # read only
python examples/config.py --set <agent> <model>
"""

import asyncio
import json
import os
import sys

from zeroclaw_client import Client
from zeroclaw_client.config import comment_op, replace_op, test_op


async def main(args: list[str]) -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(url, token=os.environ.get("ZEROCLAW_TOKEN")) as client:
        config = client.config
        listing = await config.list("gateway")
        for entry in listing.entries[:8]:
            value = "<secret>" if entry.value is None else json.dumps(entry.value)
            print(f"{entry.path:<40} {entry.kind:<10} {value}")
        print("agents:", await config.map_keys("agents"))

        if not args:
            return
        if len(args) != 3 or args[0] != "--set":
            sys.exit("usage: config.py --set <agent> <model>")
        path = f"agents.{args[1]}.model"
        current = await config.get(path)
        if current.is_secret():
            sys.exit("the model is a secret?")
        patched = await config.patch(
            [
                test_op(path, current.value),
                replace_op(path, args[2]),
                comment_op(path, "changed with the config example"),
            ]
        )
        print(f"{path}: {current.value} -> {args[2]} (saved: {patched.saved})")
        if await config.pending_reload():
            print("a daemon reload is due for every subsystem to see it")


asyncio.run(main(sys.argv[1:]))
