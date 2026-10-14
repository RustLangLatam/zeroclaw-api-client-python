<h1 align="center"><img src="https://raw.githubusercontent.com/RustLangLatam/zeroclaw-api-client-python/main/docs/assets/python.svg" alt="Python logo" height="40" align="absmiddle" /> zeroclaw-api-client-python</h1>

<p align="center">
  <strong>Your ZeroClaw, from Python. Typed calls, live streams, resilient by default.</strong>
</p>

<p align="center">
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/RustLangLatam/zeroclaw-api-client-python/ci.yml?branch=main&label=build" alt="Build Status" /></a>
  <a href="https://pypi.org/project/zeroclaw-api-client/"><img src="https://img.shields.io/pypi/v/zeroclaw-api-client?label=PyPI" alt="PyPI" /></a>
  <a href="https://pypi.org/project/zeroclaw-api-client/"><img src="https://img.shields.io/pypi/pyversions/zeroclaw-api-client" alt="Python versions" /></a>
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/LICENSE-APACHE"><img src="https://img.shields.io/badge/license-MIT%20OR%20Apache%202.0-blue.svg" alt="License" /></a>
  <a href="https://mypy-lang.org/"><img src="https://img.shields.io/badge/types-mypy%20strict-2a6db2" alt="mypy strict" /></a>
  <a href="https://github.com/zeroclaw-labs/zeroclaw"><img src="https://img.shields.io/badge/ZeroClaw-0.8.5-black" alt="ZeroClaw 0.8.5" /></a>
</p>

<p align="center">
  <a href="https://www.python-httpx.org/"><img src="https://img.shields.io/badge/HTTP-httpx-3776ab" alt="httpx" /></a>
  <a href="https://docs.pydantic.dev/"><img src="https://img.shields.io/badge/models-pydantic%20v2-e92063" alt="pydantic" /></a>
  <a href="https://websockets.readthedocs.io/"><img src="https://img.shields.io/badge/WebSocket-websockets-475569" alt="websockets" /></a>
  <a href="https://tenacity.readthedocs.io/"><img src="https://img.shields.io/badge/retries-tenacity-c2410c" alt="tenacity" /></a>
  <a href="https://github.com/pypa/pip-audit"><img src="https://img.shields.io/badge/supply%20chain-pip--audit-15803d" alt="pip-audit" /></a>
</p>

<p align="center">
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/introduction.md">Docs</a> ·
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/getting-started/index.md">Quick start</a> ·
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/guides/index.md">Guides</a> ·
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/guides/resilience.md">Resilience</a> ·
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/reference/endpoints.md">Endpoint map</a> ·
  <a href="https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/architecture/overview.md">Architecture</a> ·
  <a href="https://github.com/zeroclaw-labs/zeroclaw">ZeroClaw</a>
</p>

---

`zeroclaw-api-client` is a typed, resilient, async Python client for the
[ZeroClaw](https://github.com/zeroclaw-labs/zeroclaw) gateway: its HTTP API,
its Server-Sent Events stream and its WebSocket chat.

> An independent, community-maintained client. It is not affiliated with or
> endorsed by ZeroClaw Labs; ZeroClaw is a trademark of ZeroClaw Labs.

```sh
pip install zeroclaw-api-client     # or: uv add zeroclaw-api-client
```

```python
import asyncio

from zeroclaw_client import Client


async def main() -> None:
    async with Client("http://127.0.0.1:42617", token="zc_…") as client:
        status = await client.system.status()
        channels = await client.channels.list()
        await client.config.set("agents.helper.model", "gpt-5.4-mini")

        async with await client.chat("helper") as chat:
            reply = await chat.ask("How many orders are pending?")
        print(status.version, len(channels), reply.full_response)


asyncio.run(main())
```

## Why an SDK

ZeroClaw is a self-hosted AI agent runtime. Everything an operator can do
with it (configure agents, models and channels, pair devices, run SOPs,
schedule jobs, read sessions and costs, talk to an agent) is exposed by its
gateway over HTTP and WebSockets. Calling that surface by hand from every
application that embeds ZeroClaw means repeating, in each of them:

- **the contract**: about 150 routes, a dozen response shapes for errors, a
  JSON Patch dialect for the configuration, an event stream whose frames have
  no names, a chat protocol with typed frames;
- **the edge cases**: secrets that are never returned, paths that must be
  encoded segment by segment, a gateway that drops connections while it
  reloads, routes that only exist with some build features;
- **the resilience**: timeouts that must not cut a stream, retries that must
  never repeat a write, back-pressure.

This package does it once, typed and tested, so applications talk to
ZeroClaw in terms of channels, agents and sessions instead of URLs and JSON.
When the gateway changes, one place changes.

## Features

- **The whole client surface** of the gateway, one attribute per area:

  | Attribute | Covers |
  |---|---|
  | `config` | per-field reads and writes, atomic JSON Patch, map aliases (agents, providers, channels), drift, catalogs, setup sections |
  | `pairing` | pairing codes, bearer tokens, paired devices |
  | `channels` | channel state, sending, group chats and their members, identity binding, relinking |
  | `chat()` | agent chat over WebSocket: streamed replies, tool calls, tool approvals |
  | `sessions`, `events` | transcripts, session state, the live Server-Sent Events stream |
  | `agent()`, `files`, `skills` | agent workspaces, personality files, shared files, image uploads, skill bundles |
  | `cron`, `memory`, `cost` | scheduled jobs, long-term memory, usage and cost |
  | `sops`, `canvas`, `quickstart` | SOP authoring, runs and approvals; canvases; the first-agent setup |
  | `system` | health, status, metrics, diagnostics, tools, logs, upgrades, reload |
  | `webhook`, `webauthn` | one-shot webhook and A2A messages; hardware-key ceremonies |

- **Async from end to end** (`asyncio`): one client is shared by every task;
  the streams are async iterators.
- **Resilient by default**, built as a stack of layers over an `httpx`
  transport: answer timeouts that never cut a stream, retries with jittered
  exponential backoff for idempotent calls only that honor `Retry-After`
  ([tenacity](https://tenacity.readthedocs.io/)), and, opt-in, a circuit
  breaker ([purgatory](https://github.com/mardiros/purgatory)), a client-side
  rate limit ([aiolimiter](https://github.com/mjpieters/aiolimiter)) and a
  shared concurrency limit; plus your own middleware (metrics, tracing,
  signing) around every request.
- **Typed end to end**: every answer is a [pydantic](https://docs.pydantic.dev/)
  model validated on arrival, the package ships `py.typed` and passes
  `mypy --strict`.
- **Typed errors**: every failure is a `ZeroClawError`; a gateway refusal is
  an `APIError` that keeps its status, its explanation and its JSON body;
  `is_not_found`, `is_unauthorized`, `is_rate_limited` and `is_transient`
  classify any error.
- **Pull, not callbacks**: the event feed is an `EventStream`, the canvas
  and SOP-run feeds a `Feed`, and a chat a session you iterate with
  `async for`. The client starts no background work of its own.
- **Safe by construction**: every path segment is percent-encoded, the token
  never appears in `repr`, nothing is printed or logged.

## Technologies

| Concern | Choice |
|---|---|
| Language | Python 3.11+ (`asyncio`) |
| HTTP | [httpx](https://www.python-httpx.org/) (HTTP/1.1, optional HTTP/2, proxies, TLS) |
| Middleware | layered transport: deadline, rate limit, retry (jitter, `Retry-After`), concurrency limit, circuit breaker, your own `Middleware` |
| Retries | [tenacity](https://tenacity.readthedocs.io/) |
| Rate limiting | [aiolimiter](https://github.com/mjpieters/aiolimiter) leaky bucket |
| Circuit breaking | [purgatory](https://github.com/mardiros/purgatory) |
| WebSockets | [websockets](https://websockets.readthedocs.io/) (`zeroclaw.v1` subprotocol, keep-alive pings) |
| Models | [pydantic v2](https://docs.pydantic.dev/) |
| Tests | pytest with an `httpx.MockTransport` gateway, an in-test WebSocket gateway, captured response vectors, parametrized tests |
| Quality | ruff (format and lint), mypy strict |
| Docs | Google-style docstrings and an [mdBook](https://rust-lang.github.io/mdBook/) book |
| Supply chain | [pip-audit](https://github.com/pypa/pip-audit), a locked `uv.lock`, PyPI trusted publishing |

## Architecture

```text
 your code
    │  await client.channels.rooms("whatsapp.main")
    ▼
 Client ── resource attributes (config, channels, chat, …) ── pydantic requests/responses
    │
    ├─ HTTP ──► your middleware ─► circuit breaker ─► concurrency limit ─► retry ─► rate limit ─► deadline ─► httpx transport ─► gateway
    ├─ SSE ───► the same stack; the body is read as a stream of events
    └─ WebSocket ─► websockets (chat, canvas and SOP-run feeds)
```

Each method's docstring names the route it calls; the
[endpoint map](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/reference/endpoints.md)
is generated from them.

## Resilience

```python
from zeroclaw_client import CircuitBreaker, Client, RateLimit, RetryPolicy

client = Client(
    "http://127.0.0.1:42617",
    token="zc_…",
    timeout=10,  # wait for an answer at most 10 s
    retry=RetryPolicy(max_retries=5, base_delay=0.25, max_delay=8),
    concurrency_limit=4,  # shared by every copy
    rate_limit=RateLimit(rate=10, burst=20),  # 10 requests/s, bursts of 20
    circuit_breaker=CircuitBreaker(),  # open after 5 failures in a row, for 30 s
    middleware=[my_middleware],  # async (request, next) -> response
)
```

Retries apply to `GET`, `HEAD`, `OPTIONS`, `PUT` and `DELETE` after a
connection failure, a connection dropped before the answer, a timeout, or a
408, 429, 502, 503 or 504, with jittered backoff and the gateway's
`Retry-After` honored. A `POST` or `PATCH` is never repeated. An open
breaker fails calls at once with `CircuitOpenError`; the rate limit fails a
wait longer than the timeout with `RateLimitedError`. The timeout bounds the
wait for the answer's headers, so the event stream stays open.

## Examples

Runnable scripts under [`examples/`](https://github.com/RustLangLatam/zeroclaw-api-client-python/tree/main/examples):

| Example | Shows |
|---|---|
| `status.py` | version, model and channels |
| `pairing.py` | exchanging a pairing code for a token |
| `config.py` | reading fields, listing agents, an atomic patch |
| `group_chats.py` | channels, their group chats and members |
| `events.py` | following the live event stream, reconnecting |
| `chat.py` | streaming an agent's reply over the WebSocket |
| `announce.py` | posting on a channel through a one-off cron job |
| `resilient.py` | timeouts, retries, rate limit, circuit breaker, concurrency limit and a custom middleware |

```sh
ZEROCLAW_URL=http://127.0.0.1:42617 ZEROCLAW_TOKEN=zc_… python examples/status.py
```

## Testing

- **Parametrized unit tests** for every piece of logic: error mapping, URL
  encoding, SSE parsing, chat frames, retry decisions, backoff, patch
  operations, schedules.
- **HTTP-boundary tests** for every endpoint against a mock gateway: method,
  path, query, body and decoding; plus retry, timeout, circuit breaker, rate
  limit, concurrency and middleware behavior.
- **Response vectors**: answers captured from a real gateway
  (`scripts/capture-vectors.py`, anonymized) must decode into the SDK's
  models and re-encode without losing a field.
- **Live tests** against a running gateway (`pytest -m live`): every read
  decodes real answers, and a write suite covers the rest of the surface,
  cleaning up after itself.

```sh
uv sync && uv run pytest
```

## Compatibility

Targets the ZeroClaw **0.8.5** gateway; see
[Compatibility](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/docs/book/src/reference/compatibility.md)
for the builds it is verified against and the routes that need a newer one.

## Other languages

The same client, with the same surface, behavior and tests:

| Language | Repository | Install |
|---|---|---|
| Rust | [zeroclaw-api-client-rust](https://github.com/RustLangLatam/zeroclaw-api-client-rust) | `cargo add zeroclaw-api-client` |
| Go | [zeroclaw-api-client-go](https://github.com/RustLangLatam/zeroclaw-api-client-go) | `go get github.com/RustLangLatam/zeroclaw-api-client-go` |

## Contributing

Work happens on branches with pull requests to `main`; see
[CONTRIBUTING.md](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/CONTRIBUTING.md)
and [AGENTS.md](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/AGENTS.md).

## License

Licensed under either of [Apache License, Version 2.0](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/LICENSE-APACHE)
or [MIT license](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/LICENSE-MIT),
at your option.

The Python logo is a trademark of the Python Software Foundation, used here
to say the client is written in Python, in line with the
[PSF Trademark Usage Policy](https://www.python.org/psf/trademarks/).
