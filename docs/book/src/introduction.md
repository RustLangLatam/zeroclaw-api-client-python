# ZeroClaw API Client

`zeroclaw-api-client` is a typed, async Python client for the
[ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) gateway: the HTTP and
WebSocket surface a ZeroClaw daemon exposes for its dashboard, its CLI and
third-party tooling. It is the Python port of
[zeroclaw-api-client-rust](https://github.com/RustLangLatam/zeroclaw-api-client-rust)
and [zeroclaw-api-client-go](https://github.com/RustLangLatam/zeroclaw-api-client-go),
and covers the same routes.

With it an application can do everything the gateway allows a client to do:

- read and change the configuration, one field at a time or in atomic
  batches, including agents, providers and channels;
- pair new clients and manage the paired devices;
- see channels, send through them, and manage WhatsApp group chats and their
  members;
- chat with an agent, streaming its reply, tool calls and approval requests;
- follow the live event stream and read session transcripts;
- schedule cron jobs, store and recall memory, and read usage and cost;
- edit agent workspaces, personality files, skills and SOPs, and run SOPs;
- check health, run diagnostics, read logs and upgrade the daemon.

It is a library: it never prints, logs or starts tasks that outlive a call.
Every call returns a typed result or raises a typed [error](./guides/errors.md)
carrying the gateway's own explanation.

This is an independent, community-maintained client. It is not affiliated
with or endorsed by ZeroClaw Labs.

## How it is organized

A [`Client`](./architecture/overview.md) holds the gateway URL and the bearer
token. Each group of endpoints is reached through an attribute, so call sites
read like the gateway's routes:

```python
async with Client("http://127.0.0.1:42617", token="zc_…") as client:
    channels = await client.channels.list()
    await client.config.set("agents.helper.model", "gpt-5.4-mini")
    async with await client.chat("helper") as chat:
        reply = await chat.ask("Hi")
    print(len(channels), reply.full_response)
```

Every call is a coroutine to `await`, and a failure raises a
`ZeroClawError`. Start with [Getting Started](./getting-started/index.md).
The [endpoint map](./reference/endpoints.md) lists every route and the
method that calls it.
