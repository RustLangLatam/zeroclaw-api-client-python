"""Skill bundles and the skills in them.

Gateway handler: ``crates/zeroclaw-gateway/src/api_skills.rs``. Bundles
themselves are configuration (``skill_bundles.<alias>``); this module edits
the skills inside them. A skill is a SKILL.md: front matter plus a Markdown
body.
"""

from __future__ import annotations

import builtins
from typing import TYPE_CHECKING, Any

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["Skill", "SkillBundle", "SkillSummary", "SkillsAPI"]


class SkillBundle(Model):
    """A skill bundle."""

    #: The bundle's alias.
    alias: str
    #: Its directory.
    directory: str
    #: The skills it includes.
    include: list[str] | None = None
    #: The skills it leaves out.
    exclude: list[str] | None = None


class SkillSummary(Model):
    """A skill in a listing."""

    #: The bundle.
    bundle: str
    #: The skill's name.
    name: str
    #: Its directory.
    directory: str
    #: The front matter (name, description, tags, slash_options, …).
    frontmatter: Any


class Skill(Model):
    """A skill."""

    #: The bundle.
    bundle: str
    #: The skill's name.
    name: str
    #: The front matter.
    frontmatter: Any
    #: The Markdown body.
    body: str


def _skill(bundle: str, name: str) -> list[str]:
    return ["api", "skills", "bundles", bundle, "skills", name]


class SkillsAPI:
    """The skill endpoints (``/api/skills``), from :attr:`Client.skills`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def bundles(self) -> builtins.list[SkillBundle]:
        """Return the skill bundles (GET /api/skills/bundles)."""
        return await self._c._field(
            "GET", ["api", "skills", "bundles"], "bundles", list[SkillBundle]
        )

    async def list(self, bundle: str) -> builtins.list[SkillSummary]:
        """Return the skills of a bundle (GET /api/skills/bundles/{bundle}/skills)."""
        return await self._c._field(
            "GET", ["api", "skills", "bundles", bundle, "skills"], "skills", list[SkillSummary]
        )

    async def create(
        self, bundle: str, name: str, frontmatter: Any, body: str, no_scaffold: bool = False
    ) -> None:
        """Create a skill (POST /api/skills/bundles/{bundle}/skills).

        It gets scripts/, references/ and assets/ unless ``no_scaffold``.
        ``frontmatter`` is encoded as JSON.
        """
        await self._c._request(
            "POST",
            ["api", "skills", "bundles", bundle, "skills"],
            json_body={
                "name": name,
                "frontmatter": frontmatter,
                "body": body,
                "no_scaffold": no_scaffold,
            },
        )

    async def read(self, bundle: str, name: str) -> Skill:
        """Return a skill (GET /api/skills/bundles/{bundle}/skills/{name})."""
        return await self._c._call("GET", _skill(bundle, name), Skill)

    async def write(self, bundle: str, name: str, frontmatter: Any, body: str) -> None:
        """Replace a skill's front matter (encoded as JSON) and body.

        PUT /api/skills/bundles/{bundle}/skills/{name}.
        """
        await self._c._request(
            "PUT", _skill(bundle, name), json_body={"frontmatter": frontmatter, "body": body}
        )

    async def delete(self, bundle: str, name: str, purge: bool = False) -> None:
        """Archive a skill, or delete it for good with ``purge``.

        DELETE /api/skills/bundles/{bundle}/skills/{name}.
        """
        await self._c._request("DELETE", _skill(bundle, name), query={"purge": purge})

    async def slash_option_kinds(self) -> builtins.list[Any]:
        """Return the option types a skill's slash command may declare.

        GET /api/skills/slash-option-kinds.
        """
        return await self._c._field(
            "GET", ["api", "skills", "slash-option-kinds"], "kinds", list[Any]
        )
