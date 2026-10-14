---
id: ADR-004
title: Requests go through a layered async transport
date: 2026-10-14
status: accepted
relates-to:
  - src/zeroclaw_client/_transport.py
  - docs/book/src/guides/resilience.md
---

# ADR-004: Requests Go Through A Layered Async Transport

## Context

A ZeroClaw gateway restarts on reloads and some configuration changes,
refusing connections for seconds; it answers 502 and 503 while a channel
reconnects and 429 when rate-limited; some calls take minutes. Applications
need timeouts, retries and back-pressure, and often their own cross-cutting
concerns (metrics, tracing). Hand-written loops in each client method would
repeat that logic and could not be extended by callers.

The gateway's clients are I/O-bound and long-lived (event streams, chats),
and the Rust client this one ports is async too.

## Decision

**Async only.** Every call is a coroutine on `asyncio`, and the streams are
async iterators. One `Client` is shared by every task of an application. A
synchronous wrapper may come later, as a thin layer over this API, if
applications ask for it; it is not part of the first release.

**A layered transport.** Every HTTP request is sent through one
`httpx.AsyncBaseTransport` (`StackTransport`) built once per client, made
of handlers that each wrap the next: the caller's `Middleware`, an optional
circuit breaker, an optional global concurrency limit, the retry policy, an
optional rate limit and a deadline, around `httpx.AsyncHTTPTransport` (or
the caller's transport, `transport=`). A transport is httpx's own extension
point, so the stack needs no framework, and a `Middleware` is just
`async def (request, next_) -> response`.

- **Retry** only for idempotent methods and failures a retry can fix, with
  jittered exponential backoff that honors `Retry-After`; never a `POST` or
  `PATCH`. The request body is read once and sent again on each attempt.
- **Deadline** is a layer of the client's own rather than an `httpx`
  timeout: it bounds the response headers only, with `asyncio.timeout`, so
  streams are not cut, and honors a per-request timeout for long gateway
  calls. The caller's own `asyncio.timeout` still bounds the whole call.
- **Concurrency limit** is an `asyncio.Semaphore`, shared by every copy of
  the client; waiting for a slot can be cancelled.
- **No background tasks:** the stack runs in the caller's task.

## Consequences

- Resilience is configured, not coded per call, and covered by
  parametrized tests of each decision (method, status, attempt, backoff,
  `Retry-After`) and by tests against the mock gateway
  (`tests/test_resilience.py`).
- Callers plug metrics, tracing or signing in through `middleware=`.
- Synchronous applications run the client in an event loop of their own
  (`asyncio.run`) until a wrapper exists.
- WebSockets are outside the stack: a dropped chat or feed is the caller's to
  reopen.
