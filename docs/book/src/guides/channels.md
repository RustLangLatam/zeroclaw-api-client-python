# Channels and group chats

A channel is named `type.alias` (`whatsapp.main`, `telegram.bot`), as
`client.channels.list()` returns it with its status, health and readiness.

## What the gateway requires

| Action | Needs |
|---|---|
| list channels, bind an identity, relink | a token |
| list rooms and members | a token, pairing on, the channel configured and running |
| send, create rooms, invite, remove members | the above, plus the channel in `[gateway] send_channels` |
| create rooms and manage members on WhatsApp Web | also `room_management = true` on the channel |

Refusals carry the channel and the reason
(`{"channel": "whatsapp.main", "error": "…"}`), which the
[error](./errors.md) keeps as its message.

## Sending

`client.channels.send(channel, to, content, thread_id=None)` delivers plain
text with no agent turn: for notifications a person, not the agent, is
sending. Without a `thread_id` it is sent outside a thread. With
`[gateway] send_groups_only`, only group chats can be addressed.

## Group chats

```python
channels = client.channels
created = await channels.create_room("whatsapp.main", "Orders team", invites=["+34600000000"])
for room in await channels.rooms("whatsapp.main"):
    members = await channels.room_members("whatsapp.main", room.id)
    print(room.name, len(members))
await channels.invite("whatsapp.main", created.room, "+34611111111")
await channels.remove_member("whatsapp.main", created.room, "+34611111111")
```

On WhatsApp, invitees are also added to the channel's allowlist, and the new
group to its allowed groups, so the agent answers in it. Creating rooms and
invitations are rate-limited per channel (`[gateway] rooms_per_hour`,
`invites_per_hour`, `invites_per_day`): over the limit the call fails with
429.

## Identities and logins

- `bind(channel_type, alias, identity)` allows a Telegram, WeChat or LINE
  user to talk to the channel.
- `relink(channel)` clears a QR-paired channel's saved login (WhatsApp Web);
  after `client.system.reload()` the channel asks to be paired again.
