"""Response vectors.

Answers captured from a real gateway (``scripts/capture-vectors.py``,
anonymized) must decode into the SDK's models, and re-encode without losing a
field.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

import pytest
from pydantic import TypeAdapter

import zeroclaw_client as z

VECTORS = pathlib.Path(__file__).parent / "vectors"

#: Every vector, with the envelope field the SDK unwraps (if any) and the type
#: that field decodes into.
TABLE: dict[str, tuple[str, Any]] = {
    "health": ("", z.Health),
    "runtime_health": ("health", z.HealthSnapshot),
    "status": ("", z.Status),
    "channels": ("channels", list[z.Channel]),
    "config_list": ("", z.ConfigList),
    "config_drift": ("drifted", list[z.DriftEntry]),
    "config_reload_status": ("pending_reload", bool),
    "config_templates": ("templates", list[z.TemplateEntry]),
    "config_map_keys": ("keys", list[str]),
    "config_catalog": ("model_providers", list[z.CatalogModelProvider]),
    "config_status": ("", z.ConfigStatus),
    "config_agent_options": ("", z.AgentOptions),
    "config_sections": ("sections", list[z.ConfigSection]),
    "cron_list": ("jobs", list[z.CronJob]),
    "cron_settings": ("", z.CronSettings),
    "cost": ("cost", z.CostSummary),
    "sessions": ("sessions", list[z.Session]),
    "events_history": ("events", list[dict[str, Any]]),
    "tools": ("tools", list[z.ToolSpec]),
    "integrations": ("integrations", list[z.Integration]),
    "integration_settings": ("settings", dict[str, z.IntegrationSetting]),
    "skill_bundles": ("bundles", list[z.SkillBundle]),
    "slash_option_kinds": ("kinds", list[Any]),
    "quickstart_state": ("", Any),
    "tuis": ("tuis", list[z.Tui]),
    "devices": ("devices", list[z.Device]),
    "personality_files": ("", z.PersonalityFiles),
    "agent_skills": ("", z.AgentSkills),
}


def decodes(tp: Any, raw: Any) -> None:
    """Decode ``raw`` as ``tp`` and check that encoding it back keeps every field ``raw`` has."""
    adapter: TypeAdapter[Any] = TypeAdapter(tp)
    again = adapter.dump_python(adapter.validate_python(raw), mode="json", by_alias=True)
    kept("", raw, again)


def kept(at: str, before: Any, after: Any) -> None:
    """Fail on the first non-null value of ``before`` that ``after`` lacks."""
    if isinstance(before, dict):
        assert isinstance(after, dict), f"{at}: object became {after!r}"
        for key, value in before.items():
            kept(f"{at}.{key}", value, after.get(key))
    elif isinstance(before, list):
        assert isinstance(after, list), f"{at}: array became {after!r}"
        assert len(after) == len(before), f"{at}: array became {after!r}"
        for i, (b, a) in enumerate(zip(before, after, strict=True)):
            kept(f"{at}[{i}]", b, a)
    elif before is not None:
        assert before == after, f"{at}: {before!r} became {after!r}"


def vectors() -> dict[str, dict[str, Any]]:
    out = {f.stem: json.loads(f.read_text()) for f in sorted(VECTORS.glob("*.json"))}
    assert len(out) >= 20
    return out


@pytest.mark.parametrize(("name", "vector"), vectors().items())
def test_every_captured_answer_decodes(name: str, vector: dict[str, Any]) -> None:
    assert name in TABLE, f"{name}: no type for this vector; add it to the table"
    field, tp = TABLE[name]
    raw = vector["response"][field] if field else vector["response"]
    decodes(tp, raw)


@pytest.mark.parametrize(("name", "vector"), vectors().items())
def test_vectors_record_their_route_and_build(name: str, vector: dict[str, Any]) -> None:
    assert vector["route"].startswith("/")
    assert vector["build"]


@pytest.mark.parametrize("name", [f.name for f in VECTORS.glob("*.json")])
def test_anonymization_leaves_the_wire_format_intact(name: str) -> None:
    # A placeholder glued into a timestamp or a UUID means the anonymizer
    # rewrote something that was not a phone number.
    text = (VECTORS / name).read_text()
    for artifact in (".+34", "-+34", ":+34", "T+34"):
        assert artifact not in text


def test_a_lost_field_is_caught() -> None:
    settings = {"enabled": True, "catch_up_on_startup": False, "max_run_history": 5}
    with pytest.raises(AssertionError):
        decodes(z.CronSettings, {**settings, "not_modeled": 1})
    decodes(z.CronSettings, {**settings, "not_modeled": None})
