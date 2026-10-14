"""The stack every HTTP request goes through, from the caller to the network.

    middleware → breaker → concurrency limit → retry → rate limit → deadline → transport

- Circuit breaker: optional (:class:`CircuitBreaker`, backed by ``purgatory``);
  after repeated failures it refuses calls at once with
  :class:`CircuitOpenError` for a while, instead of piling them on a gateway
  that is down.
- Concurrency limit: optional, shared by every copy of the client.
- Retry: idempotent requests (GET, HEAD, OPTIONS, PUT, DELETE) are retried
  (with ``tenacity``) on connection failures, timeouts and the statuses that
  mean "try again" (408, 429, 502, 503, 504), with exponential backoff and
  jitter. A POST or PATCH is never retried: it could apply twice. A
  ``Retry-After`` header on a 429 or 503 is honored, up to the policy's
  ``max_delay``.
- Rate limit: optional (:class:`RateLimit`, backed by ``aiolimiter``); every
  attempt, retries included, waits for its turn, so the client stays under
  the gateway's limits instead of collecting 429s.
- Deadline: bounds the wait for the response headers, so a long
  Server-Sent Events body is never cut. A request carrying its own timeout
  (the client sets one on long gateway calls such as a manual cron run) uses
  it instead of the client's.

The WebSocket chat and feeds are not HTTP requests and do not go through
this stack.
"""

from __future__ import annotations

import asyncio
import email.utils
import random
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

import httpx
from aiolimiter import AsyncLimiter
from purgatory import AsyncCircuitBreakerFactory
from purgatory.domain.model import OpenedState
from tenacity import AsyncRetrying, RetryCallState, retry_if_exception, retry_if_result
from tenacity.stop import stop_after_attempt

from ._errors import (
    RETRYABLE_STATUSES,
    CircuitOpenError,
    RateLimitedError,
    RequestTimeoutError,
    is_retryable_error,
)

__all__ = ["CircuitBreaker", "Handler", "Middleware", "RateLimit", "RetryPolicy"]

#: Sends a request and returns the answer (its headers; the body may still stream).
Handler = Callable[[httpx.Request], Awaitable[httpx.Response]]

#: Wraps every HTTP request (metrics, tracing, request signing, …): it gets the
#: request and the next handler, and returns the answer.
Middleware = Callable[[httpx.Request, Handler], Awaitable[httpx.Response]]

#: The request extension that carries a per-request answer timeout (seconds).
TIMEOUT_EXTENSION = "zeroclaw_timeout"

_IDEMPOTENT = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """When and how often a failed idempotent request is tried again.

    The delay before retry ``n`` (0-based) is ``base_delay * 2**n``, capped at
    ``max_delay``; with ``jitter``, the wait is a random point in its upper
    half, so clients that failed together do not retry together.
    """

    #: How many times a request is tried again at most.
    max_retries: int = 3
    #: The wait before the first retry, in seconds.
    base_delay: float = 0.2
    #: The cap on the wait between retries, in seconds.
    max_delay: float = 5.0
    #: Randomize each wait between half and all of its delay.
    jitter: bool = True

    @classmethod
    def none(cls) -> RetryPolicy:
        """Return a policy that never retries."""
        return cls(max_retries=0, base_delay=0, max_delay=0, jitter=False)

    def delay(self, attempt: int) -> float:
        """Return how long to wait before retry ``attempt`` (0-based), without jitter."""
        if self.base_delay <= 0:
            return 0.0
        return float(min(self.base_delay * 2.0 ** min(attempt, 64), self.max_delay))

    def wait(
        self, attempt: int, response: httpx.Response | None, now: float | None = None
    ) -> float:
        """Return how long to sleep before retry ``attempt`` after ``response``.

        ``response`` is ``None`` after a transport error. The wait is the
        policy's delay, jittered, or the gateway's ``Retry-After`` when
        longer, never beyond ``max_delay``.
        """
        d = self.delay(attempt)
        if self.jitter and d > 0:
            d = d / 2 + random.uniform(0, d / 2)
        after = retry_after(response, time.time() if now is None else now)
        if after > d:
            d = min(after, self.max_delay)
        return d


def retry_after(response: httpx.Response | None, now: float) -> float:
    """Return the wait a 429 or 503 asks for in ``Retry-After`` (seconds or an HTTP date), or 0."""
    if response is None or response.status_code not in (429, 503):
        return 0.0
    value = response.headers.get("Retry-After", "").strip()
    if value.isdigit():
        return float(int(value))
    try:
        at = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return 0.0
    return max(at.timestamp() - now, 0.0)


def is_idempotent(method: str) -> bool:
    """Report whether repeating a request with this method is safe."""
    return method.upper() in _IDEMPOTENT


@dataclass(frozen=True, slots=True)
class RateLimit:
    """Keep the client under ``rate`` requests per second, with bursts of up to ``burst``.

    Shared by every copy of the client. Every attempt, retries included,
    waits for its turn; a wait longer than the request's timeout fails with
    :class:`RateLimitedError`.
    """

    rate: float
    burst: int = 1


@dataclass(frozen=True, slots=True)
class CircuitBreaker:
    """Stop calling a gateway that keeps failing.

    After ``threshold`` failures in a row, calls fail at once with
    :class:`CircuitOpenError` until ``ttl`` seconds have passed and a trial
    call works. A transport error, a 5xx, 408 or 429 count as failures; the
    caller's own cancellations do not. The breaker is shared by every copy of
    the client, and sees one logical call (its retries included).
    """

    threshold: int = 5
    ttl: float = 30.0


class _FailedAnswer(Exception):
    """Marks, inside the breaker, an answer that counts as a failure."""

    def __init__(self, response: httpx.Response) -> None:
        self.response = response


def _deadline(next_: Handler, timeout: float | None) -> Handler:
    async def handle(request: httpx.Request) -> httpx.Response:
        limit = request.extensions.get(TIMEOUT_EXTENSION, timeout)
        if limit is None or limit <= 0:
            return await next_(request)
        try:
            async with asyncio.timeout(limit):
                return await next_(request)
        except TimeoutError as exc:
            raise RequestTimeoutError() from exc

    return handle


def _throttle(next_: Handler, limiter: AsyncLimiter, timeout: float | None) -> Handler:
    async def handle(request: httpx.Request) -> httpx.Response:
        limit = request.extensions.get(TIMEOUT_EXTENSION, timeout)
        try:
            async with asyncio.timeout(limit if limit and limit > 0 else None):
                await limiter.acquire()
        except TimeoutError as exc:
            raise RateLimitedError("client rate limit exceeded") from exc
        return await next_(request)

    return handle


def _retry(next_: Handler, policy: RetryPolicy) -> Handler:
    def wait(state: RetryCallState) -> float:
        outcome = state.outcome
        response = None
        if outcome is not None and not outcome.failed:
            response = outcome.result()
        return policy.wait(state.attempt_number - 1, response)

    async def discard(state: RetryCallState) -> None:
        # The answer that is retried is closed, so its connection is reused.
        outcome = state.outcome
        if outcome is not None and not outcome.failed:
            response: httpx.Response = outcome.result()
            await response.aclose()

    def last(state: RetryCallState) -> httpx.Response:
        assert state.outcome is not None
        result: httpx.Response = state.outcome.result()
        return result

    async def handle(request: httpx.Request) -> httpx.Response:
        if policy.max_retries <= 0 or not is_idempotent(request.method):
            return await next_(request)
        await request.aread()  # the body is sent again on each attempt
        retrying = AsyncRetrying(
            stop=stop_after_attempt(policy.max_retries + 1),
            wait=wait,
            retry=(
                retry_if_exception(is_retryable_error)
                | retry_if_result(lambda r: r.status_code in RETRYABLE_STATUSES)
            ),
            before_sleep=discard,
            retry_error_callback=last,
            reraise=True,
        )
        result: httpx.Response = await retrying(next_, request)
        return result

    return handle


def _limit(next_: Handler, slots: asyncio.Semaphore) -> Handler:
    async def handle(request: httpx.Request) -> httpx.Response:
        async with slots:
            return await next_(request)

    return handle


def _breaker(next_: Handler, settings: CircuitBreaker) -> Handler:
    factory = AsyncCircuitBreakerFactory(
        default_threshold=settings.threshold,
        default_ttl=settings.ttl,
        exclude=[asyncio.CancelledError],
    )

    async def handle(request: httpx.Request) -> httpx.Response:
        try:
            async with await factory.get_breaker("zeroclaw"):
                response = await next_(request)
                if response.status_code >= 500 or response.status_code in RETRYABLE_STATUSES:
                    raise _FailedAnswer(response)
                return response
        except _FailedAnswer as failed:
            return failed.response
        except OpenedState as exc:
            raise CircuitOpenError("circuit breaker is open") from exc

    return handle


def _with_middleware(next_: Handler, middleware: Middleware) -> Handler:
    async def handle(request: httpx.Request) -> httpx.Response:
        return await middleware(request, next_)

    return handle


class StackTransport(httpx.AsyncBaseTransport):
    """The ``httpx`` transport that sends every request through the stack."""

    def __init__(
        self,
        base: httpx.AsyncBaseTransport,
        *,
        timeout: float | None,
        retry: RetryPolicy,
        concurrency_limit: int | None,
        rate_limit: RateLimit | None,
        circuit_breaker: CircuitBreaker | None,
        middleware: Sequence[Middleware],
    ) -> None:
        self._base = base
        handler: Handler = _deadline(base.handle_async_request, timeout)
        if rate_limit is not None:
            limiter = AsyncLimiter(rate_limit.burst, rate_limit.burst / rate_limit.rate)
            handler = _throttle(handler, limiter, timeout)
        handler = _retry(handler, retry)
        if concurrency_limit:
            handler = _limit(handler, asyncio.Semaphore(concurrency_limit))
        if circuit_breaker is not None:
            handler = _breaker(handler, circuit_breaker)
        for m in reversed(middleware):
            handler = _with_middleware(handler, m)
        self._handler = handler

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """Send ``request`` through the stack."""
        return await self._handler(request)

    async def aclose(self) -> None:
        """Close the underlying transport."""
        await self._base.aclose()
