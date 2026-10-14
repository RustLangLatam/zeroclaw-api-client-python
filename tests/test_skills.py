from __future__ import annotations

import httpx

from zeroclaw_client import Client
from zeroclaw_client.skills import SkillsAPI

from .conftest import Gateway, body, reply

FRONTMATTER = {"name": "greet", "description": "Greets"}


async def test_manages_skills_in_bundles(gateway: Gateway, client: Client) -> None:
    def create(request: httpx.Request) -> httpx.Response:
        assert body(request) == {
            "name": "greet",
            "frontmatter": FRONTMATTER,
            "body": "",
            "no_scaffold": True,
        }
        return reply({"bundle": "team", "name": "greet", "directory": "/s/team/greet"}, 201)(
            request
        )

    def write(request: httpx.Request) -> httpx.Response:
        assert body(request) == {"frontmatter": FRONTMATTER, "body": "# Hi"}
        return httpx.Response(204)

    def delete(request: httpx.Request) -> httpx.Response:
        assert request.url.params["purge"] == "true"
        return httpx.Response(204)

    route = "/api/skills/bundles/team/skills"
    gateway.on(
        "GET",
        "/api/skills/bundles",
        {"bundles": [{"alias": "team", "directory": "/s/team", "include": [], "exclude": []}]},
    )
    gateway.on(
        "GET",
        route,
        {
            "skills": [
                {
                    "bundle": "team",
                    "name": "greet",
                    "directory": "/s/team/greet",
                    "frontmatter": FRONTMATTER,
                }
            ]
        },
    )
    gateway.on("POST", route, create)
    gateway.on(
        "GET",
        f"{route}/greet",
        {"bundle": "team", "name": "greet", "frontmatter": FRONTMATTER, "body": "# Greet"},
    )
    gateway.on("PUT", f"{route}/greet", write)
    gateway.on("DELETE", f"{route}/greet", delete)
    gateway.on("GET", "/api/skills/slash-option-kinds", {"kinds": [{"manifest_name": "string"}]})

    skills = SkillsAPI(client)
    assert (await skills.bundles())[0].alias == "team"
    listed = await skills.list("team")
    assert listed[0].name == "greet"
    assert listed[0].frontmatter == FRONTMATTER
    await skills.create("team", "greet", FRONTMATTER, "", no_scaffold=True)
    assert (await skills.read("team", "greet")).body == "# Greet"
    await skills.write("team", "greet", FRONTMATTER, "# Hi")
    await skills.delete("team", "greet", purge=True)
    assert await skills.slash_option_kinds() == [{"manifest_name": "string"}]


async def test_delete_without_purge_says_so(gateway: Gateway, client: Client) -> None:
    def delete(request: httpx.Request) -> httpx.Response:
        assert request.url.params["purge"] == "false"
        return httpx.Response(204)

    gateway.on("DELETE", "/api/skills/bundles/team/skills/greet", delete)
    await SkillsAPI(client).delete("team", "greet")
