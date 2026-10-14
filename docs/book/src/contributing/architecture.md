# Contributing

Read [`AGENTS.md`](https://github.com/RustLangLatam/zeroclaw-api-client-python/blob/main/AGENTS.md)
first: it holds the rules every change follows. This page explains the most
common change, covering a gateway route.

## Adding or changing an endpoint

1. **Find the handler.** In the ZeroClaw build listed in
   [Compatibility](../reference/compatibility.md), find the route in
   `crates/zeroclaw-gateway/src/lib.rs` and read its handler: auth, query,
   body, every status it answers, and the struct or `json!` it returns.
2. **Pick the module.** Routes belong to the module of their area
   (`config.py`, `channels.py`, …). A new area gets a new module, a class
   holding the client, and a property on `Client`.
3. **Write the method.** It is `async`, and its docstring names the route
   (`"""Run a job now and wait for it (POST /api/cron/{id}/run)."""`). Pass
   the path as a list of segments to `self._c._call` (or `_json`, `_field`,
   `_request`), never a formatted string. Unwrap single-field envelopes
   with `_field` (`{"jobs": […]}` returns `list[CronJob]`).
4. **Write the types.** Mirror the gateway's fields in a `Model`; default
   anything optional or newer to `None`; type dynamic shapes `Any`
   ([ADR-002](../architecture/decisions/ADR-002-dynamic-shapes-stay-json.md)).
   Export new public names from `__init__.py`.
5. **Test it.** Add the call to the area's `tests/test_<area>.py`, against
   the mock gateway of `tests/conftest.py`: assert the method, path, query
   and body the gateway expects, and decode a body copied from the handler.
   Capture a response vector for new types (see [Testing](./testing.md)).
6. **Update the docs.** Regenerate the [endpoint map](../reference/endpoints.md)
   with `python3 scripts/endpoint-map.py --write` (CI fails while it is
   stale), and update the guide of the area.

## Checks

```sh
uv sync
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest --cov
uvx pip-audit
python3 scripts/endpoint-map.py --check
mdbook build docs/book
```

CI runs the tests on Python 3.11, 3.12, 3.13 and 3.14, and once with the
lowest dependency versions.

## Branches and pull requests

Branch from `main` (`feat/*`, `fix/*`, `docs/*`) and open a PR with the
template filled in; never push to `main` directly. Use conventional
commits. Releases are tagged `vX.Y.Z` from `main` (the tag must match
`src/zeroclaw_client/_version.py`); the release workflow builds the package
and publishes it to PyPI, and `CHANGELOG.md` gets the release's entry.
