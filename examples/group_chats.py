"""List the channels, their group chats and the members of each."""

import asyncio
import os

from zeroclaw_client import Client, ZeroClawError


async def main() -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(url, token=os.environ.get("ZEROCLAW_TOKEN")) as client:
        channels = client.channels
        for ch in await channels.list():
            print(f"{ch.name} ({ch.status}, {ch.health})")
            try:
                rooms = await channels.rooms(ch.name)
            except ZeroClawError as err:
                # Not running, or a build without the route: say why and go on.
                print(f"  rooms unavailable: {err}")
                continue
            for room in rooms:
                print(f"  {room.name} — {room.id} ({room.participants} members)")
                for m in await channels.room_members(ch.name, room.id):
                    print(f"    {m.id:<20} {'admin' if m.admin else 'member'}")


asyncio.run(main())
