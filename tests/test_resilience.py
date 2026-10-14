from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from zeroclaw_client import (
    APIError,
    CircuitBreaker,
    CircuitOpenError,
    Client,
    Handler,
    RateLimit,
    RateLimitedError,
    RequestTimeoutError,
    RetryPolicy,
    TransportError,
    is_transient,
)
from zeroclaw_client.cron import CronJobPatch

FAST = RetryPolicy(max_retries=3, base_delay=0.001, max_delay=0.001)
JOBS: dict[str, list[object]] = {"jobs": []}


class Statuses:
    """Answers each status in turn (the last one from then on) and counts the calls."""

    def __init__(self, *codes: int | Exception) -> None:
        self.codes = codes
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        code = self.codes[min(self.calls, len(self.codes) - 1)]
        self.calls += 1
        if isinstance(code, Exception):
            raise code
        return httpx.Response(code, json=JOBS if code == 200 else {"error": "down"})


def make(handler: Callable[..., Any], **kwargs: Any) -> Client:
    kwargs.setdefault("retry", FAST)
    return Client("http://gateway.test", transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.parametrize(
    ("codes", "retries", "calls", "ok"),
    [
        ((503, 200), 3, 2, True),
        ((503, 503, 503, 200), 3, 4, True),
        ((503,), 3, 4, False),
        ((200,), 3, 1, True),
        ((500,), 3, 1, False),
        ((429, 200), 3, 2, True),
        ((502, 200), 3, 2, True),
        ((503,), 0, 1, False),
    ],
)
async def test_retry_decision_vectors(
    codes: tuple[int, ...], retries: int, calls: int, ok: bool
) -> None:
    gateway = Statuses(*codes)
    async with make(gateway, retry=RetryPolicy(retries, 0.001, 0.001)) as client:
        if ok:
            await client.cron.list()
        else:
            with pytest.raises(APIError):
                await client.cron.list()
    assert gateway.calls == calls


@pytest.mark.parametrize("method", ["PUT", "DELETE"])
async def test_idempotent_writes_are_retried_with_their_body(method: str) -> None:
    bodies: list[bytes] = []

    def handle(request: httpx.Request) -> httpx.Response:
        bodies.append(request.content)
        return httpx.Response(503 if len(bodies) < 3 else 200, json={})

    async with make(handle) as client:
        await client._request(method, ["api", "x"], json_body={"a": 1})
    assert bodies == [b'{"a":1}'] * 3


@pytest.mark.parametrize("method", ["POST", "PATCH"])
async def test_non_idempotent_calls_are_never_retried(method: str) -> None:
    gateway = Statuses(503)
    async with make(gateway) as client:
        with pytest.raises(APIError) as err:
            await client._request(method, ["api", "cron", "j1"], json_body=CronJobPatch())
    assert gateway.calls == 1
    assert is_transient(err.value)


async def test_a_dropped_connection_is_retried() -> None:
    gateway = Statuses(httpx.RemoteProtocolError("server disconnected"), 200)
    async with make(gateway) as client:
        await client.cron.list()
    assert gateway.calls == 2


async def test_a_dropped_connection_without_retries_is_transient() -> None:
    gateway = Statuses(httpx.ReadError("connection reset"))
    async with make(gateway, retry=RetryPolicy.none()) as client:
        with pytest.raises(TransportError) as err:
            await client.cron.list()
    assert is_transient(err.value)
    assert isinstance(err.value.__cause__, httpx.ReadError)


async def test_errors_a_retry_cannot_fix_are_raised_at_once() -> None:
    gateway = Statuses(httpx.UnsupportedProtocol("nope"))
    async with make(gateway) as client:
        with pytest.raises(TransportError):
            await client.cron.list()
    assert gateway.calls == 1


async def test_a_slow_gateway_times_out() -> None:
    calls = 0

    async def slow(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        await asyncio.sleep(5)
        return httpx.Response(200, json=JOBS)

    async with make(slow, timeout=0.05, retry=RetryPolicy(1, 0.001, 0.001)) as client:
        with pytest.raises(RequestTimeoutError) as err:
            await client.cron.list()
    assert is_transient(err.value)
    assert calls == 2  # a timeout is retried


async def test_the_callers_own_timeout_is_not_the_clients() -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200, json=JOBS)

    async with make(slow, timeout=None) as client:
        with pytest.raises(TimeoutError) as err:
            async with asyncio.timeout(0.05):
                await client.cron.list()
    assert not isinstance(err.value, RequestTimeoutError)


async def test_an_unreachable_gateway_is_a_transient_transport_error() -> None:
    async with Client("http://127.0.0.1:1", retry=RetryPolicy(1, 0.001, 0.001)) as client:
        with pytest.raises(TransportError) as err:
            await client.cron.list()
    assert is_transient(err.value)


async def test_the_timeout_does_not_cut_the_event_stream() -> None:
    async def frames() -> AsyncIterator[bytes]:
        for i in range(3):
            await asyncio.sleep(0.05)
            yield f'data: {{"type":"tick","n":{i}}}\n\n'.encode()

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=frames())

    async with make(handle, timeout=0.02) as client, await client.events.subscribe() as stream:
        assert [e["n"] async for e in stream] == [0, 1, 2]


async def test_middleware_runs_outermost_first() -> None:
    seen: list[str] = []

    def named(name: str) -> Any:
        async def middleware(request: httpx.Request, next_: Handler) -> httpx.Response:
            seen.append(f"{name}>")
            response = await next_(request)
            seen.append(f"<{name}")
            return response

        return middleware

    async with make(Statuses(503, 200), middleware=[named("a"), named("b")]) as client:
        await client.cron.list()
    # Middleware wraps the retries: it sees one logical call.
    assert seen == ["a>", "b>", "<b", "<a"]


async def test_middleware_can_change_requests() -> None:
    async def sign(request: httpx.Request, next_: Handler) -> httpx.Response:
        request.headers["X-Signature"] = "s"
        return await next_(request)

    def handle(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-Signature"] == "s"
        return httpx.Response(200, json=JOBS)

    async with make(handle, middleware=[sign]) as client:
        await client.cron.list()


async def test_a_middleware_that_refuses_is_raised_as_is() -> None:
    class Refused(Exception):
        pass

    async def refuse(request: httpx.Request, next_: Handler) -> httpx.Response:
        raise Refused

    async with make(Statuses(200), middleware=[refuse]) as client:
        with pytest.raises(Refused):
            await client.cron.list()


async def test_the_concurrency_limit_is_shared_by_copies() -> None:
    running = peak = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return httpx.Response(200, json=JOBS)

    async with make(handle, concurrency_limit=2) as client:
        clients = [client, client.with_token("a"), client.with_token("b")]
        await asyncio.gather(*(c.cron.list() for c in clients for _ in range(4)))
    assert peak == 2


async def test_retry_after_is_honored() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        if handle.calls == 0:  # type: ignore[attr-defined]
            handle.calls = 1  # type: ignore[attr-defined]
            return httpx.Response(429, headers={"Retry-After": "1"})
        return httpx.Response(200, json=JOBS)

    handle.calls = 0  # type: ignore[attr-defined]
    policy = RetryPolicy(max_retries=1, base_delay=0.001, max_delay=0.2)
    async with make(handle, retry=policy) as client:
        start = time.monotonic()
        await client.cron.list()
    assert time.monotonic() - start >= 0.2


async def test_the_circuit_breaker_stops_calling_a_failing_gateway() -> None:
    gateway = Statuses(503)
    async with make(
        gateway, retry=RetryPolicy.none(), circuit_breaker=CircuitBreaker(threshold=2, ttl=0.1)
    ) as client:
        for _ in range(2):
            with pytest.raises(APIError):
                await client.cron.list()
        with pytest.raises(CircuitOpenError) as err:
            await client.cron.list()
        assert gateway.calls == 2
        assert is_transient(err.value)
        # After the ttl, a trial call goes through, and closes it when it works.
        gateway.codes = (200,)
        await asyncio.sleep(0.15)
        await client.cron.list()
        await client.cron.list()
    assert gateway.calls == 4


async def test_not_found_does_not_trip_the_breaker() -> None:
    gateway = Statuses(404)
    async with make(gateway, circuit_breaker=CircuitBreaker(threshold=1)) as client:
        for _ in range(3):
            with pytest.raises(APIError):
                await client.cron.list()
    assert gateway.calls == 3


async def test_the_rate_limit_spaces_calls() -> None:
    async with make(Statuses(200), rate_limit=RateLimit(rate=20, burst=1)) as client:
        start = time.monotonic()
        for _ in range(4):
            await client.cron.list()
    assert time.monotonic() - start >= 0.1


async def test_a_wait_past_the_timeout_fails_at_once() -> None:
    gateway = Statuses(200)
    async with make(gateway, timeout=0.05, rate_limit=RateLimit(rate=0.1, burst=1)) as client:
        await client.cron.list()
        with pytest.raises(RateLimitedError) as err:
            await client.cron.list()
    assert gateway.calls == 1
    assert is_transient(err.value)
