# Chatting with an agent

## Over the WebSocket

`await client.chat(alias)` opens `/ws/chat` for agent `alias` and waits for
the gateway to confirm the session. The connection is a session
(`gw_<session_id>`); pass `session_id=` to resume one, and `name=` or `cwd=`
to name it or set its working directory. The returned `ChatSession` is an
async context manager: leaving it closes the socket.

`ask` sends a message and waits for the reply:

```python
async with await client.chat("helper") as chat:
    reply = await chat.ask("How many orders are pending?")
print(reply.full_response)
if reply.tokens_used is not None:
    print(reply.tokens_used, "tokens")
```

To show progress, or to answer tool approvals, iterate the frames.
`frame.type` is one of the `FRAME_*` constants and says which fields are
set:

```python
from zeroclaw_client import (
    FRAME_APPROVAL_REQUEST,
    FRAME_CHUNK,
    FRAME_DONE,
    FRAME_ERROR,
    FRAME_TOOL_CALL,
    TurnError,
)

async with await client.chat("helper") as chat:
    await chat.send("Archive last month's invoices")
    async for frame in chat:  # ends when the gateway closes the chat
        if frame.type == FRAME_CHUNK:
            print(frame.content, end="")  # append to the screen
        elif frame.type == FRAME_TOOL_CALL:
            print("running", frame.name)
        elif frame.type == FRAME_APPROVAL_REQUEST:
            await chat.answer_approval(frame.request_id, "approve")
        elif frame.type == FRAME_DONE:
            break  # frame.done holds the tokens and cost
        elif frame.type == FRAME_ERROR:
            raise TurnError(frame.code, frame.message)
```

Frames are read by one task at a time (`async for`, or `next_frame()`, which
returns `None` once the socket closed); sending is safe from any task. A
message sent while a turn runs steers it. Closing the chat, or
`client.sessions.abort(id)`, cancels the running turn. `ask` raises a failed
turn as a `TurnError` with its `code` (`PROVIDER_ERROR`,
`SESSION_QUEUE_FULL`, `ABORTED`, …).

To bound a turn, wrap it in `asyncio.timeout`: the cancellation reaches the
socket read, and closing the session then cancels the turn on the gateway.

## One-shot: webhook and A2A

`client.webhook.send(message, ...)` posts to `/webhook` and returns the
agent's reply in one HTTP call. Its keyword arguments carry the `agent`,
the `secret` (`X-Webhook-Secret`) when the gateway sets one, an
`idempotency_key` (a repeat answers a `WebhookReply` with `duplicate` set,
without running again) and a `session_id` to keep calls in one conversation.

`client.webhook.a2a_send(alias, text)` does the same over the A2A protocol
(`message/send`) for agents published with `a2a.server.enabled`.
