# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project
uses [Semantic Versioning](https://semver.org/).

## 0.2.0 - 2026-10-16

### Removed

- **Breaking:** `ChannelsAPI.send`, `rooms`, `create_room`, `room_members`,
  `invite` and `remove_member`, with their models `RoomSummary`,
  `RoomMember`, `Participant` and `CreatedRoom`. Their routes
  (`/api/channels/{channel}/send` and `/api/channels/{channel}/rooms…`) only
  exist in a fork, never in the official ZeroClaw gateway, which declined
  them ([zeroclaw-labs/zeroclaw#11434](https://github.com/zeroclaw-labs/zeroclaw/issues/11434)).
  The client now covers only the official gateway.

## 0.1.0 - 2026-10-14

First release: the Python port of
[zeroclaw-api-client-go](https://github.com/RustLangLatam/zeroclaw-api-client-go).

### Added

- The whole client surface of the ZeroClaw 0.8.5 gateway, async on
  `asyncio`: the HTTP API, the Server-Sent Events stream and the WebSocket
  chat, one `Client` attribute per area (`config`, `pairing`, `channels`,
  `sessions`, `events`, `files`, `skills`, `cron`, `memory`, `cost`, `sops`,
  `canvas`, `quickstart`, `system`, `webhook`, `webauthn`), plus
  `client.agent(alias)` and `await client.chat(alias)`.
- Typed pydantic v2 models for every stable response, decoded leniently;
  dynamic shapes (SOPs, schemas, quickstart, WebAuthn) as decoded JSON.
- Pull-based streams: `EventStream`, `ChatSession` and `Feed` are async
  iterators and async context managers.
- Resilience as a layered `httpx` transport: answer timeouts that never cut
  a stream, retries of idempotent calls with jittered backoff that honor
  `Retry-After` (`RetryPolicy`), and, opt-in, a concurrency limit, a
  client-side rate limit (`RateLimit`), a circuit breaker
  (`CircuitBreaker`) and your own `Middleware`.
- Typed exceptions under `ZeroClawError` (`APIError`, `TransportError`,
  `RequestTimeoutError`, `CircuitOpenError`, `RateLimitedError`,
  `DecodeError`, `WebSocketError`, `TurnError`, `InvalidURLError`) and the
  classifiers `status_code`, `is_not_found`, `is_unauthorized`,
  `is_rate_limited` and `is_transient`.
- `py.typed`, checked with `mypy --strict`; Python 3.11 to 3.14.
- Runnable examples, HTTP-boundary tests against a mock gateway, captured
  response vectors and a live test suite.
