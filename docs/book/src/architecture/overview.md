# Architecture

The distribution is one package, `zeroclaw_client`, with one module per area
of the gateway. Everything public is exported from the package itself.

## The client

`Client` (`_client.py`) holds the base URL, the bearer token and one
`httpx.AsyncClient` whose transport is the resilience stack. Its constructor
takes keyword arguments (`token`, `timeout`, `retry`, `concurrency_limit`,
`rate_limit`, `circuit_breaker`, `middleware`, `transport`). A `Client` is
safe to share between tasks; `with_token` returns a copy that shares the
pool, the concurrency limit, the rate limit and the circuit breaker. It is
an async context manager, or is closed with `aclose()`.

Requests are sent through a stack of layers (`_transport.py`,
[ADR-004](./decisions/ADR-004-transport-stack.md)): the caller's
middleware, an optional circuit breaker, an optional concurrency limit,
retry, an optional rate limit and a deadline, around an `httpx` transport.
All HTTP goes through a few private helpers in `_client.py`:

- `_url(segments)` appends **path segments**, each percent-encoded, to the
  base URL. Ids are never formatted into a path string, so an id holding
  `/` or `?` stays one segment;
- `_build` attaches the bearer token, the `User-Agent`, the query and the
  JSON body;
- `_send` passes the request through the stack and turns a non-success
  status into an `APIError`, keeping the gateway's message and JSON body;
- `_json`, `_call`, `_text` and `_field` (which unwraps single-field
  envelopes) decode.

## Resource attributes

Each module defines a small class holding the client (`ConfigAPI`,
`ChannelsAPI`, …) whose methods are the endpoints, and `Client` exposes it
as a property (`client.config`, `client.channels`, …).
`client.agent(alias)` also carries the agent alias. A method's docstring
names the route it calls, which the
[endpoint map](../reference/endpoints.md) is generated from.

## Streams

Two kinds of live data are read by the caller, one value at a time (the
client starts no tasks for them):

- **Server-Sent Events** (`client.events.subscribe()`): `events.py` splits
  the body into frames and decodes their JSON; `EventStream` is an async
  iterator, and `next()` returns `None` at the end;
- **WebSockets** (`chat.py`, on `websockets`): a socket is opened with
  ZeroClaw's `zeroclaw.v1` subprotocol and the bearer token, turning a
  refused handshake into an `APIError`. The chat reads typed `ChatFrame`s
  (`async for frame in chat`); the canvas and SOP-run feeds are `Feed`s of
  JSON frames.

## Types

Response models are pydantic models (`_model.Model`) that mirror the
gateway's serialized structs and `json!` literals, field for field, and
name the handler in their module docstring. Shapes that are dynamic or
versioned with ZeroClaw stay decoded JSON, typed `Any`
([ADR-002](./decisions/ADR-002-dynamic-shapes-stay-json.md)).
