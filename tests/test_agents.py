from __future__ import annotations

import httpx
import pytest

from zeroclaw_client import APIError, Client
from zeroclaw_client.agents import AgentAPI, PersonalityContext

from .conftest import Gateway, Handler, body, reply


async def test_agent_edits_its_workspace(gateway: Gateway, client: Client) -> None:
    def listing(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "docs"
        return reply({"path": "docs", "entries": [{"name": "a.pdf", "kind": "file", "size": 10}]})(
            request
        )

    def read(request: httpx.Request) -> httpx.Response:
        assert request.url.params["path"] == "docs/a.pdf"
        return reply(
            {
                "path": "docs/a.pdf",
                "size": 10,
                "is_text": False,
                "content": "JVBERg==",
                "encoding": "base64",
            }
        )(request)

    def expect(want: object, answer: object) -> Handler:
        def handle(request: httpx.Request) -> httpx.Response:
            assert body(request) == want
            return reply(answer)(request)

        return handle

    base = "/api/agents/helper"
    gateway.on("GET", f"{base}/workspace/list", listing)
    gateway.on("GET", f"{base}/workspace/read", read)
    gateway.on("POST", f"{base}/workspace/mkdir", expect({"path": "docs"}, {"created": "docs"}))
    gateway.on(
        "POST", f"{base}/workspace/move", expect({"from": "a", "to": "b"}, {"from": "a", "to": "b"})
    )
    gateway.on("DELETE", f"{base}/workspace/path", expect({"path": "b"}, {"removed": "b"}))
    gateway.on(
        "GET", f"{base}/skills", {"agent": "helper", "skills": [{"name": "s", "origin": "bundle"}]}
    )

    agent = AgentAPI(client, "helper")
    assert agent.alias == "helper"
    assert (await agent.list_files("docs")).entries[0].size == 10
    assert (await agent.read_file("docs/a.pdf")).encoding == "base64"
    await agent.make_dir("docs")
    await agent.move_path("a", "b")
    await agent.remove_path("b")
    skills = await agent.skills()
    assert len(skills.skills) == 1
    assert skills.dropped is None


async def test_agent_reads_and_writes_personality_files(gateway: Gateway, client: Client) -> None:
    def with_agent(answer: object, status: int = 200, want: object = None) -> Handler:
        def handle(request: httpx.Request) -> httpx.Response:
            assert request.url.params["agent"] == "helper"
            if want is not None:
                assert body(request) == want
            return reply(answer, status)(request)

        return handle

    def templates(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {"agent": "helper", "user_name": "Ana"}
        return reply({"preset": "default", "files": [{"filename": "USER.md", "content": "Ana"}]})(
            request
        )

    gateway.on(
        "GET",
        "/api/personality",
        with_agent(
            {
                "max_chars": 20000,
                "files": [{"filename": "SOUL.md", "exists": True, "size": 3, "mtime_ms": 1}],
            }
        ),
    )
    gateway.on(
        "GET",
        "/api/personality/SOUL.md",
        with_agent(
            {
                "filename": "SOUL.md",
                "content": "Hi",
                "exists": True,
                "truncated": False,
                "mtime_ms": 1,
            }
        ),
    )
    gateway.on(
        "PUT",
        "/api/personality/SOUL.md",
        with_agent(
            {"bytes_written": 3, "mtime_ms": 2}, want={"content": "New", "expected_mtime_ms": 1}
        ),
    )
    gateway.on(
        "PUT",
        "/api/personality/USER.md",
        with_agent(
            {"error": "personality_disk_drift", "filename": "USER.md", "current_mtime_ms": 5},
            status=409,
            # Without an expected time, the gateway gets an explicit null.
            want={"content": "y", "expected_mtime_ms": None},
        ),
    )
    gateway.on("GET", "/api/personality/templates", templates)

    agent = AgentAPI(client, "helper")
    assert (await agent.personality_files()).max_chars == 20_000
    assert (await agent.personality("SOUL.md")).content == "Hi"
    assert (await agent.write_personality("SOUL.md", "New", 1)).mtime_ms == 2
    with pytest.raises(APIError) as caught:
        await agent.write_personality("USER.md", "y")
    assert caught.value.status == 409
    rendered = await agent.personality_templates(PersonalityContext(user_name="Ana"))
    assert rendered.preset == "default"


@pytest.mark.parametrize(
    ("context", "want"),
    [
        (PersonalityContext(), {"agent": "helper"}),
        (PersonalityContext(agent_name="", timezone="UTC"), {"agent": "helper", "timezone": "UTC"}),
        (
            PersonalityContext(include_memory=False, communication_style="brief"),
            {"agent": "helper", "communication_style": "brief", "include_memory": "false"},
        ),
    ],
)
async def test_personality_template_query(
    gateway: Gateway, client: Client, context: PersonalityContext, want: dict[str, str]
) -> None:
    def templates(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == want
        return reply({"preset": "default", "files": []})(request)

    gateway.on("GET", "/api/personality/templates", templates)
    await AgentAPI(client, "helper").personality_templates(context)
