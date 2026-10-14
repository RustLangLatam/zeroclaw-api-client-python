"""The exceptions the client raises, and helpers to classify them."""

from __future__ import annotations

import json
from typing import Any

import httpx

__all__ = [
    "APIError",
    "CircuitOpenError",
    "DecodeError",
    "InvalidURLError",
    "RateLimitedError",
    "RequestTimeoutError",
    "TransportError",
    "TurnError",
    "WebSocketError",
    "ZeroClawError",
    "is_not_found",
    "is_rate_limited",
    "is_transient",
    "is_unauthorized",
    "status_code",
]

#: Statuses that ask the client to try again later.
RETRYABLE_STATUSES = frozenset({408, 429, 502, 503, 504})


class ZeroClawError(Exception):
    """Base class of every error the client raises."""


class InvalidURLError(ZeroClawError, ValueError):
    """The gateway URL, or a URL built from it, is not valid."""


class RequestTimeoutError(ZeroClawError, TimeoutError):
    """The gateway did not answer within the client's timeout (after any retries).

    A timeout or cancellation of the caller's own (``asyncio.timeout``) is
    raised as the caller's exception instead.
    """

    def __init__(self, message: str = "the gateway did not answer in time") -> None:
        super().__init__(message)


class DecodeError(ZeroClawError):
    """The gateway answered successfully but the body did not have the expected shape."""


class WebSocketError(ZeroClawError):
    """A WebSocket connection to the gateway failed."""


class CircuitOpenError(ZeroClawError):
    """The circuit breaker refused the call because the gateway kept failing; it was not sent."""


class RateLimitedError(ZeroClawError):
    """The client's own rate limit could not let the call through within its timeout.

    The call was not sent.
    """


class TransportError(ZeroClawError):
    """The request could not reach the gateway or its answer was lost.

    The underlying ``httpx`` error is the ``__cause__``.
    """


class APIError(ZeroClawError):
    """A gateway answer with a non-success status.

    Attributes:
        status: The HTTP status code.
        message: The gateway's own explanation (its ``error`` or ``message``
            field) when the body carries one, otherwise the body text.
        body: The JSON error body, when the gateway sent one.
    """

    status: int
    message: str
    body: Any

    def __init__(self, status: int, message: str, body: Any = None) -> None:
        super().__init__(f"gateway answered {status}: {message}")
        self.status = status
        self.message = message
        self.body = body

    @classmethod
    def from_response(cls, status: int, text: bytes) -> APIError:
        """Build the error from a failed answer's status and body."""
        try:
            body = json.loads(text)
        except ValueError:
            return cls(status, text.decode("utf-8", "replace").strip())
        if isinstance(body, dict):
            for key in ("error", "message"):
                if key in body:
                    value = body[key]
                    message = value if isinstance(value, str) else json.dumps(value)
                    return cls(status, message, body)
        return cls(status, text.decode("utf-8", "replace").strip(), body)


class TurnError(ZeroClawError):
    """An agent turn on the chat that ended in an ``error`` frame, or was aborted.

    Attributes:
        code: The stable code, e.g. ``PROVIDER_ERROR`` or ``ABORTED``; empty
            when the gateway sent none.
        message: What went wrong.
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"agent turn failed: {message}")
        self.code = code
        self.message = message


def status_code(err: BaseException) -> int:
    """Return the HTTP status of an :class:`APIError`, or 0 for any other error."""
    return err.status if isinstance(err, APIError) else 0


def is_not_found(err: BaseException) -> bool:
    """Report whether the gateway answered 404 (the resource does not exist)."""
    return status_code(err) == 404


def is_unauthorized(err: BaseException) -> bool:
    """Report whether the gateway refused the credentials (401) or the action (403)."""
    return status_code(err) in (401, 403)


def is_rate_limited(err: BaseException) -> bool:
    """Report whether the gateway rate-limited the call (429), or the client's own limit did."""
    return status_code(err) == 429 or isinstance(err, RateLimitedError)


def is_transient(err: BaseException) -> bool:
    """Report whether the call may work if made again later.

    True for no connection, a connection dropped before the answer, a
    timeout, a "try again" status (408, 429, 502, 503, 504), an open circuit
    or the client's own rate limit. The client already retried idempotent
    calls before raising it.
    """
    if isinstance(err, APIError):
        return err.status in RETRYABLE_STATUSES
    return isinstance(err, CircuitOpenError | RateLimitedError) or is_retryable_error(err)


def is_retryable_error(err: BaseException) -> bool:
    """Report whether a failure is one a retry may fix.

    No connection, no answer in time, or a connection the gateway dropped
    before answering (it does while it restarts).
    """
    if isinstance(err, RequestTimeoutError):
        return True
    if isinstance(err, TransportError) and err.__cause__ is not None:
        err = err.__cause__
    return isinstance(err, httpx.TimeoutException | httpx.NetworkError | httpx.RemoteProtocolError)
