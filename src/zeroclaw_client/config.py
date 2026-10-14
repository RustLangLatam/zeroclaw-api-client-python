"""Configuration: per-property reads and writes, atomic JSON Patch batches.

Also map aliases (agents, providers, channels…), drift, catalogs and the
quickstart sections.

Gateway handlers: ``crates/zeroclaw-gateway/src/api_config.rs`` and
``api_sections.rs``. Property paths are dotted
(``providers.models.openai.default.api_key``). Reads return values as the
gateway's display strings; writes take typed JSON, which the gateway coerces
to the field's kind. Secrets are never returned: their reads say only whether
they are populated.
"""

from __future__ import annotations

import builtins
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import Field

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = [
    "AgentOptions",
    "AliasSource",
    "CatalogModelProvider",
    "CatalogModels",
    "ConfigAPI",
    "ConfigEntry",
    "ConfigList",
    "ConfigSection",
    "ConfigStatus",
    "DeletePlan",
    "DriftEntry",
    "MapKeyResponse",
    "MigrateResponse",
    "ModelPricing",
    "PatchOp",
    "PatchOpResult",
    "PatchResponse",
    "PropValue",
    "ReferenceSite",
    "RenameResponse",
    "SectionItem",
    "SectionItems",
    "SelectedItem",
    "TemplateEntry",
    "ValidationWarning",
    "add_op",
    "comment_op",
    "remove_op",
    "replace_op",
    "test_op",
]

#: The header that lets :meth:`ConfigAPI.patch` overwrite paths changed on
#: disk since the gateway loaded them.
OVERRIDE_DRIFT_HEADER = "X-ZeroClaw-Override-Drift"


class ValidationWarning(Model):
    """A validation problem the gateway reports without refusing the write."""

    #: Stable, e.g. ``pre_existing_validation_error``.
    code: str
    #: What is wrong.
    message: str
    #: The field concerned.
    path: str


class PropValue(Model):
    """A field as GET, PUT and DELETE /api/config/prop return it.

    A regular field carries ``value``, a secret only ``populated``.
    """

    #: The dotted path.
    path: str
    #: The gateway's display value (``None`` after a reset, and for secrets).
    value: Any = None
    #: Validation problems of the configuration.
    warnings: list[ValidationWarning] | None = None
    #: For a secret, whether it has a value.
    populated: bool | None = None

    def is_secret(self) -> bool:
        """Whether the field is a secret (only ``populated`` is known)."""
        return self.populated is not None


class PatchOp(Model):
    """One operation of :meth:`ConfigAPI.patch`.

    RFC 6902 ``add``, ``replace``, ``remove`` and ``test``, plus ZeroClaw's
    ``comment``. ``None`` fields are left out.
    """

    #: ``add``, ``replace``, ``remove``, ``test`` or ``comment``.
    op: str
    #: Dotted, or a JSON Pointer (``/a/b``).
    path: str
    #: The value for ``add``, ``replace`` and ``test``.
    value: Any = None
    #: The TOML comment written above the key.
    comment: str | None = None


def replace_op(path: str, value: Any) -> PatchOp:
    """Set ``path`` to ``value``."""
    return PatchOp(op="replace", path=path, value=value)


def add_op(path: str, value: Any) -> PatchOp:
    """Set ``path`` to ``value``, creating the map alias it implies."""
    return PatchOp(op="add", path=path, value=value)


def remove_op(path: str) -> PatchOp:
    """Reset ``path`` to its default."""
    return PatchOp(op="remove", path=path)


def test_op(path: str, value: Any) -> PatchOp:
    """Fail the whole patch unless ``path`` currently displays as ``value``."""
    return PatchOp(op="test", path=path, value=value)


# Not a test, despite its name.
test_op.__test__ = False  # type: ignore[attr-defined]


def comment_op(path: str, comment: str) -> PatchOp:
    """Write ``comment`` above the key of ``path``."""
    return PatchOp(op="comment", path=path, comment=comment)


class PatchOpResult(Model):
    """What one patch operation left."""

    #: The operation.
    op: str
    #: The dotted path.
    path: str
    #: The new display value (``None`` for secrets and comments).
    value: Any = None
    #: For secrets, whether it now has a value.
    populated: bool | None = None
    #: For ``comment``, the comment written.
    comment: str | None = None


class PatchResponse(Model):
    """The result of :meth:`ConfigAPI.patch`."""

    #: Always true on success: the patch was saved.
    saved: bool
    #: One result per operation, in order.
    results: list[PatchOpResult]
    #: Validation problems outside the patched paths.
    warnings: list[ValidationWarning] | None = None


class DriftEntry(Model):
    """A field whose value on disk differs from the gateway's."""

    #: The dotted path.
    path: str
    #: Whether it is a secret (no values shown).
    secret: bool = False
    #: Always true.
    drifted: bool
    #: The gateway's value.
    in_memory_value: Any = None
    #: The value in ``config.toml``.
    on_disk_value: Any = None


class ConfigEntry(Model):
    """One configuration field."""

    #: The dotted path.
    path: str
    #: Groups fields.
    category: str
    #: ``string``, ``bool``, ``integer``, ``float``, ``enum``, ``alias-ref``,
    #: ``string-array``, ``object-array`` or ``object``.
    kind: str
    #: The Rust type, e.g. ``Option<String>``.
    type_hint: str
    #: The display value; ``None`` for secrets.
    value: Any = None
    #: Whether it has a value.
    populated: bool
    #: Whether it is a secret.
    is_secret: bool
    #: Whether an environment variable overrides it.
    is_env_overridden: bool = False
    #: The allowed values of an enum.
    enum_variants: list[str] | None = None
    #: The setup section it belongs to.
    section: str | None = None
    #: The dashboard tab.
    tab: str = ""
    #: Whether it is edited as multi-line text.
    multiline: bool = False


class ConfigList(Model):
    """The result of :meth:`ConfigAPI.list`."""

    #: The fields.
    entries: list[ConfigEntry]
    #: The fields whose value on disk differs from the gateway's.
    drifted: list[DriftEntry] | None = None


class MigrateResponse(Model):
    """The result of :meth:`ConfigAPI.migrate`."""

    #: Whether the file changed.
    migrated: bool
    #: Where the previous file was kept.
    backup_path: str | None = None
    #: The schema version now on disk.
    schema_version: int


class TemplateEntry(Model):
    """A map or list section and the type of its entries."""

    #: The dotted path.
    path: str
    #: ``map`` or ``list``.
    kind: str
    #: The Rust type of an entry.
    value_type: str
    #: What the section holds.
    description: str


class MapKeyResponse(Model):
    """The result of creating or deleting a map alias."""

    #: The map section.
    path: str
    #: The alias.
    key: str
    #: Whether a new alias was created.
    created: bool
    #: Cleanup steps that failed after the change was saved.
    warnings: list[str] | None = None


class ReferenceSite(Model):
    """A field that references an alias."""

    #: The dotted path of the referencing field.
    path: str
    #: Its raw value.
    raw_value: str


class DeletePlan(Model):
    """What deleting an alias would do."""

    #: The map section.
    path: str
    #: The alias.
    key: str
    #: Whether the delete would go through.
    allowed: bool
    #: The references that block it.
    blockers: list[ReferenceSite]
    #: The references it would clear.
    scrubs: list[ReferenceSite]
    #: For agents, the live ACP sessions (they block the delete).
    live_acp_sessions: int | None = None
    #: Whether the agent's memory, cron jobs and sessions go too.
    cascades_owned_state: bool


class RenameResponse(Model):
    """The result of :meth:`ConfigAPI.rename_map_key`."""

    #: The map section.
    path: str
    #: The old alias.
    from_: str = Field(alias="from")
    #: The new alias.
    to: str
    #: Whether it was renamed.
    renamed: bool
    #: Follow-up steps that failed (re-sending the rename finishes them).
    warnings: list[str] | None = None


class AliasSource(StrEnum):
    """An alias kind an alias-reference field can point to."""

    #: ``providers.models.*``.
    MODEL_PROVIDERS = "model_providers"
    TTS_PROVIDERS = "tts_providers"
    TRANSCRIPTION_PROVIDERS = "transcription_providers"
    #: ``channels.*``.
    CHANNELS = "channels"
    RISK_PROFILES = "risk_profiles"
    RUNTIME_PROFILES = "runtime_profiles"
    #: ``agents.*``.
    AGENTS = "agents"
    SKILL_BUNDLES = "skill_bundles"
    KNOWLEDGE_BUNDLES = "knowledge_bundles"
    MCP_BUNDLES = "mcp_bundles"


class CatalogModelProvider(Model):
    """A model provider the build knows."""

    #: The provider family name.
    name: str
    #: Shown to people.
    display_name: str
    #: Whether it runs locally.
    local: bool


class ModelPricing(Model):
    """A model's prices as the provider states them."""

    #: The input price.
    prompt: str | None = None
    #: The output price.
    completion: str | None = None
    #: The cached input read price.
    input_cache_read: str | None = None
    #: The cached input write price.
    input_cache_write: str | None = None


class CatalogModels(Model):
    """The models of a provider."""

    #: The provider family name.
    model_provider: str
    #: The model ids.
    models: list[str]
    #: The prices per model, when the provider publishes them.
    pricing: dict[str, ModelPricing] | None = None
    #: Whether it runs locally.
    local: bool
    #: Whether the list came live from the provider.
    live: bool


class ConfigStatus(Model):
    """Whether the setup is complete."""

    #: Whether the quickstart still has to run.
    needs_quickstart: bool
    #: ``has_dispatchable_agent``, ``incomplete_agent`` or ``fresh_install``.
    reason: str
    #: Whether part of the setup is done.
    has_partial_state: bool
    #: The steps left, in words.
    missing: list[str]


class AgentOptions(Model):
    """The aliases an agent can reference."""

    #: Channels, as ``type.alias``.
    channels: list[str]
    #: The channel types.
    channel_types: list[str]
    #: Model providers, as ``type.alias``.
    model_providers: list[str]
    #: The risk profiles.
    risk_profiles: list[str]
    #: The runtime profiles.
    runtime_profiles: list[str]
    #: The skill bundles.
    skill_bundles: list[str]
    #: The knowledge bundles.
    knowledge_bundles: list[str]
    #: The MCP bundles.
    mcp_bundles: list[str]
    #: The agents.
    agents: list[str]


class ConfigSection(Model):
    """A setup section."""

    #: The section key, e.g. ``providers.models``.
    key: str
    #: Shown to people.
    label: str
    #: The help text.
    help: str
    #: Whether it offers items to pick (:meth:`ConfigAPI.section_items`).
    has_picker: bool
    #: Whether it is completed.
    completed: bool
    #: Whether it is ready to use.
    ready: bool = False
    #: The group it is shown under.
    group: str = ""
    #: Whether the quickstart includes it.
    is_quickstart: bool = False
    #: ``direct_form``, ``one_tier_alias_map``, ``typed_family_map`` or
    #: ``backend_picker``.
    shape: str | None = None
    #: The cost category.
    cost_category: str = ""


class SectionItem(Model):
    """An item of a picker section."""

    #: The item key.
    key: str
    #: Shown to people.
    label: str
    #: What it is.
    description: str | None = None
    #: ``configured``, ``needs setup``, ``active`` or ``created``.
    badge: str | None = None


class SectionItems(Model):
    """The items of a picker section."""

    #: The section key.
    section: str
    #: The items.
    items: list[SectionItem]
    #: The help text.
    help: str


class SelectedItem(Model):
    """The result of :meth:`ConfigAPI.select_section_item`."""

    #: The prefix of the fields to fill (:meth:`ConfigAPI.list`).
    fields_prefix: str
    #: Whether something was created.
    created: bool


class ConfigAPI:
    """The configuration endpoints (``/api/config``), from :attr:`Client.config`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def snapshot(self) -> Any:
        """Return the whole configuration with secrets masked as ``***MASKED***``.

        GET /api/config. A compatibility snapshot; prefer :meth:`list` and
        :meth:`get`, which carry field metadata.
        """
        return await self._c._json("GET", ["api", "config"])

    async def schema(self) -> Any:
        """Return the JSON Schema of the whole configuration (OPTIONS /api/config).

        Static per gateway build. Public.
        """
        return await self._c._json("OPTIONS", ["api", "config"])

    async def prop_schema(self, path: str) -> Any:
        """Return the schema plus the field's metadata under ``x-zeroclaw-prop``.

        OPTIONS /api/config/prop. Public.
        """
        return await self._c._json(
            "OPTIONS", ["api", "config", "prop"], query={"path": path or None}
        )

    async def get(self, path: str) -> PropValue:
        """Read one field (GET /api/config/prop)."""
        return await self._c._call(
            "GET", ["api", "config", "prop"], PropValue, query={"path": path or None}
        )

    async def set(self, path: str, value: Any, comment: str | None = None) -> PropValue:
        """Write one field (PUT /api/config/prop).

        ``value`` is encoded as JSON (``None`` resets it); a non-empty
        ``comment`` is written above the key in the TOML. A map alias implied
        by the path is created.
        """
        body: dict[str, Any] = {"path": path, "value": value}
        if comment:
            body["comment"] = comment
        return await self._c._call("PUT", ["api", "config", "prop"], PropValue, json_body=body)

    async def reset(self, path: str) -> PropValue:
        """Reset one field to its default (DELETE /api/config/prop)."""
        return await self._c._call(
            "DELETE", ["api", "config", "prop"], PropValue, query={"path": path or None}
        )

    async def patch(
        self, ops: builtins.list[PatchOp], override_drift: bool = False
    ) -> PatchResponse:
        """Apply ``ops`` atomically, all or nothing (PATCH /api/config).

        With ``override_drift``, paths edited on disk since the gateway loaded
        them are overwritten instead of refused with 409.
        """
        headers = {OVERRIDE_DRIFT_HEADER: "true"} if override_drift else None
        return await self._c._call(
            "PATCH", ["api", "config"], PatchResponse, json_body=ops, headers=headers
        )

    async def list(self, prefix: str | None = None) -> ConfigList:
        """Return every field reachable under ``prefix`` (all fields when empty).

        With its kind, category and current value (GET /api/config/list).
        """
        return await self._c._call(
            "GET", ["api", "config", "list"], ConfigList, query={"prefix": prefix or None}
        )

    async def drift(self) -> builtins.list[DriftEntry]:
        """Return the fields whose value on disk differs from the gateway's.

        GET /api/config/drift.
        """
        return await self._c._field("GET", ["api", "config", "drift"], "drifted", list[DriftEntry])

    async def pending_reload(self) -> bool:
        """Report whether saved changes wait for a daemon reload.

        GET /api/config/reload-status.
        """
        return await self._c._field(
            "GET", ["api", "config", "reload-status"], "pending_reload", bool
        )

    async def init(self, section: str | None = None) -> builtins.list[str]:
        """Fill unset nested sections under ``section`` with defaults.

        Everywhere when empty. Returns the sections created
        (POST /api/config/init).
        """
        return await self._c._field(
            "POST",
            ["api", "config", "init"],
            "initialized",
            list[str],
            query={"section": section or None},
        )

    async def migrate(self) -> MigrateResponse:
        """Migrate ``config.toml`` to the current schema in place, keeping a backup.

        POST /api/config/migrate.
        """
        return await self._c._call("POST", ["api", "config", "migrate"], MigrateResponse)

    async def templates(self) -> builtins.list[TemplateEntry]:
        """Return the map and list sections and the type of their entries.

        GET /api/config/templates.
        """
        return await self._c._field(
            "GET", ["api", "config", "templates"], "templates", list[TemplateEntry]
        )

    async def map_keys(self, path: str) -> builtins.list[str]:
        """Return the aliases of a map section, e.g. ``agents`` or ``channels.whatsapp``.

        GET /api/config/map-keys.
        """
        return await self._c._field(
            "GET", ["api", "config", "map-keys"], "keys", list[str], query={"path": path or None}
        )

    async def create_map_key(self, path: str, key: str) -> MapKeyResponse:
        """Create alias ``key`` under map ``path`` with defaults (POST /api/config/map-key).

        ``created`` is false when it already existed.
        """
        return await self._c._call(
            "POST",
            ["api", "config", "map-key"],
            MapKeyResponse,
            query={"path": path or None, "key": key or None},
        )

    async def delete_map_key(self, path: str, key: str) -> MapKeyResponse:
        """Remove alias ``key`` and the references to it (DELETE /api/config/map-key).

        Deleting an agent also archives its workspace and its memory, cron
        jobs and sessions; check :meth:`delete_plan` first.
        """
        return await self._c._call(
            "DELETE",
            ["api", "config", "map-key"],
            MapKeyResponse,
            query={"path": path or None, "key": key or None},
        )

    async def delete_plan(self, path: str, key: str) -> DeletePlan:
        """Say what deleting alias ``key`` would block on or rewrite, changing nothing.

        GET /api/config/delete-plan.
        """
        return await self._c._call(
            "GET",
            ["api", "config", "delete-plan"],
            DeletePlan,
            query={"path": path or None, "key": key or None},
        )

    async def rename_map_key(self, path: str, from_: str, to: str) -> RenameResponse:
        """Rename alias ``from_`` to ``to``, and every reference to it.

        POST /api/config/rename-map-key.
        """
        return await self._c._call(
            "POST",
            ["api", "config", "rename-map-key"],
            RenameResponse,
            json_body={"path": path, "from": from_, "to": to},
        )

    async def refresh_context_window(self, provider_type: str, alias: str) -> int:
        """Ask the provider for the model's context window and store it.

        POST /api/config/model-providers/{type}/{alias}/refresh-context-window.
        """
        return await self._c._field(
            "POST",
            ["api", "config", "model-providers", provider_type, alias, "refresh-context-window"],
            "context_window",
            int,
        )

    async def alias_values(self, source: AliasSource) -> builtins.list[str]:
        """Return the aliases an alias-reference field may point to.

        Providers and channels as ``type.alias``
        (GET /api/config/resolve-alias-source).
        """
        return await self._c._field(
            "GET",
            ["api", "config", "resolve-alias-source"],
            "values",
            list[str],
            query={"source": str(source) or None},
        )

    async def catalog(self) -> builtins.list[CatalogModelProvider]:
        """Return the model providers this build knows (GET /api/config/catalog)."""
        return await self._c._field(
            "GET", ["api", "config", "catalog"], "model_providers", list[CatalogModelProvider]
        )

    async def catalog_models(self, model_provider: str) -> CatalogModels:
        """Return the models of a provider (GET /api/config/catalog/models).

        It may call the provider with the configured credentials.
        """
        return await self._c._call(
            "GET",
            ["api", "config", "catalog", "models"],
            CatalogModels,
            query={"model_provider": model_provider or None},
        )

    async def status(self) -> ConfigStatus:
        """Report whether the setup is complete (GET /api/config/status)."""
        return await self._c._call("GET", ["api", "config", "status"], ConfigStatus)

    async def agent_options(self) -> AgentOptions:
        """Return the aliases an agent can reference (GET /api/config/agent-options)."""
        return await self._c._call("GET", ["api", "config", "agent-options"], AgentOptions)

    async def sections(self) -> builtins.list[ConfigSection]:
        """Return the setup sections, in wizard order (GET /api/config/sections)."""
        return await self._c._field(
            "GET", ["api", "config", "sections"], "sections", list[ConfigSection]
        )

    async def section_items(self, section: str) -> SectionItems:
        """Return the items a picker section offers.

        E.g. the provider families of ``providers.models``
        (GET /api/config/sections/{section}).
        """
        return await self._c._call("GET", ["api", "config", "sections", section], SectionItems)

    async def select_section_item(
        self, section: str, key: str, alias: str | None = None
    ) -> SelectedItem:
        """Pick an item, creating what it needs, and return where its fields live.

        POST /api/config/sections/{section}/items/{key}. An empty ``alias``
        lets the gateway use ``default`` where the section takes one.
        """
        return await self._c._call(
            "POST",
            ["api", "config", "sections", section, "items", key],
            SelectedItem,
            json_body={"alias": alias or None},
        )
