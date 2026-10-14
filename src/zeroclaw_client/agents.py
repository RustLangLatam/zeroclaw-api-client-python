"""Per-agent resources: the agent's workspace files, personality files and skills.

Agents themselves are configuration entries (``agents.<alias>``), created
and removed through the configuration endpoints.

Gateway handlers: ``crates/zeroclaw-gateway/src/api_browse.rs``,
``api_personality.rs`` and ``api_skills.rs``. Workspace paths are relative
to the agent's workspace; escaping it is refused, and the personality files
and sessions at its root are protected.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._model import Model
from .files import FileContent, FileListing

if TYPE_CHECKING:
    from ._client import Client

__all__ = [
    "AgentAPI",
    "AgentSkills",
    "PersonalityContext",
    "PersonalityFile",
    "PersonalityFileEntry",
    "PersonalityFiles",
    "PersonalityTemplates",
    "PersonalityWritten",
]


class PersonalityContext(Model):
    """Fills the default personality files of :meth:`AgentAPI.personality_templates`.

    ``None`` or empty fields are not sent.
    """

    #: The agent's name.
    agent_name: str | None = None
    #: The user's name.
    user_name: str | None = None
    #: The time zone.
    timezone: str | None = None
    #: The communication style.
    communication_style: str | None = None
    #: Whether to render MEMORY.md.
    include_memory: bool | None = None


class PersonalityFileEntry(Model):
    """A personality file's presence."""

    #: The file name.
    filename: str
    #: Whether it exists.
    exists: bool
    #: Its size in bytes.
    size: int
    #: Its modification time, ms since the epoch.
    mtime_ms: int | None = None


class PersonalityFiles(Model):
    """The personality files of an agent."""

    #: Each editable file.
    files: list[PersonalityFileEntry]
    #: The maximum characters per file.
    max_chars: int


class PersonalityFile(Model):
    """A personality file's content."""

    #: The file name.
    filename: str
    #: The content (``None`` when the file does not exist).
    content: str | None = None
    #: Whether it exists.
    exists: bool
    #: Whether the content was cut at the size limit.
    truncated: bool
    #: Its modification time, for :meth:`AgentAPI.write_personality`.
    mtime_ms: int | None = None


class PersonalityWritten(Model):
    """The result of :meth:`AgentAPI.write_personality`."""

    #: The number of bytes written.
    bytes_written: int
    #: The new modification time.
    mtime_ms: int | None = None


class PersonalityTemplates(Model):
    """The rendered default personality files."""

    #: The preset used.
    preset: str
    #: Each file: ``{filename, content}``.
    files: list[Any]


class AgentSkills(Model):
    """The skills an agent loads."""

    #: The agent.
    agent: str
    #: The loaded skills: name, description, origin (workspace, open-skills,
    #: plugin, bundle), editable, …
    skills: list[Any]
    #: The skills left out, with ``reason_kind`` and ``reason``.
    dropped: list[Any] | None = None


class AgentAPI:
    """One agent's endpoints, from :meth:`Client.agent`."""

    def __init__(self, client: Client, alias: str) -> None:
        self._c = client
        self._alias = alias

    @property
    def alias(self) -> str:
        """The agent's alias."""
        return self._alias

    def _workspace(self, action: str) -> list[str]:
        return ["api", "agents", self._alias, "workspace", action]

    async def list_files(self, path: str | None = None) -> FileListing:
        """Return a workspace directory, the root when ``path`` is empty.

        GET /api/agents/{alias}/workspace/list.
        """
        return await self._c._call(
            "GET", self._workspace("list"), FileListing, query={"path": path or None}
        )

    async def read_file(self, path: str) -> FileContent:
        """Return a workspace file, up to 4 MiB; binary files come base64-encoded.

        GET /api/agents/{alias}/workspace/read.
        """
        return await self._c._call(
            "GET", self._workspace("read"), FileContent, query={"path": path or None}
        )

    async def make_dir(self, path: str) -> None:
        """Create a directory (POST /api/agents/{alias}/workspace/mkdir)."""
        await self._c._request("POST", self._workspace("mkdir"), json_body={"path": path})

    async def move_path(self, from_: str, to: str) -> None:
        """Move or rename a file or directory (POST /api/agents/{alias}/workspace/move)."""
        await self._c._request("POST", self._workspace("move"), json_body={"from": from_, "to": to})

    async def remove_path(self, path: str) -> None:
        """Remove a file or directory (DELETE /api/agents/{alias}/workspace/path)."""
        await self._c._request("DELETE", self._workspace("path"), json_body={"path": path})

    async def personality_files(self) -> PersonalityFiles:
        """Return the agent's personality files and whether each exists (GET /api/personality)."""
        return await self._c._call(
            "GET", ["api", "personality"], PersonalityFiles, query={"agent": self._alias or None}
        )

    async def personality(self, filename: str) -> PersonalityFile:
        """Return one personality file (GET /api/personality/{filename}).

        ``filename`` is SOUL.md, IDENTITY.md, USER.md, AGENTS.md, TOOLS.md,
        HEARTBEAT.md or MEMORY.md.
        """
        return await self._c._call(
            "GET",
            ["api", "personality", filename],
            PersonalityFile,
            query={"agent": self._alias or None},
        )

    async def write_personality(
        self, filename: str, content: str, expected_mtime_ms: int | None = None
    ) -> PersonalityWritten:
        """Replace a personality file, at most 20 000 characters (PUT /api/personality/{filename}).

        With ``expected_mtime_ms``, the write is refused (409) if the file
        changed since it was read.
        """
        return await self._c._call(
            "PUT",
            ["api", "personality", filename],
            PersonalityWritten,
            query={"agent": self._alias or None},
            json_body={"content": content, "expected_mtime_ms": expected_mtime_ms},
        )

    async def personality_templates(
        self, context: PersonalityContext | None = None
    ) -> PersonalityTemplates:
        """Return the default personality files rendered for this agent, without writing them.

        GET /api/personality/templates.
        """
        pc = context or PersonalityContext()
        query = {
            "agent": self._alias,
            "agent_name": pc.agent_name,
            "user_name": pc.user_name,
            "timezone": pc.timezone,
            "communication_style": pc.communication_style,
            "include_memory": pc.include_memory,
        }
        return await self._c._call(
            "GET",
            ["api", "personality", "templates"],
            PersonalityTemplates,
            query={k: v for k, v in query.items() if v != ""},
        )

    async def skills(self) -> AgentSkills:
        """Return the skills the agent loads, where each comes from, and those the audit dropped.

        GET /api/agents/{alias}/skills.
        """
        return await self._c._call("GET", ["api", "agents", self._alias, "skills"], AgentSkills)
