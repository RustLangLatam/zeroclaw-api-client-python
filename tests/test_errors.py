from __future__ import annotations

from typing import Any

import httpx
import pytest

from zeroclaw_client import (
    APIError,
    CircuitOpenError,
    DecodeError,
    RateLimitedError,
    RequestTimeoutError,
    TransportError,
    is_not_found,
    is_rate_limited,
    is_transient,
    is_unauthorized,
    status_code,
)
from zeroclaw_client._errors import is_retryable_error


@pytest.mark.parametrize(
    ("text", "message", "body"),
    [
        (b'{"error":"agent not found"}', "agent not found", {"error": "agent not found"}),
        (b'{"message":"bad input"}', "bad input", {"message": "bad input"}),
        (b'{"error":{"code":7}}', '{"code": 7}', {"error": {"code": 7}}),
        (b'{"other":1}', '{"other":1}', {"other": 1}),
        (b"[1]", "[1]", [1]),
        (b"  plain text\n", "plain text", None),
        (b"", "", None),
    ],
)
def test_gateway_error_body_vectors(text: bytes, message: str, body: Any) -> None:
    err = APIError.from_response(400, text)
    assert err.status == 400
    assert err.message == message
    assert err.body == body
    assert str(err) == f"gateway answered 400: {message}"


@pytest.mark.parametrize(
    ("status", "found", "unauthorized", "limited", "transient"),
    [
        (404, True, False, False, False),
        (401, False, True, False, False),
        (403, False, True, False, False),
        (429, False, False, True, True),
        (503, False, False, False, True),
        (500, False, False, False, False),
    ],
)
def test_api_error_classification(
    status: int, found: bool, unauthorized: bool, limited: bool, transient: bool
) -> None:
    err = APIError(status, "x")
    assert status_code(err) == status
    assert is_not_found(err) is found
    assert is_unauthorized(err) is unauthorized
    assert is_rate_limited(err) is limited
    assert is_transient(err) is transient


def wrapped(cause: Exception) -> TransportError:
    err = TransportError("request to the gateway failed")
    err.__cause__ = cause
    return err


@pytest.mark.parametrize(
    ("err", "retryable", "transient"),
    [
        (RequestTimeoutError(), True, True),
        (wrapped(httpx.ConnectError("refused")), True, True),
        (wrapped(httpx.ReadError("reset")), True, True),
        (wrapped(httpx.RemoteProtocolError("closed")), True, True),
        (wrapped(httpx.ReadTimeout("slow")), True, True),
        (wrapped(httpx.UnsupportedProtocol("ftp")), False, False),
        (httpx.ConnectError("refused"), True, True),
        (CircuitOpenError(), False, True),
        (RateLimitedError(), False, True),
        (DecodeError(), False, False),
        (ValueError(), False, False),
    ],
)
def test_retryable_error_vectors(err: Exception, retryable: bool, transient: bool) -> None:
    assert is_retryable_error(err) is retryable
    assert is_transient(err) is transient
    assert status_code(err) == 0


def test_rate_limited_covers_the_clients_own_limit() -> None:
    assert is_rate_limited(RateLimitedError())


def test_timeouts_are_builtin_timeouts() -> None:
    assert isinstance(RequestTimeoutError(), TimeoutError)
