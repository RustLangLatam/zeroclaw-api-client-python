# Guides

Each guide covers one area of the gateway and the module that calls it:

| Guide | Module | Attribute |
|---|---|---|
| [Configuration](./configuration.md) | `config.py` | `client.config` |
| [Agents, personality and skills](./agents.md) | `agents.py`, `skills.py`, `files.py` | `client.agent(alias)`, `client.skills`, `client.files` |
| [Channels and group chats](./channels.md) | `channels.py` | `client.channels` |
| [Chatting with an agent](./chat.md) | `chat.py`, `webhook.py` | `await client.chat(alias, …)`, `client.webhook` |
| [Sessions and live events](./events.md) | `sessions.py`, `events.py` | `client.sessions`, `client.events` |
| [Cron, memory and cost](./operations.md) | `cron.py`, `memory.py`, `cost.py`, `system.py` | `client.cron`, `client.memory`, `client.cost`, `client.system` |
| [SOPs](./sops.md) | `sops.py`, `canvas.py`, `quickstart.py` | `client.sops`, `client.canvas`, `client.quickstart` |
| [Resilience](./resilience.md) | `_transport.py` | `Client(...)` arguments |
| [Errors](./errors.md) | `_errors.py` | — |

Pairing is covered in [Getting Started](../getting-started/pairing.md);
WebAuthn (`client.webauthn`) only carries the JSON of a hardware-key
ceremony run elsewhere.

The snippets run inside an `async def` with a `client: Client` at hand;
names come from `zeroclaw_client`.
