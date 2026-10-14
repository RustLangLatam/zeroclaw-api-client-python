# Sessions and live events

## Sessions

Every conversation is a session: web chats are `gw_<id>`, channel
conversations `whatsapp_<channel>_<peer>…`. `client.sessions.list()`
returns them with their agent and channel; `messages(id)` the transcript
(tool calls and results included, as JSON text); `state(id)` whether a turn
is running; `running()` only the gateway's own (web chat) sessions.

`add_message(id, content)` appends an assistant message (shown to chat
clients, with no agent turn); `rename`, `abort` and `delete` do what they
say.

## The live event stream

`await client.events.subscribe()` follows `/api/events`, the gateway's
Server-Sent Events stream. Read it with `next()` until it returns `None`
(or with `async for`):

```python
from zeroclaw_client import DecodeError

async with await client.events.subscribe() as events:
    while True:
        try:
            event = await events.next()
        except DecodeError:
            continue  # a frame that is not JSON; the stream goes on
        if event is None:
            break  # the gateway closed it: subscribe again
        if event.kind == "agent_end":
            print("turn cost", event.get("cost_usd"))  # tokens and cost of a turn
        elif event.kind == "cron_result":
            pass  # a job ran
        elif event.is_log:
            pass  # a structured log event
```

An `Event` is a `dict` of the frame's top-level fields, decoded from JSON.
Frames have no SSE event name; `Event.kind` reads their `type`. Observer
events (`llm_request`, `tool_call`, `tool_call_start`, `agent_start`,
`agent_end`, `error`, `history_trimmed`) carry `source: "observability"`;
log events carry `@timestamp` instead of a `type`. Frames of a single
session are not published here; they reach that session's chat. The stream
ends when the gateway closes it (on reload, for instance): subscribe again;
`examples/events.py` shows the loop. `client.events.history()` returns the
latest observer events, kept in memory.

The client's timeout bounds only the wait for the stream to open; once
events flow it stays open as long as the gateway keeps it, until you close
it, or until your task is cancelled.
