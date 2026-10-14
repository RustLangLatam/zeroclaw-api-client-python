---
id: ADR-005
title: Proven packages for HTTP, models and resilience
date: 2026-10-14
status: accepted
relates-to:
  - pyproject.toml
  - src/zeroclaw_client/_transport.py
---

# ADR-005: Proven Packages For HTTP, Models And Resilience

## Context

The Go client stands on its standard library for HTTP, TLS and JSON. Python's
standard library has no async HTTP client, no WebSocket client and no typed
validation of JSON, so the port needs packages for those, and for the
resilience the Go client gets from small libraries:

- a gateway that is down, or restarting in a loop, keeps receiving every
  call (each with its retries) and every caller waits for its timeout;
- a busy application sends faster than the gateway's limits and turns into
  a stream of 429s.

Both have well-known answers (a circuit breaker, a rate limiter) whose
details are easy to get subtly wrong: half-open trial calls, bursts,
cancellation while waiting. The same is true of retry loops. Writing them
again inside the client would be one more thing to maintain and test.

Every package chosen must be actively maintained, async-native on
`asyncio`, and typed (or small enough that its untyped surface is a few
calls).

## Decision

Six runtime dependencies, each for one concern:

- [httpx](https://www.python-httpx.org/) for HTTP: async, typed, with a
  pluggable transport (the resilience stack is one,
  [ADR-004](./ADR-004-transport-stack.md)), a mock transport for tests,
  proxies and optional HTTP/2;
- [pydantic v2](https://docs.pydantic.dev/) for the models: validation on
  arrival with clear errors, lenient about unknown fields, and a mypy
  plugin, so `mypy --strict` checks the models;
- [websockets](https://websockets.readthedocs.io/) for the chat and the
  feeds: asyncio-native, typed, with subprotocols, keep-alive pings and
  frame size limits;
- [tenacity](https://tenacity.readthedocs.io/) for the retry loop: an async
  retrying controller whose stop, wait and retry conditions the client
  supplies (its own jitter and `Retry-After` reading are a few lines of the
  standard library);
- [aiolimiter](https://github.com/mjpieters/aiolimiter) for
  `rate_limit=`: an asyncio leaky bucket every attempt waits on, inside the
  retry loop;
- [purgatory](https://github.com/mardiros/purgatory) for
  `circuit_breaker=`: an async circuit breaker outside the retry loop, so
  one call counts once.

Considered and not taken:

- **requests**: synchronous only, so every call would block the event loop
  or need a thread;
- **aiohttp**: async, but with its own session API and no pluggable
  transport layer to build the stack on or to mock in tests;
- **pybreaker**: its async support needs tornado;
- **aiobreaker**: unmaintained since 2021;
- **hand-written retries**: the decision logic (method, status, attempt) is
  the client's own and tested as such, but the loop around it, with its
  sleeps, cancellation and final outcome, is what tenacity already does well.

## Consequences

- Six dependencies instead of the Go client's three; all support the
  Python 3.11 floor ([ADR-003](./ADR-003-python-floor.md)), are bounded to
  a major version in `pyproject.toml`, and are checked by `pip-audit` in CI.
- The rate limit and the breaker are configured with the client's own small
  `RateLimit` and `CircuitBreaker` types, so their packages can be swapped
  without changing the API.
- Neither the rate limit nor the breaker is active unless the application
  turns it on: the default behavior is the Rust client's.
