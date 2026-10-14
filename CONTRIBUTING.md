# Contributing to zeroclaw-api-client-python

Thanks for your interest. Every kind of contribution helps: code, docs, bug
reports and reports of gateway changes the client does not follow yet.

All PRs target **`main`**; never push to it directly.

1. **Find the gateway side.** Every change starts from the ZeroClaw build the
   client targets ([Compatibility](docs/book/src/reference/compatibility.md)):
   the route in `crates/zeroclaw-gateway/src/lib.rs` and its handler.
2. **Branch.** `feat/*`, `fix/*` or `docs/*` from `main`.
3. **Change, test, document.** Follow [AGENTS.md](AGENTS.md) and the
   step-by-step guide in
   [docs/book/src/contributing/architecture.md](docs/book/src/contributing/architecture.md).
4. **Open the PR** with the template filled in and conventional commit titles
   (`feat: …`, `fix: …`, `docs: …`). Commits are authored by the repository
   owner. Name no application or company that uses the client. Add what
   changed for users to `CHANGELOG.md`.

## Setup

The project uses [uv](https://docs.astral.sh/uv/):

```sh
uv sync    # creates .venv with the package and its dev dependencies
```

## Checks

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov
uvx pip-audit
python3 scripts/endpoint-map.py --check
mdbook build docs/book
```

`ruff format .` and `ruff check --fix .` fix what they can.

Against a running gateway, the read-only live test checks that every model
decodes real answers:

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

What each test needs from the gateway, and what is never exercised live, is
in [Testing](docs/book/src/contributing/testing.md#live). Never run them
against a gateway you cannot afford to have changed: a run cut short may
leave `sdk-py-test` leftovers.
