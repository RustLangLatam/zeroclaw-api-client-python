# Errors

Every failure raises a `ZeroClawError` subclass, except the caller's own
cancellation and timeouts. Catch the class you care about:

| Exception | When |
|---|---|
| `APIError(status, message, body)` | The gateway answered with a non-success status. `message` is its explanation (the `error` or `message` field, or the body text); `body` keeps the JSON error body, decoded. |
| `TransportError` | No HTTP answer: connection refused, TLS, a broken connection. Its text starts with `request to the gateway failed`; the `httpx` error is its `__cause__`. |
| `RequestTimeoutError` | The gateway did not answer in time, after any retries. It is also a `TimeoutError`. |
| `TimeoutError`, `asyncio.CancelledError` | Your own `asyncio.timeout` ended, or your task was cancelled, first. |
| your middleware's exception | A [middleware](./resilience.md#your-own-middleware) you added refused the request. |
| `CircuitOpenError` | The [circuit breaker](./resilience.md#circuit-breaker) is open; the call was not sent. |
| `RateLimitedError` | The client's own [rate limit](./resilience.md#rate-limit) could not let the call through in time; it was not sent. |
| `DecodeError` | A successful answer did not have the expected shape. |
| `WebSocketError` | A WebSocket failed. |
| `TurnError(code, message)` | A chat turn ended in an `error` frame, or was aborted (`ABORTED`). |
| `InvalidURLError` | The base URL is not an absolute `http`/`https` URL. It is also a `ValueError`. |

`status_code(err)`, `is_not_found(err)`, `is_unauthorized(err)` (401 and
403), `is_rate_limited(err)` (429, or the client's own limit) and
`is_transient(err)` (no connection, a timeout, an open circuit, the client's
rate limit, or 408, 429, 502, 503, 504: worth trying again later) answer the
usual questions on any exception. Idempotent calls were already retried
before a transient error reaches you; see [Resilience](./resilience.md).

## The gateway's error bodies

The gateway does not use one error shape, and the client reads all of them
into `message`:

- `{"error": "…"}`, most routes, sometimes with `retry_after` (seconds) on
  429;
- `{"code": "…", "message": "…", "path": "…", "op_index": n}` on
  configuration routes (`path_not_found`, `value_type_mismatch`,
  `config_changed_externally`, …) and uploads;
- `{"channel": "…", "error": "…"}` on channel actions;
- plain text when the request is refused before its handler runs (a
  malformed body, a body over 64 KiB, the device endpoints' 401), and an
  empty body on the gateway's request timeout (408).

Read further fields from `body`:

```python
from zeroclaw_client import APIError

try:
    await client.config.set("gateway.port", "not a number")
except APIError as err:
    if err.status == 400 and isinstance(err.body, dict):
        print(err.body.get("code"))  # value_type_mismatch
```
