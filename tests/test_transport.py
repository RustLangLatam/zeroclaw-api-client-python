from __future__ import annotations

import email.utils

import httpx
import pytest

from zeroclaw_client import RetryPolicy
from zeroclaw_client._errors import RETRYABLE_STATUSES
from zeroclaw_client._transport import is_idempotent, retry_after

NOW = 1_791_979_200.0  # 2026-10-14T12:00:00Z


@pytest.mark.parametrize(
    ("method", "want"),
    [
        ("GET", True),
        ("HEAD", True),
        ("OPTIONS", True),
        ("PUT", True),
        ("DELETE", True),
        ("POST", False),
        ("PATCH", False),
    ],
)
def test_idempotency_vectors(method: str, want: bool) -> None:
    assert is_idempotent(method) is want


@pytest.mark.parametrize(
    ("status", "want"),
    [
        *[(200, False), (204, False), (400, False), (401, False), (404, False), (408, True)],
        *[(409, False), (429, True), (500, False), (502, True), (503, True), (504, True)],
    ],
)
def test_retryable_status_vectors(status: int, want: bool) -> None:
    assert (status in RETRYABLE_STATUSES) is want


@pytest.mark.parametrize(
    ("attempt", "seconds"),
    [(0, 0.1), (1, 0.2), (2, 0.4), (3, 0.8), (4, 1.0), (9, 1.0), (40, 1.0), (10_000, 1.0)],
)
def test_backoff_vectors(attempt: int, seconds: float) -> None:
    policy = RetryPolicy(max_retries=10, base_delay=0.1, max_delay=1.0, jitter=False)
    assert policy.delay(attempt) == pytest.approx(seconds)


def test_no_retries_never_waits() -> None:
    assert RetryPolicy.none().delay(3) == 0
    assert RetryPolicy.none().max_retries == 0


def test_jittered_waits_stay_in_the_upper_half() -> None:
    policy = RetryPolicy(max_retries=5, base_delay=0.1, max_delay=1.0, jitter=True)
    for attempt in range(5):
        full = policy.delay(attempt)
        for _ in range(100):
            assert full / 2 <= policy.wait(attempt, None) <= full
    assert RetryPolicy().jitter


def answer(status: int, header: str | None) -> httpx.Response:
    headers = {"Retry-After": header} if header is not None else {}
    return httpx.Response(status, headers=headers)


@pytest.mark.parametrize(
    ("response", "want"),
    [
        (answer(429, "3"), 3.0),
        (answer(503, "1"), 1.0),
        (answer(503, email.utils.formatdate(NOW + 2, usegmt=True)), 2.0),
        (answer(503, email.utils.formatdate(NOW - 1, usegmt=True)), 0.0),
        (answer(502, "3"), 0.0),
        (answer(429, None), 0.0),
        (answer(429, "soon"), 0.0),
        (answer(429, "-1"), 0.0),
        (None, 0.0),
    ],
)
def test_retry_after_vectors(response: httpx.Response | None, want: float) -> None:
    assert retry_after(response, NOW) == pytest.approx(want)


def test_retry_after_is_honored_but_capped() -> None:
    policy = RetryPolicy(base_delay=0.001, max_delay=2.0, jitter=False)
    assert policy.wait(0, answer(429, "60")) == 2.0
