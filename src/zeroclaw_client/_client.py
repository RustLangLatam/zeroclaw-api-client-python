"""The client: a connection to one ZeroClaw gateway."""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any, Self, TypeVar
from urllib.parse import quote, urlsplit

import httpx

from ._errors import (
    APIError,
    DecodeError,
    InvalidURLError,
    RequestTimeoutError,
    TransportError,
    ZeroClawError,
)
from ._model import decode, encode
from ._transport import (
    TIMEOUT_EXTENSION,
    CircuitBreaker,
    Middleware,
    RateLimit,
    RetryPolicy,
    StackTransport,
)
from ._version import __version__
from .agents import AgentAPI
from .canvas import CanvasAPI
from .channels import ChannelsAPI
from .chat import ChatSession, Feed, open_chat, open_socket
from .config import ConfigAPI
from .cost import CostAPI
from .cron import CronAPI
from .events import EventsAPI
from .files import FilesAPI
from .memory import MemoryAPI
from .pairing import PairingAPI
from .quickstart import QuickstartAPI
from .sessions import SessionsAPI
from .skills import SkillsAPI
from .sops import SopsAPI
from .system import SystemAPI
from .webauthn import WebAuthnAPI
from .webhook import WebhookAPI

__all__ = ["DEFAULT_TIMEOUT", "Client"]

T = TypeVar("T")

#: How long a request waits for the gateway's answer (its headers: a streamed
#: body is not bounded), in seconds. The gateway's own limit is 30 s; calls
#: that do longer work set their own.
DEFAULT_TIMEOUT = 60.0

#: How long opening a connection may take, in seconds.
CONNECT_TIMEOUT = 10.0

#: How much of a failed answer's body is kept for the error.
_ERROR_BODY_LIMIT = 1 << 20

#: Characters a path segment keeps unescaped (as Go's url.PathEscape).
_SEGMENT_SAFE = "!$&'()*+,;=:@"

USER_AGENT = f"zeroclaw-api-client-python/{__version__}"

Query = Mapping[str, str | int | bool | None]


class Client:
    """A connection to one ZeroClaw gateway.

    Use it as an async context manager, or call :meth:`aclose` when done::

        async with Client("http://127.0.0.1:42617", token=token) as client:
            health = await client.system.health()

    It is safe to share between tasks; copies made with :meth:`with_token`
    share the connection pool, the concurrency limit, the rate limit and the
    circuit breaker. Resource groups are reached through attributes such as
    :attr:`cron` or :attr:`config`.

    Args:
        base_url: The gateway's URL, e.g. ``http://127.0.0.1:42617``.
        token: The bearer token sent with every request (obtained by pairing,
            see :attr:`pairing`). Without one, only public endpoints answer.
        timeout: How long a request waits for the gateway's answer, in
            seconds. It bounds the headers only, so the event stream is not
            cut; long gateway calls (a manual cron run) use their own, longer
            limit. ``None`` waits without limit.
        retry: How failed idempotent requests are retried
            (:meth:`RetryPolicy.none` turns retries off).
        concurrency_limit: At most this many requests wait for the gateway's
            answer at once; the rest wait their turn.
        rate_limit: Keep the client under a request rate.
        circuit_breaker: Stop calling a gateway that keeps failing.
        middleware: Wrap every HTTP request in middleware of your own. The
            first is outermost: it sees the request first and the response
            last, around the client's own retry and timeout.
        transport: An ``httpx`` transport to send through (proxy, TLS,
            HTTP/2, a mock in tests); the stack still wraps it. The WebSocket
            chat and feeds open their own connections.

    Raises:
        InvalidURLError: ``base_url`` is not an absolute http or https URL.
    """

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float | None = DEFAULT_TIMEOUT,
        retry: RetryPolicy | None = None,
        concurrency_limit: int | None = None,
        rate_limit: RateLimit | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        middleware: Sequence[Middleware] = (),
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parts = urlsplit(base_url)
        if parts.scheme not in ("http", "https") or not parts.netloc or not parts.hostname:
            raise InvalidURLError(f"{base_url!r} is not an absolute http or https URL")
        # Segments are appended to the base path, so it must not end in "/".
        self._base = f"{parts.scheme}://{parts.netloc}{parts.path.rstrip('/')}"
        self._token = token or None
        self._timeout = timeout
        stack = StackTransport(
            transport or httpx.AsyncHTTPTransport(),
            timeout=timeout,
            retry=retry if retry is not None else RetryPolicy(),
            concurrency_limit=concurrency_limit,
            rate_limit=rate_limit,
            circuit_breaker=circuit_breaker,
            middleware=middleware,
        )
        # The stack bounds the wait for the answer; httpx only bounds the
        # connection and reading the pool.
        self._http = httpx.AsyncClient(
            transport=stack,
            timeout=httpx.Timeout(None, connect=CONNECT_TIMEOUT),
            headers={"User-Agent": USER_AGENT},
            follow_redirects=False,
        )

    def __repr__(self) -> str:
        """Describe the client without its token, so it never reaches logs."""
        return f"Client(base_url={self._base!r}, authenticated={self._token is not None})"

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the connection pool, shared with every copy of the client."""
        await self._http.aclose()

    def with_token(self, token: str | None) -> Client:
        """Return a client for the same gateway and connection pool with another bearer token.

        E.g. the one a pairing just returned.
        """
        other = copy.copy(self)
        other._token = token or None
        return other

    @property
    def base_url(self) -> str:
        """The gateway's base URL."""
        return self._base

    @property
    def timeout(self) -> float | None:
        """How long a request waits for the gateway's answer, in seconds."""
        return self._timeout

    # Resource groups.

    @property
    def cron(self) -> CronAPI:
        """The scheduled jobs endpoints (``/api/cron``)."""
        return CronAPI(self)

    @property
    def events(self) -> EventsAPI:
        """The live event stream endpoints (``/api/events``)."""
        return EventsAPI(self)

    @property
    def canvas(self) -> CanvasAPI:
        """The canvas endpoints (``/api/canvas``)."""
        return CanvasAPI(self)

    @property
    def channels(self) -> ChannelsAPI:
        """The channels and their group chats endpoints (``/api/channels``)."""
        return ChannelsAPI(self)

    @property
    def config(self) -> ConfigAPI:
        """The configuration endpoints (``/api/config``)."""
        return ConfigAPI(self)

    @property
    def cost(self) -> CostAPI:
        """The usage and cost endpoint (``/api/cost``)."""
        return CostAPI(self)

    @property
    def files(self) -> FilesAPI:
        """The shared directory and image uploads (``/api/browse``, ``/api/upload``)."""
        return FilesAPI(self)

    @property
    def memory(self) -> MemoryAPI:
        """The long-term memory endpoints (``/api/memory``)."""
        return MemoryAPI(self)

    @property
    def pairing(self) -> PairingAPI:
        """The pairing and paired devices endpoints (``/api/pair``, ``/api/devices``, …)."""
        return PairingAPI(self)

    @property
    def quickstart(self) -> QuickstartAPI:
        """The first-agent quickstart endpoints (``/api/quickstart``)."""
        return QuickstartAPI(self)

    @property
    def sessions(self) -> SessionsAPI:
        """The conversation sessions endpoints (``/api/sessions``)."""
        return SessionsAPI(self)

    @property
    def skills(self) -> SkillsAPI:
        """The skill bundles and skills (``/api/skills``)."""
        return SkillsAPI(self)

    @property
    def sops(self) -> SopsAPI:
        """The standard operating procedure endpoints (``/api/sops``)."""
        return SopsAPI(self)

    @property
    def system(self) -> SystemAPI:
        """Health, status, diagnostics, logs, versions and administration."""
        return SystemAPI(self)

    @property
    def webauthn(self) -> WebAuthnAPI:
        """The hardware-key registration and assertion endpoints (``/api/webauthn``)."""
        return WebAuthnAPI(self)

    @property
    def webhook(self) -> WebhookAPI:
        """The generic webhook and A2A endpoints (``/webhook``, ``/a2a``)."""
        return WebhookAPI(self)

    def agent(self, alias: str) -> AgentAPI:
        """Return the endpoints of agent ``alias`` (workspace, personality, skills)."""
        return AgentAPI(self, alias)

    async def chat(
        self,
        alias: str,
        *,
        session_id: str | None = None,
        name: str | None = None,
        cwd: str | None = None,
    ) -> ChatSession:
        """Open a chat with agent ``alias`` (GET /ws/chat, upgraded to a WebSocket).

        Waits for the gateway to confirm the session. ``session_id`` resumes
        or creates that session (a new one without it), ``name`` names it and
        ``cwd`` is its working directory (it must exist on the host). Close
        the session when done, or use it as an async context manager.
        """
        return await open_chat(self, alias, session_id, name, cwd)

    async def _feed(self, *segments: str) -> Feed:
        """Open a server-push WebSocket feed on ``segments``."""
        return Feed(await open_socket(self, segments))

    # Requests.

    def _url(self, segments: Sequence[str], base: str | None = None) -> str:
        """Return the URL of ``segments`` under the base, each percent-encoded.

        An id holding ``/`` or ``?`` stays one segment.
        """
        path = "".join("/" + quote(s, safe=_SEGMENT_SAFE) for s in segments)
        return (base or self._base) + path

    def _headers(self, extra: Mapping[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        if self._token is not None:
            headers["Authorization"] = f"Bearer {self._token}"
        return headers

    def _build(
        self,
        method: str,
        segments: Sequence[str],
        *,
        query: Query | None = None,
        json_body: Any = None,
        content: bytes | None = None,
        files: Any = None,
        headers: Mapping[str, str] | None = None,
        timeout: float | None = None,
    ) -> httpx.Request:
        params = {k: _query_value(v) for k, v in (query or {}).items() if v is not None}
        extra = dict(headers or {})
        body: bytes | None = content
        if json_body is not None:
            body = json.dumps(encode(json_body), separators=(",", ":")).encode()
            extra.setdefault("Content-Type", "application/json")
        request = self._http.build_request(
            method,
            self._url(segments),
            params=params or None,
            content=body,
            files=files,
            headers=self._headers(extra),
        )
        if timeout is not None:
            request.extensions[TIMEOUT_EXTENSION] = timeout
        return request

    async def _send(self, request: httpx.Request, *, stream: bool = False) -> httpx.Response:
        """Send ``request``, turning a non-success status into an :class:`APIError`.

        With ``stream``, the caller reads and closes the answer's body.
        """
        try:
            response = await self._http.send(request, stream=True)
        except ZeroClawError:
            raise
        except httpx.TimeoutException as exc:
            raise RequestTimeoutError() from exc
        except httpx.HTTPError as exc:
            raise TransportError(f"request to the gateway failed: {exc}") from exc
        if 200 <= response.status_code < 300:
            if not stream:
                try:
                    await response.aread()
                except httpx.HTTPError as exc:
                    raise TransportError(
                        f"request to the gateway failed: reading the answer: {exc}"
                    ) from exc
                finally:
                    await response.aclose()
            return response
        try:
            text = b""
            async for chunk in response.aiter_bytes():
                text += chunk
                if len(text) >= _ERROR_BODY_LIMIT:
                    break
        except httpx.HTTPError:
            pass
        finally:
            await response.aclose()
        raise APIError.from_response(response.status_code, text[:_ERROR_BODY_LIMIT])

    async def _request(self, method: str, segments: Sequence[str], **kwargs: Any) -> httpx.Response:
        """Build and send a request; the answer's body is read."""
        return await self._send(self._build(method, segments, **kwargs))

    async def _json(self, method: str, segments: Sequence[str], **kwargs: Any) -> Any:
        """Make a call and return its JSON answer (``None`` for an empty body)."""
        response = await self._request(method, segments, **kwargs)
        if not response.content.strip():
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise DecodeError(f"unexpected gateway response: {exc}") from exc

    async def _call(self, method: str, segments: Sequence[str], tp: type[T], **kwargs: Any) -> T:
        """Make a JSON call and decode its answer as ``tp``."""
        return decode(await self._json(method, segments, **kwargs), tp)

    async def _field(
        self, method: str, segments: Sequence[str], name: str, tp: type[T], **kwargs: Any
    ) -> T:
        """Make a JSON call and decode only one field of its envelope as ``tp``.

        E.g. ``jobs`` of ``{"jobs": [...]}``.
        """
        envelope = await self._json(method, segments, **kwargs)
        if not isinstance(envelope, dict) or name not in envelope:
            raise DecodeError(f"unexpected gateway response: missing field {name!r}")
        return decode(envelope[name], tp)

    async def _text(self, method: str, segments: Sequence[str], **kwargs: Any) -> str:
        """Make a call and return its body as text."""
        return (await self._request(method, segments, **kwargs)).text


def _query_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
