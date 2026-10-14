"""A mock gateway for the HTTP-boundary tests."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest

from zeroclaw_client import Client, RetryPolicy

#: The token every test client sends.
TOKEN = "zc_" + "0" * 64

Handler = Callable[[httpx.Request], httpx.Response]


def reply(body: Any = None, status: int = 200, headers: dict[str, str] | None = None) -> Handler:
    """Answer ``status`` with ``body``: JSON for a dict or list, text for a string."""

    def handle(_: httpx.Request) -> httpx.Response:
        if isinstance(body, str):
            return httpx.Response(status, text=body, headers=headers)
        return httpx.Response(status, json=body, headers=headers)

    return handle


def body(request: httpx.Request) -> Any:
    """The JSON body of ``request``."""
    return json.loads(request.content)


class Gateway:
    """Answers the routes a test registers and fails the test on any other request."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], tuple[Handler, bool]] = {}
        self.hits: Counter[tuple[str, str]] = Counter()
        self.unexpected: list[str] = []
        self.requests: list[httpx.Request] = []

    def on(self, method: str, path: str, handler: Handler | Any, *, public: bool = False) -> None:
        """Answer ``method`` on ``path`` (escaped, as sent); a non-callable is replied as JSON."""
        if not callable(handler):
            handler = reply(handler)
        self.routes[(method, path)] = (handler, public)

    def calls(self, method: str, path: str) -> int:
        """How many times ``method`` on ``path`` was requested."""
        return self.hits[(method, path)]

    def handle(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.raw_path.split(b"?")[0].decode())
        self.hits[key] += 1
        self.requests.append(request)
        if key not in self.routes:
            self.unexpected.append(f"{key[0]} {key[1]}")
            return httpx.Response(404, text="no such route in the mock")
        handler, public = self.routes[key]
        if not public and request.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.unexpected.append(f"{key[0]} {key[1]}: missing bearer token")
        return handler(request)


@pytest.fixture
def gateway() -> Gateway:
    return Gateway()


@pytest.fixture
async def client(gateway: Gateway) -> AsyncIterator[Client]:
    async with Client(
        "http://gateway.test",
        token=TOKEN,
        transport=httpx.MockTransport(gateway.handle),
        retry=RetryPolicy(max_retries=3, base_delay=0.001, max_delay=0.001),
    ) as c:
        yield c
    assert not gateway.unexpected, gateway.unexpected
