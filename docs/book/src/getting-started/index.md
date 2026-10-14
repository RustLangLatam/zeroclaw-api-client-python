# Getting Started

## Install

Add the package from [PyPI](https://pypi.org/project/zeroclaw-api-client/):

```sh
pip install zeroclaw-api-client     # or: uv add zeroclaw-api-client
```

and import it as one package:

```python
from zeroclaw_client import Client
```

It needs Python 3.11 or newer
([why](../architecture/decisions/ADR-003-python-floor.md)) and brings six
well-established dependencies: `httpx` (HTTP), `pydantic` (the models),
`websockets` (chat and feeds), `tenacity` (retries), `aiolimiter` (the
optional rate limit) and `purgatory` (the optional circuit breaker)
([why these](../architecture/decisions/ADR-005-resilience-dependencies.md)).

## What you need from the gateway

- **Its URL.** The gateway listens on `127.0.0.1:42617` by default. Behind a
  reverse proxy, or with `[gateway] path_prefix`, use the full base URL
  (`https://host/zeroclaw`): the client appends routes to it.
- **A bearer token**, unless the gateway runs with pairing off. Tokens come
  from pairing: see [Connecting and pairing](./pairing.md).
- **Remote admin rights**, only for `/admin/*` calls from another host:
  those need `[gateway] allow_remote_admin = true` and pairing on.

Then make your [first calls](./first-calls.md).

The client is async only: every call is awaited inside a coroutine run by
`asyncio`. The snippets in this book, past the first calls, run inside an
`async def` with a `client: Client` at hand.
