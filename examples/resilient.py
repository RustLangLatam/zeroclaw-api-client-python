"""Timeouts, retries, rate limit, circuit breaker, concurrency limit and a custom middleware."""

import asyncio
import os
import sys
import time

import httpx

from zeroclaw_client import (
    CircuitBreaker,
    CircuitOpenError,
    Client,
    Handler,
    RateLimit,
    RequestTimeoutError,
    RetryPolicy,
    ZeroClawError,
    is_transient,
)


async def timed(request: httpx.Request, next_: Handler) -> httpx.Response:
    """Log how long each call took, retries included."""
    start = time.monotonic()
    try:
        return await next_(request)
    finally:
        took = (time.monotonic() - start) * 1000
        print(f"  {request.method} {request.url.path} {took:.0f} ms", file=sys.stderr)


async def main() -> None:
    url = os.environ.get("ZEROCLAW_URL", "http://127.0.0.1:42617")
    async with Client(
        url,
        token=os.environ.get("ZEROCLAW_TOKEN"),
        timeout=10,
        retry=RetryPolicy(max_retries=5, base_delay=0.25, max_delay=8),
        concurrency_limit=4,
        rate_limit=RateLimit(rate=10, burst=10),
        circuit_breaker=CircuitBreaker(threshold=5, ttl=15),
        middleware=[timed],
    ) as client:
        try:
            status = await client.system.status()
            print(f"ZeroClaw {status.version} up {status.uptime_seconds}s")
        except CircuitOpenError as err:
            print("the gateway keeps failing; not calling it for now:", err)
        except RequestTimeoutError as err:
            print("no answer even after retries:", err)
        except ZeroClawError as err:
            if not is_transient(err):
                raise
            print("still unavailable:", err)

        # The client is safe to share between tasks: eight calls share the
        # connection pool, and at most four wait for an answer at once.
        async def count() -> None:
            try:
                print(f"{len(await client.channels.list())} channels")
            except ZeroClawError as err:
                print("channels:", err)

        async with asyncio.TaskGroup() as tasks:
            for _ in range(8):
                tasks.create_task(count())


asyncio.run(main())
