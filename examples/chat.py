"""Stream an agent's reply over the chat WebSocket.

python examples/chat.py <agent> <question>
"""

import asyncio
import os
import sys

from zeroclaw_client import Client
from zeroclaw_client.chat import FRAME_CHUNK, FRAME_DONE, FRAME_ERROR, FRAME_TOOL_CALL


async def main(agent: str, question: str) -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with (
        Client(url, token=os.environ.get("ZEROCLAW_TOKEN")) as client,
        await client.chat(agent) as chat,
    ):
        await chat.send(question)
        async for frame in chat:
            if frame.type == FRAME_CHUNK:
                print(frame.content, end="", flush=True)
            elif frame.type == FRAME_TOOL_CALL:
                print(f"\n[tool: {frame.name}]")
            elif frame.type == FRAME_DONE:
                assert frame.done is not None
                print(f"\n— {frame.done.tokens_used or 0} tokens")
                return
            elif frame.type == FRAME_ERROR:
                sys.exit(frame.message)


if len(sys.argv) != 3:
    sys.exit("usage: chat.py <agent> <question>")
asyncio.run(main(sys.argv[1], sys.argv[2]))
