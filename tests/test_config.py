from __future__ import annotations

from typing import Any

import httpx
import pytest

from zeroclaw_client import Client
from zeroclaw_client._errors import APIError, is_not_found
from zeroclaw_client._model import encode
from zeroclaw_client.config import (
    AliasSource,
    ConfigAPI,
    PatchOp,
    PropValue,
    add_op,
    comment_op,
    remove_op,
    replace_op,
)
from zeroclaw_client.config import test_op as op_test

from .conftest import Gateway, body, reply


@pytest.mark.parametrize(
    ("op", "want"),
    [
        (replace_op("a.b", 1), {"op": "replace", "path": "a.b", "value": 1}),
        (add_op("agents.x.model", "m"), {"op": "add", "path": "agents.x.model", "value": "m"}),
        (remove_op("/a/b"), {"op": "remove", "path": "/a/b"}),
        (op_test("a", True), {"op": "test", "path": "a", "value": True}),
        (comment_op("a", "why"), {"op": "comment", "path": "a", "comment": "why"}),
        (replace_op("a", ["x", "y"]), {"op": "replace", "path": "a", "value": ["x", "y"]}),
    ],
)
def test_patch_op_vectors(op: PatchOp, want: dict[str, Any]) -> None:
    assert encode(op) == want


@pytest.mark.parametrize(
    ("source", "name"),
    [
        (AliasSource.MODEL_PROVIDERS, "model_providers"),
        (AliasSource.TTS_PROVIDERS, "tts_providers"),
        (AliasSource.TRANSCRIPTION_PROVIDERS, "transcription_providers"),
        (AliasSource.CHANNELS, "channels"),
        (AliasSource.RISK_PROFILES, "risk_profiles"),
        (AliasSource.RUNTIME_PROFILES, "runtime_profiles"),
        (AliasSource.AGENTS, "agents"),
        (AliasSource.SKILL_BUNDLES, "skill_bundles"),
        (AliasSource.KNOWLEDGE_BUNDLES, "knowledge_bundles"),
        (AliasSource.MCP_BUNDLES, "mcp_bundles"),
    ],
)
def test_alias_source_vectors(source: AliasSource, name: str) -> None:
    assert str(source) == name


@pytest.mark.parametrize(
    ("wire", "secret", "value", "populated"),
    [
        ({"path": "gateway.port", "value": "42617"}, False, "42617", None),
        ({"path": "providers.models.x.default.api_key", "populated": True}, True, None, True),
    ],
)
def test_props_decode_as_values_or_secrets(
    wire: dict[str, Any], secret: bool, value: Any, populated: bool | None
) -> None:
    prop = PropValue.model_validate(wire)
    assert prop.is_secret() == secret
    assert prop.value == value
    assert prop.populated == populated


async def test_reads_writes_and_resets_one_field(gateway: Gateway, client: Client) -> None:
    def get(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "gateway.port"
        return reply({"path": "gateway.port", "value": "42617"})(request)

    def put(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"path": "agents.x.model", "value": "m", "comment": "set"}
        return reply({"path": "agents.x.model", "value": "m"})(request)

    def delete(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "providers.models.x.default.api_key"
        return reply({"path": "providers.models.x.default.api_key", "populated": False})(request)

    gateway.on("GET", "/api/config/prop", get)
    gateway.on("PUT", "/api/config/prop", put)
    gateway.on("DELETE", "/api/config/prop", delete)

    config = ConfigAPI(client)
    assert (await config.get("gateway.port")).value == "42617"
    await config.set("agents.x.model", "m", "set")
    reset = await config.reset("providers.models.x.default.api_key")
    assert reset.is_secret()
    assert reset.populated is False


async def test_set_sends_null_and_no_empty_comment(gateway: Gateway, client: Client) -> None:
    def put(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"path": "a", "value": None}
        return reply({"path": "a", "value": None})(request)

    gateway.on("PUT", "/api/config/prop", put)
    assert (await ConfigAPI(client).set("a", None)).value is None


async def test_patches_atomically_and_can_override_drift(gateway: Gateway, client: Client) -> None:
    def patch(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-ZeroClaw-Override-Drift"] == "true"
        assert body(request) == [
            {"op": "replace", "path": "gateway.port", "value": 1},
            {"op": "remove", "path": "agents.x.model"},
        ]
        return reply(
            {
                "saved": True,
                "results": [
                    {"op": "replace", "path": "gateway.port", "value": "1"},
                    {"op": "remove", "path": "agents.x.model", "value": None},
                ],
            }
        )(request)

    gateway.on("PATCH", "/api/config", patch)
    patched = await ConfigAPI(client).patch(
        [replace_op("gateway.port", 1), remove_op("agents.x.model")], override_drift=True
    )
    assert patched.saved
    assert len(patched.results) == 2


async def test_patch_without_override_sends_no_header(gateway: Gateway, client: Client) -> None:
    def patch(request: httpx.Request) -> httpx.Response:
        assert "X-ZeroClaw-Override-Drift" not in request.headers
        return reply({"saved": True, "results": []})(request)

    gateway.on("PATCH", "/api/config", patch)
    assert (await ConfigAPI(client).patch([])).saved


async def test_errors_keep_the_gateways_message(gateway: Gateway, client: Client) -> None:
    gateway.on(
        "GET",
        "/api/config/prop",
        reply({"code": "path_not_found", "message": "no field `x`", "path": "x"}, status=404),
    )
    with pytest.raises(APIError) as caught:
        await ConfigAPI(client).get("x")
    assert is_not_found(caught.value)
    assert str(caught.value) == "gateway answered 404: no field `x`"


async def test_lists_drift_and_status(gateway: Gateway, client: Client) -> None:
    def list_(request: httpx.Request) -> httpx.Response:
        assert request.url.params["prefix"] == "gateway"
        return reply(
            {
                "entries": [
                    {
                        "path": "gateway.port",
                        "category": "gateway",
                        "kind": "integer",
                        "type_hint": "u16",
                        "value": "42617",
                        "populated": True,
                        "is_secret": False,
                    }
                ]
            }
        )(request)

    gateway.on("GET", "/api/config/list", list_)
    gateway.on("GET", "/api/config/drift", {"drifted": [{"path": "a", "drifted": True}]})
    gateway.on("GET", "/api/config/reload-status", {"pending_reload": True})
    gateway.on(
        "GET",
        "/api/config/status",
        {
            "needs_quickstart": False,
            "reason": "has_dispatchable_agent",
            "has_partial_state": False,
            "missing": [],
        },
    )
    gateway.on("GET", "/api/config", {"gateway": {"port": 42617}})

    config = ConfigAPI(client)
    assert (await config.list("gateway")).entries[0].kind == "integer"
    assert (await config.drift())[0].path == "a"
    assert await config.pending_reload()
    assert not (await config.status()).needs_quickstart
    assert (await config.snapshot())["gateway"]["port"] == 42617


async def test_list_without_prefix_sends_no_query(gateway: Gateway, client: Client) -> None:
    def list_(request: httpx.Request) -> httpx.Response:
        assert not request.url.params
        return reply({"entries": []})(request)

    gateway.on("GET", "/api/config/list", list_)
    assert (await ConfigAPI(client).list()).entries == []


async def test_manages_map_aliases(gateway: Gateway, client: Client) -> None:
    def map_keys(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "agents"
        return reply({"path": "agents", "keys": ["a", "b"]})(request)

    def map_key(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "agents"
        assert request.url.params["key"] == "a"
        created = request.method == "POST"
        return reply({"path": "agents", "key": "a", "created": created})(request)

    def delete_plan(request: httpx.Request) -> httpx.Response:
        assert request.url.params["key"] == "a"
        return reply(
            {
                "path": "agents",
                "key": "a",
                "allowed": True,
                "blockers": [],
                "scrubs": [{"path": "heartbeat.agent", "raw_value": "a"}],
                "live_acp_sessions": 0,
                "cascades_owned_state": True,
            }
        )(request)

    def rename(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"path": "agents", "from": "a", "to": "c"}
        return reply({"path": "agents", "from": "a", "to": "c", "renamed": True})(request)

    def alias_source(request: httpx.Request) -> httpx.Response:
        assert request.url.params["source"] == "model_providers"
        return reply({"source": "model_providers", "values": ["openai.default"]})(request)

    gateway.on("GET", "/api/config/map-keys", map_keys)
    gateway.on("POST", "/api/config/map-key", map_key)
    gateway.on("DELETE", "/api/config/map-key", map_key)
    gateway.on("GET", "/api/config/delete-plan", delete_plan)
    gateway.on("POST", "/api/config/rename-map-key", rename)
    gateway.on("GET", "/api/config/resolve-alias-source", alias_source)

    config = ConfigAPI(client)
    assert await config.map_keys("agents") == ["a", "b"]
    assert (await config.create_map_key("agents", "a")).created
    assert not (await config.delete_map_key("agents", "a")).created
    assert len((await config.delete_plan("agents", "a")).scrubs) == 1
    renamed = await config.rename_map_key("agents", "a", "c")
    assert renamed.renamed
    assert renamed.from_ == "a"
    assert await config.alias_values(AliasSource.MODEL_PROVIDERS) == ["openai.default"]


async def test_maintains_the_config_file(gateway: Gateway, client: Client) -> None:
    def init(request: httpx.Request) -> httpx.Response:
        assert request.url.params["section"] == "memory"
        return reply({"initialized": ["memory.sqlite"]})(request)

    gateway.on("POST", "/api/config/init", init)
    gateway.on(
        "POST",
        "/api/config/migrate",
        {"migrated": True, "backup_path": "/c.bak", "schema_version": 3},
    )
    gateway.on(
        "GET",
        "/api/config/templates",
        {
            "templates": [
                {
                    "path": "agents",
                    "kind": "map",
                    "value_type": "AgentConfig",
                    "description": "Agents",
                }
            ]
        },
    )
    gateway.on(
        "POST",
        "/api/config/model-providers/openai/default/refresh-context-window",
        {"path": "providers.models.openai.default", "context_window": 200000},
    )

    config = ConfigAPI(client)
    assert await config.init("memory") == ["memory.sqlite"]
    assert (await config.migrate()).schema_version == 3
    assert (await config.templates())[0].kind == "map"
    assert await config.refresh_context_window("openai", "default") == 200_000


async def test_reads_catalogs_and_sections(gateway: Gateway, client: Client) -> None:
    def models(request: httpx.Request) -> httpx.Response:
        assert request.url.params["model_provider"] == "openai"
        return reply(
            {"model_provider": "openai", "models": ["gpt-x"], "local": False, "live": True}
        )(request)

    def select(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"alias": "main"}
        return reply({"fields_prefix": "channels.whatsapp.main", "created": True})(request)

    gateway.on(
        "GET",
        "/api/config/catalog",
        {"model_providers": [{"name": "openai", "display_name": "OpenAI", "local": False}]},
    )
    gateway.on("GET", "/api/config/catalog/models", models)
    gateway.on(
        "GET",
        "/api/config/agent-options",
        {
            "channels": [],
            "channel_types": [],
            "model_providers": ["openai.default"],
            "risk_profiles": [],
            "runtime_profiles": [],
            "skill_bundles": [],
            "knowledge_bundles": [],
            "mcp_bundles": [],
            "agents": ["helper"],
        },
    )
    gateway.on(
        "GET",
        "/api/config/sections",
        {
            "sections": [
                {
                    "key": "channels",
                    "label": "Channels",
                    "help": "",
                    "has_picker": True,
                    "completed": False,
                }
            ]
        },
    )
    gateway.on(
        "GET",
        "/api/config/sections/channels",
        {
            "section": "channels",
            "help": "",
            "items": [{"key": "whatsapp", "label": "WhatsApp", "badge": "configured"}],
        },
    )
    gateway.on("POST", "/api/config/sections/channels/items/whatsapp", select)

    config = ConfigAPI(client)
    assert (await config.catalog())[0].name == "openai"
    assert (await config.catalog_models("openai")).live
    assert (await config.agent_options()).agents == ["helper"]
    assert (await config.sections())[0].has_picker
    assert (await config.section_items("channels")).items[0].badge == "configured"
    selected = await config.select_section_item("channels", "whatsapp", "main")
    assert selected.fields_prefix == "channels.whatsapp.main"


async def test_select_without_alias_sends_null(gateway: Gateway, client: Client) -> None:
    def select(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"alias": None}
        return reply({"fields_prefix": "memory", "created": False})(request)

    gateway.on("POST", "/api/config/sections/memory/items/sqlite", select)
    assert not (await ConfigAPI(client).select_section_item("memory", "sqlite")).created


async def test_schemas_use_options(gateway: Gateway, client: Client) -> None:
    def prop(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "gateway.port"
        return reply({"x-zeroclaw-prop": {"kind": "integer"}})(request)

    gateway.on("OPTIONS", "/api/config", {"title": "Config"}, public=True)
    gateway.on("OPTIONS", "/api/config/prop", prop, public=True)

    config = ConfigAPI(client)
    assert await config.schema() == {"title": "Config"}
    assert await config.prop_schema("gateway.port") == {"x-zeroclaw-prop": {"kind": "integer"}}
