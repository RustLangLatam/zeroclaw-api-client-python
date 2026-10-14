# Compatibility

## ZeroClaw versions

The client targets the ZeroClaw **0.8.5** gateway. It is verified against the
RustLangLatam fork's production build, `0.8.5+unified.13` (branch
`fix/whatsapp-silence-stopped-channel`), whose router is the
[source of truth](../architecture/decisions/ADR-001-gateway-is-the-source-of-truth.md)
for every request and response shape here.

Against an upstream ZeroClaw 0.8.5 build everything works except these
routes, which the fork adds; upstream answers them with its web UI fallback
or 404:

| Route | Method |
|---|---|
| `POST /api/channels/{channel}/send` | `client.channels.send` |
| `GET /api/channels/{channel}/rooms` | `client.channels.rooms` |
| `POST /api/channels/{channel}/rooms` | `client.channels.create_room` |
| `GET /api/channels/{channel}/rooms/{room}/members` | `client.channels.room_members` |
| `POST /api/channels/{channel}/rooms/{room}/invites` | `client.channels.invite` |
| `DELETE /api/channels/{channel}/rooms/{room}/members/{user}` | `client.channels.remove_member` |

Some routes exist only when the gateway is built with a feature: WebAuthn
(`webauthn`) and A2A (`a2a`). Without it they answer 404.

Response models decode leniently: fields a gateway adds are ignored, and
optional or newer fields default to `None`, so a nearby build still decodes.

## Python

The minimum supported Python version is **3.11**, the `requires-python` of
`pyproject.toml` ([ADR-003](../architecture/decisions/ADR-003-python-floor.md)).
CI tests on 3.11, 3.12, 3.13 and 3.14, and once on 3.11 with the lowest
dependency versions `pyproject.toml` allows.

## Runtime

The client runs on `asyncio`. HTTP goes through
[httpx](https://www.python-httpx.org/), over the standard library's `ssl`;
WebSockets use [websockets](https://websockets.readthedocs.io/); models
are [pydantic v2](https://docs.pydantic.dev/), whose core ships as prebuilt
wheels for the common platforms. Retries use
[tenacity](https://tenacity.readthedocs.io/); the optional rate limit and
circuit breaker use [aiolimiter](https://github.com/mjpieters/aiolimiter)
and [purgatory](https://github.com/mardiros/purgatory)
([ADR-005](../architecture/decisions/ADR-005-resilience-dependencies.md)).
