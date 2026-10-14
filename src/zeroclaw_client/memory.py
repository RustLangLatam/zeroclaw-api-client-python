"""Long-term memory: entries the agents store and recall.

Gateway handlers: ``crates/zeroclaw-gateway/src/api.rs`` (``/api/memory*``);
entry type in ``crates/zeroclaw-api/src/memory_traits.rs``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._model import Model

if TYPE_CHECKING:
    from ._client import Client

__all__ = ["MemoryAPI", "MemoryEntry"]


class MemoryEntry(Model):
    """A memory entry."""

    #: The entry id.
    id: str
    #: The key.
    key: str
    #: The content.
    content: str
    #: The category.
    category: str
    #: When it was stored.
    timestamp: str
    #: The session it came from.
    session_id: str | None = None
    #: The relevance of a recall match.
    score: float | None = None
    #: The namespace.
    namespace: str | None = None
    #: The importance.
    importance: float | None = None
    #: The entry that replaced it.
    superseded_by: str | None = None
    #: ``"episodic"``, ``"procedural"`` or ``{"semantic": "fact"|…}``.
    kind: Any = None
    #: Whether it is pinned.
    pinned: bool
    #: The owning agent.
    agent_alias: str | None = None


class MemoryAPI:
    """The long-term memory endpoints (``/api/memory``), from :attr:`Client.memory`."""

    def __init__(self, client: Client) -> None:
        self._c = client

    async def search(
        self,
        *,
        query: str | None = None,
        category: str | None = None,
        since: str | None = None,
        until: str | None = None,
        agent: str | None = None,
    ) -> list[MemoryEntry]:
        """Search the memory (GET /api/memory).

        With a text (``query``) or time (``since``, ``until``, RFC 3339)
        filter, return the best matches (at most 50); otherwise every entry
        (of ``category``, when set: ``core``, ``daily``, ``conversation`` or
        custom). ``agent`` searches an agent's memory instead of the shared
        one. Contents longer than 4096 characters come truncated.
        """
        params = {
            "query": query,
            "category": category,
            "since": since,
            "until": until,
            "agent": agent,
        }
        return await self._c._field(
            "GET",
            ["api", "memory"],
            "entries",
            list[MemoryEntry],
            query={k: v or None for k, v in params.items()},
        )

    async def store(
        self, key: str, content: str, category: str | None = None, agent: str | None = None
    ) -> None:
        """Store ``content`` under ``key`` (POST /api/memory).

        In category ``core`` unless ``category`` is set, and in ``agent``'s
        memory or, without one, the shared one.
        """
        body = {
            "key": key,
            "content": content,
            "category": category or None,
            "agent": agent or None,
        }
        await self._c._request("POST", ["api", "memory"], json_body=body)

    async def forget(self, key: str, agent: str | None = None) -> bool:
        """Forget an entry and report whether it existed (DELETE /api/memory/{key}).

        From ``agent``'s memory, or the shared one without it.
        """
        return await self._c._field(
            "DELETE", ["api", "memory", key], "deleted", bool, query={"agent": agent or None}
        )
