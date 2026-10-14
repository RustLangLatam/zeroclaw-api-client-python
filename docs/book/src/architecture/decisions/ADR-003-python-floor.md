---
id: ADR-003
title: Python 3.11 floor
date: 2026-10-14
status: accepted
relates-to:
  - pyproject.toml
  - .github/workflows/ci.yml
---

# ADR-003: Python 3.11 Floor

## Context

The client is meant to be embedded in other applications, and those often
run on older interpreters than the latest Python release. Every dependency
added to the client becomes one of theirs too.

At the same time, the client is built on `asyncio`, and Python 3.11 is the
release that made structured async code practical in the standard library:

- `asyncio.timeout`, which the deadline and the rate limit of the transport
  stack use, and which callers use to bound a call;
- `asyncio.TaskGroup`, for callers fanning calls out over one client;
- `typing.Self`, for the async context managers and iterators;
- `enum.StrEnum`, for string enumerations such as `AliasSource`.

Python 3.10 reaches its end of life in October 2026: it gets no security
fixes after that.

## Decision

`pyproject.toml` declares `requires-python = ">=3.11"`, ruff and mypy
target 3.11, and CI tests on 3.11 and every later release (3.12, 3.13,
3.14), plus a run on 3.11 with the lowest dependency versions
`pyproject.toml` allows. The runtime dependencies
([ADR-005](./ADR-005-resilience-dependencies.md)) all support 3.11.

## Consequences

- New dependencies, or newer minimums of the current ones, must support
  3.11, or the floor moves in a recorded change.
- Standard-library APIs and language features newer than 3.11 (`type`
  statements, PEP 695 generics) are not used.
- A new dependency needs a reason a few lines of code cannot meet.
