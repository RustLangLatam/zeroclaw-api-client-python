# Testing

Four layers of tests, each catching what the others cannot:

| Kind | Where | Catches |
|---|---|---|
| Parametrized tests | `tests/test_*.py`, next to the area | logic mistakes: parsing, mapping, decisions |
| HTTP boundary | `tests/test_<area>.py`, against the mock gateway in `tests/conftest.py` | wrong method, path, query or body; decoding of the documented shape |
| Response vectors | `tests/vectors/*.json` + `tests/test_vectors.py` | models that do not match what a real gateway sends |
| Live | tests marked `live`, run with `pytest -m live` | anything a real gateway does differently today |

Run them (all but the live ones) with:

```sh
uv run pytest
```

## Parametrized tests

Logic is tested as a table of cases (`pytest.mark.parametrize`) and one
assertion, so a new case is one line and a failure names the case:

```python
@pytest.mark.parametrize(
    ("status", "want"),
    [(200, False), (400, False), (408, True), (429, True), (500, False), (503, True)],
)
def test_retryable_status_vectors(status: int, want: bool) -> None:
    assert (status in RETRYABLE_STATUSES) is want
```

## The mock gateway

`tests/conftest.py` provides a `gateway` fixture, a `Gateway` that answers
only the routes a test registers (`gateway.on("GET", "/api/cron", {...})`),
records every request, and fails the test on any other route or a missing
bearer token; and a `client` fixture, a `Client` sending to it through
`httpx.MockTransport`. The chat tests run an in-test WebSocket gateway.

## Response vectors

`scripts/capture-vectors.py` calls the gateway's read-only routes and saves
each answer, anonymized, as `{"route", "build", "response"}`. Phone numbers,
ids, UUIDs, tokens, IPs and e-mails are replaced; `ZEROCLAW_REDACT` replaces
the words of your own deployment (aliases, names); MCP tools and routes that
hold people's words (logs, memory, transcripts) are left out. Review the
files before committing them.

```sh
ZEROCLAW_URL=http://127.0.0.1:42617 ZEROCLAW_TOKEN=zc_… \
  ZEROCLAW_AGENT=<alias> ZEROCLAW_REDACT=<your,own,names> \
  python3 scripts/capture-vectors.py
uv run pytest tests/test_vectors.py -v
```

`tests/test_vectors.py` decodes every file into the type its `TABLE` names,
and re-encodes it to check nothing is lost. A vector without a type fails
the test, so a new capture is never silently untested.

## Live

Tests marked `live` run against a real gateway; the default run leaves them
out (`addopts = "-m 'not live'"`). The read-only test (`tests/test_live.py`)
checks that every model decodes real answers; `ZEROCLAW_AGENT` adds the
per-agent reads:

```sh
ZEROCLAW_URL=http://127.0.0.1:42617 ZEROCLAW_TOKEN=zc_… \
  uv run pytest -m live tests/test_live.py -v
```

The write tests (`tests/test_live_write.py`) exercise every other route
against a real gateway. Each creates what it needs under the `sdk-py-test`
prefix and removes it afterwards; they only run with `ZEROCLAW_WRITE=1`, and
start agent turns (chat, webhook, A2A: they spend model tokens) only with
`ZEROCLAW_TURNS=1`:

```sh
ZEROCLAW_URL=… ZEROCLAW_TOKEN=… ZEROCLAW_AGENT=<alias> \
  ZEROCLAW_WRITE=1 ZEROCLAW_TURNS=1 uv run pytest -m live tests/test_live_write.py -v
```

Tests skip what the gateway does not offer:

| Test | Needs |
|---|---|
| `test_live_sops` | `[sop] sops_dir` set, and the admin routes (the engine loads SOPs on a daemon reload) |
| `test_live_admin` | pytest running on the gateway host: admin routes answer loopback only. For a gateway in Docker, run it in the gateway's network namespace (`docker run --network container:<gateway>`) |
| `test_live_a2a` | `a2a.server.enabled = true` and the agent's `a2a.published = true` |
| `test_live_webauthn` | a ZeroClaw built with `--features webauthn` and `security.webauthn.enabled = true`. The test signs with a software ES256 authenticator (the `cryptography` dev dependency): it registers, authenticates twice, checks that a replayed counter and a forged signature are refused, and deletes the key |

Never run them against a gateway you cannot afford to have changed: a run
cut short may leave `sdk-py-test` leftovers. Channel writes (sending, group
chats, relinking), `shutdown`, `upgrade`, `quickstart.apply`, `config.init`
and `select_section_item` are not exercised live: they reach real people or
reconfigure the instance. The mock gateway covers them.
