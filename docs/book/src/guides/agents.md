# Agents, personality and skills

An agent is a configuration entry (`agents.<alias>`): create, rename and
delete agents with the [configuration](./configuration.md) calls. Its files
and skills are reached through `client.agent(alias)`.

## Workspace

Each agent has a workspace directory. Paths are relative to it; leaving it is
refused, and the personality files and `sessions` at its root are protected.

```python
agent = client.agent("helper")
listing = await agent.list_files("docs")
for entry in listing.entries:
    print(entry.name, entry.kind)
file = await agent.read_file("docs/catalog.pdf")  # base64 when binary
print(file.encoding, file.size)
await agent.make_dir("archive")
await agent.move_path("docs/old.pdf", "archive/old.pdf")
await agent.remove_path("archive")
```

The shared directory (`<install>/shared/`) is listed, and has directories
made and removed, under `client.files`, which also uploads images into an
agent's workspace (`upload_image(agent, image_bytes)`) and returns the
`[IMAGE:…]` marker to attach them to a chat message.

## Personality

`SOUL.md`, `IDENTITY.md`, `USER.md`, `AGENTS.md`, `TOOLS.md`, `HEARTBEAT.md`
and `MEMORY.md` shape an agent's behavior. `personality_files()` lists them,
`personality(filename)` reads one, and
`write_personality(filename, content, expected_mtime_ms)` replaces it
(20 000 characters at most). Pass the `mtime_ms` you read to make the write
fail with 409 instead of overwriting someone else's change; `None` writes
regardless. `personality_templates(PersonalityContext(...))` renders the
defaults without writing them.

## Skills

Skills live in bundles (`skill_bundles.<alias>` in the configuration).
`client.skills` lists bundles and their skills and creates, reads, writes
and deletes (archives, or purges) a skill: front matter plus a Markdown body.
`await client.agent(alias).skills()` shows what an agent actually loads,
where each skill comes from, and which the audit dropped.
