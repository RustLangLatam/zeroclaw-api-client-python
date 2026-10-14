# Resilience

Every HTTP request goes through a stack of layers built as one `httpx`
transport (`_transport.py`). From your code to the network:

```text
your middleware → circuit breaker → concurrency limit → retry → rate limit → deadline → httpx transport → gateway
```

The circuit breaker, the concurrency limit and the rate limit are off unless
you turn them on.

```text
with none of them: your middleware → retry → deadline → httpx transport
```

## Timeouts

`timeout=` (default 60 s, `DEFAULT_TIMEOUT`) bounds how long a request
waits for the gateway's **answer headers**. A streamed body is not bounded,
so `client.events.subscribe()` stays open for as long as the gateway keeps
it. Calls that do long work on the gateway carry their own limit:
`client.cron.run` waits up to 660 s, as the gateway allows a manual run
600 s. `timeout=None` waits forever. If you pass your own transport
(`transport=`, for a proxy, custom TLS, HTTP/2 or a mock), the client's
timeout and retry still wrap it. Opening a WebSocket (chat, canvas and
SOP-run feeds) uses the same timeout for its handshake.

A timeout raises `RequestTimeoutError` (a `TimeoutError`). To bound a whole
call, retries included, wrap it in `asyncio.timeout` of your own; when that
one ends first, the call raises your `TimeoutError` (or the task's
`CancelledError` when it was cancelled), not `RequestTimeoutError`:

```python
async with asyncio.timeout(5):
    status = await client.system.status()
```

## Retries

A failed request is tried again when **both** hold:

- its method is idempotent: `GET`, `HEAD`, `OPTIONS`, `PUT`, `DELETE`. A
  `POST` (creating a cron job, sending a message, starting an SOP) or a
  `PATCH` (a config patch) is never repeated: it could apply twice;
- the failure is one a retry can fix: no connection, a connection dropped
  before the answer (the gateway does it while it restarts), a timeout, or a
  408, 429, 502, 503 or 504 answer. A 4xx that describes the request (400,
  404, 409, …) and a 500 are raised at once.

`RetryPolicy` sets how many retries and how far apart: retry `n` waits
`base_delay × 2ⁿ` seconds, capped at `max_delay`. With `jitter`, each wait
is a random point between half and all of that delay, so clients that
failed together (the gateway restarted under all of them) do not come back
together. The default (`RetryPolicy()`) is three retries, 0.2 s doubling to
5 s (about 200, 400, 800 ms), with jitter. `RetryPolicy.none()` turns them
off. The retry loop runs on [tenacity](https://tenacity.readthedocs.io/).

When a 429 or 503 carries a `Retry-After` header (seconds or an HTTP date),
the client waits that long instead, when it is longer than the backoff, but
never beyond `max_delay`.

```python
from zeroclaw_client import Client, RetryPolicy

client = Client(
    "http://127.0.0.1:42617",
    token="zc_…",
    retry=RetryPolicy(max_retries=5, base_delay=0.25, max_delay=8),
)
```

The gateway restarts itself on `client.system.reload()` and some
configuration changes; for a few seconds it refuses connections. Retries
carry reads through that window.

## Concurrency limit

`concurrency_limit=n` lets at most `n` requests wait for the gateway's
answer at once; the rest wait their turn (or until their task is
cancelled). A request holds its slot until the answer's headers arrive, its
retries and their backoff included; reading a body afterwards (an open event
stream) holds none. Every copy of the client (`with_token`) shares the
limit, so one setting protects the gateway from a whole application.

## Rate limit

`rate_limit=RateLimit(rate=r, burst=b)` keeps the client under `r` requests
per second, with bursts of up to `b`, using a leaky bucket from
[aiolimiter](https://github.com/mjpieters/aiolimiter). Every attempt waits
for its turn, retries included, so the client stays under the gateway's own
limits instead of collecting 429s. The limit is shared by every copy of the
client. A wait longer than the request's timeout fails, without sending
anything, with `RateLimitedError` (`is_rate_limited` and `is_transient` say
yes).

```python
from zeroclaw_client import Client, RateLimit

client = Client(
    "http://127.0.0.1:42617",
    token="zc_…",
    rate_limit=RateLimit(rate=10, burst=20),  # 10 per second, bursts of 20
)
```

## Circuit breaker

`circuit_breaker=CircuitBreaker(threshold=5, ttl=30)` stops calling a
gateway that keeps failing, with [purgatory](https://github.com/mardiros/purgatory).
A transport error, a timeout, a 5xx, a 408 or a 429 count as failures; a
404 or another answer about the request does not, and neither does the
caller cancelling its own task. After `threshold` failures in a row
(default 5) the breaker opens: calls fail at once with `CircuitOpenError`,
without reaching the gateway, for `ttl` seconds (default 30). Then it lets a
trial call through; if it works, it closes again. The breaker sits outside
the retries, so it counts one failure per call, not per attempt, and every
copy of the client shares it.

```python
from zeroclaw_client import CircuitBreaker, CircuitOpenError, Client

client = Client(
    "http://127.0.0.1:42617",
    token="zc_…",
    circuit_breaker=CircuitBreaker(threshold=5, ttl=10),
)
try:
    status = await client.system.status()
except CircuitOpenError:
    ...  # the gateway keeps failing; not calling it for now
```

`CircuitOpenError` tells a refusal of the breaker apart from a gateway
answer; `is_transient` says yes to both.

## Your own middleware

`middleware=[...]` wraps every request in any `Middleware`: an
`async def mw(request, next_)` that gets the `httpx.Request` and the next
`Handler`, and returns the `httpx.Response`. Use it for metrics, tracing or
request signing. Middleware listed first is outermost: it sees each call
once, with the client's retries inside it.

```python
import time

import httpx

from zeroclaw_client import Client, Handler


async def caller(request: httpx.Request, next_: Handler) -> httpx.Response:
    """Add a header to every request."""
    request.headers["X-Caller"] = "billing"
    return await next_(request)


async def timed(request: httpx.Request, next_: Handler) -> httpx.Response:
    """Time every call, retries included."""
    started = time.monotonic()
    try:
        return await next_(request)
    finally:
        print(request.method, request.url.path, time.monotonic() - started)


client = Client(
    "http://127.0.0.1:42617",
    token="zc_…",
    middleware=[caller, timed],
)
```

An exception a middleware raises ends the call with it, unchanged; an
`httpx` error is raised as a `TransportError` (a timeout as a
`RequestTimeoutError`) with the original as its `__cause__`.

## What the client does not do

It starts no tasks of its own that outlive a call: the stack runs in the
caller's task (`httpx` keeps its usual connection pool), and streams are
driven by whoever reads them. It does not reconnect streams by itself
either: when an `EventStream` ends (the gateway reloaded), subscribe again;
`examples/events.py` shows the loop. The WebSocket chat is not an HTTP
request and does not go through the stack; a failed turn is reported, not
retried.
