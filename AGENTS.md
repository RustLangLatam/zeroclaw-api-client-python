# AGENTS.md - ZeroClaw API client for Python

Core instructions for AI coding assistants working in this repository. Read `docs/book/src/contributing/architecture.md` before a non-trivial change.

## Single Source Of Truth

The gateway is the source of truth for every request and response shape. This SDK mirrors the router of the ZeroClaw build it targets (`crates/zeroclaw-gateway/src/lib.rs` in ZeroClaw) and never invents fields:

1. Before adding or changing a type, find the gateway handler and the struct (or `json!` literal) it serializes, and name it in the module docstring.
2. Shapes the gateway builds ad hoc, or that change with configuration (config sections, SOP definitions, catalogs), stay `Any` (decoded JSON) instead of guessed models.
3. Optional and newer fields default to `None`, so an older or newer gateway still decodes; unknown fields are ignored.

## Safety And Privacy

- Never commit secrets, tokens, credentials, personal data, or real identities. Tests use invented tokens and hosts.
- The bearer token never appears in `repr`, errors, or URLs.
- A library never prints, logs, or starts tasks that outlive a call: it raises typed errors (`ZeroClawError` subclasses) and leaves streams to the caller.
- Do not keep unused production code; remove it or use it.

## Working Rules

1. Read the owning module, its tests, and the matching gateway handler before editing.
2. One resource group per module (`cron.py`, `config.py`, …), reached from a `Client` attribute; path segments are passed as a list to `Client._call`/`_field`/`_request`, never formatted into a string, so ids are always encoded.
3. Keep one concern per PR. Avoid unrelated cleanup and do not mix broad formatting changes with functional changes.
4. Do not add dependencies for minor convenience. The runtime dependencies are `httpx`, `pydantic`, `tenacity`, `aiolimiter`, `purgatory` and `websockets` ([ADR-005](docs/book/src/architecture/decisions/ADR-005-resilience-dependencies.md)); a new one needs an ADR.
5. Every endpoint gets a test at the HTTP boundary (`tests/test_<area>.py`, against the mock gateway of `tests/conftest.py`) that checks method, path, query, body, and decoding. Logic gets table-driven tests (`pytest.mark.parametrize`). New response types get a captured vector (`scripts/capture-vectors.py`).
6. Work on a non-`main` branch (`feat/*`, `fix/*`, `docs/*`), open a PR to `main`, and never push directly to `main`. Releases are tagged `vX.Y.Z` from `main`; the release workflow publishes to PyPI.
7. Use conventional commits. Commits are authored by the repository owner; do not add bot or AI attribution footers or files.
8. Name no application, company or deployment that uses the client: not in code, docs, test vectors, commits or PRs. Say "an application".

## User-Facing Text

- Code, comments, errors, and documentation are in English.
- English Markdown under `docs/book/` is the documentation source of truth; docstrings (Google style) cover each public name.

## Validation

```bash
ruff format --check .
ruff check .
mypy
pytest --cov
python3 scripts/endpoint-map.py --check
```

Docs changes also build the book: `mdbook build docs/book`.
