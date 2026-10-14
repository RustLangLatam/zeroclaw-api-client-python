from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.memory import MemoryAPI

from .conftest import Gateway, body, reply


async def test_stores_recalls_and_forgets(gateway: Gateway, client: Client) -> None:
    def store(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"key": "k", "content": "c", "category": None, "agent": "helper"}
        return reply({"status": "ok"})(request)

    def search(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"query": "c", "agent": "helper"}
        return reply(
            {
                "entries": [
                    {
                        "id": "1",
                        "key": "k",
                        "content": "c",
                        "category": "core",
                        "timestamp": "t",
                        "score": 0.9,
                        "kind": {"semantic": "fact"},
                        "pinned": False,
                    }
                ]
            }
        )(request)

    def forget(request: httpx.Request) -> httpx.Response:
        assert not request.url.params
        return reply({"status": "ok", "deleted": True})(request)

    gateway.on("POST", "/api/memory", store)
    gateway.on("GET", "/api/memory", search)
    gateway.on("DELETE", "/api/memory/a%2Fb", forget)

    memory = MemoryAPI(client)
    await memory.store("k", "c", agent="helper")
    found = await memory.search(query="c", agent="helper")
    assert len(found) == 1
    assert found[0].score == 0.9
    assert found[0].kind == {"semantic": "fact"}
    assert await memory.forget("a/b")


async def test_forget_in_an_agents_memory(gateway: Gateway, client: Client) -> None:
    def forget(request: httpx.Request) -> httpx.Response:
        assert request.url.params["agent"] == "helper"
        return reply({"status": "ok", "deleted": False})(request)

    gateway.on("DELETE", "/api/memory/k", forget)
    assert not await MemoryAPI(client).forget("k", "helper")
