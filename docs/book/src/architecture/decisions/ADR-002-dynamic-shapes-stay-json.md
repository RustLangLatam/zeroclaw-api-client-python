---
id: ADR-002
title: Dynamic shapes stay JSON
date: 2026-10-14
status: accepted
relates-to:
  - src/zeroclaw_client/sops.py
  - src/zeroclaw_client/config.py
---

# ADR-002: Dynamic Shapes Stay JSON

## Context

Some gateway payloads are large, change with every ZeroClaw release, or
depend on the configuration: the whole-config snapshot and its JSON Schema,
SOP definitions, graphs and run overlays, quickstart submissions, skill front
matter, log and event frames, WebAuthn ceremonies.

## Decision

Those stay decoded JSON in the client, typed `Any` (dicts, lists and
scalars as `json` produces them; an `Event` is a `dict[str, Any]`), and
requests that send them take `Any`. Stable, small shapes (channels,
sessions, cron jobs, memory entries, cost, devices, …) are pydantic models.
Models decode leniently: unknown fields are ignored and optional or newer
ones default to `None`.

## Consequences

- A ZeroClaw upgrade that reshapes an SOP or a config section does not break
  the client.
- Callers of the JSON-shaped calls read the value themselves (as a dict, or
  validated into a model of their own with pydantic); the docstring of each
  call lists its top-level fields.
- A shape can move from `Any` to a model later, as a breaking change, when
  it has stabilized upstream.
