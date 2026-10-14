"""Writes against a real gateway.

Every test creates what it needs under the sdk-py-test prefix and removes it
in a ``finally``. Selected only with the live marker, and only run with
ZEROCLAW_WRITE=1::

    ZEROCLAW_URL=… ZEROCLAW_TOKEN=… ZEROCLAW_AGENT=<alias> ZEROCLAW_WRITE=1 \\
      pytest -m live tests/test_live_write.py

Some tests need more of the gateway and skip without it:

- ZEROCLAW_TURNS=1 lets them start agent turns (chat, webhook, A2A), which
  spend model tokens;
- admin routes answer only on the gateway host (run pytest in the gateway's
  network namespace);
- SOPs need ``[sop] sops_dir``, A2A needs ``a2a.server.enabled`` and the agent
  published, WebAuthn a build with the webauthn feature.

Never run against a gateway you cannot afford to have changed: a test cut
short may leave sdk-py-test leftovers.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import json
import os
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from functools import partial
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import Prehashed
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from zeroclaw_client import (
    FRAME_DONE,
    FRAME_ERROR,
    AliasSource,
    Client,
    CronJobPatch,
    CronSettingsPatch,
    Decision,
    DecodeError,
    LogQuery,
    NewCronJob,
    PersonalityContext,
    ZeroClawError,
    comment_op,
    is_unauthorized,
    replace_op,
    status_code,
    test_op,
)

pytestmark = pytest.mark.live

LIVE_NAME = "sdk-py-test"
TURNS = os.environ.get("ZEROCLAW_TURNS") == "1"


@pytest.fixture
def agent() -> str:
    url, token = os.environ.get("ZEROCLAW_URL", ""), os.environ.get("ZEROCLAW_TOKEN", "")
    alias = os.environ.get("ZEROCLAW_AGENT", "")
    if not url or not token or not alias or os.environ.get("ZEROCLAW_WRITE") != "1":
        pytest.skip("set ZEROCLAW_URL, ZEROCLAW_TOKEN, ZEROCLAW_AGENT and ZEROCLAW_WRITE=1")
    return alias


@pytest.fixture
async def live_client(agent: str) -> AsyncIterator[Client]:
    async with Client(os.environ["ZEROCLAW_URL"], token=os.environ["ZEROCLAW_TOKEN"]) as c:
        yield c


def skip_unoffered(what: str, err: ZeroClawError) -> None:
    """Skip when the gateway does not offer what ``err`` says it lacks.

    A disabled subsystem (503), a missing route or feature (404), or an admin
    route called from off the host (403).
    """
    if status_code(err) in (403, 404, 503):
        pytest.skip(f"{what} not offered by this gateway: {err}")


async def quietly(*calls: Callable[[], Awaitable[object]]) -> None:
    """Make cleanup calls, ignoring their errors (a test may have removed the thing)."""
    for call in calls:
        with contextlib.suppress(ZeroClawError):
            await call()


async def test_live_config(live_client: Client) -> None:
    config = live_client.config
    path = "gateway.webhook_rate_limit_per_minute"
    before = await config.get(path)
    try:
        await config.set(path, 61, f"set by {LIVE_NAME}")
        patched = await config.patch(
            [test_op(path, "61"), replace_op(path, 62), comment_op(path, LIVE_NAME)]
        )
        assert patched.saved, patched
        assert len(patched.results) == 3, patched
        with pytest.raises(ZeroClawError):  # a failing test op refuses the patch
            await config.patch([test_op(path, "1"), replace_op(path, 1)])
        # Reset on a field already at its default, so nothing changes.
        await config.reset("security.webauthn.rp_name")

        profiles = "risk_profiles"
        key = LIVE_NAME.replace("-", "_")
        renamed = key + "_2"
        try:
            assert (await config.create_map_key(profiles, key)).created, "not created"
            await config.delete_plan(profiles, key)
            assert (await config.rename_map_key(profiles, key, renamed)).renamed, "not renamed"
            await config.delete_map_key(profiles, renamed)
        finally:
            await quietly(
                lambda: config.delete_map_key(profiles, key),
                lambda: config.delete_map_key(profiles, renamed),
            )
        await config.alias_values(AliasSource.RISK_PROFILES)
        await config.catalog_models("openai")
        for s in await config.sections():
            if s.has_picker:
                await config.section_items(s.key)
                break
        await config.schema()
        await config.prop_schema(path)
    finally:
        await quietly(lambda: config.patch([replace_op(path, before.value)], True))


async def test_live_cron(live_client: Client, agent: str) -> None:
    cron = live_client.cron
    job = await cron.create(
        NewCronJob(
            agent=agent,
            name=LIVE_NAME,
            schedule="0 0 1 1 *",
            job_type="shell",
            command=f"echo {LIVE_NAME}",
            shell_output_format="raw",
        )
    )
    try:
        assert not (await cron.update(job.id, CronJobPatch(enabled=False))).enabled, "enabled"
        run = await cron.run(job.id)
        print(f"run: success={run.success} output={run.output!r}")
        await cron.runs(job.id, 5)
        settings = await cron.settings()
        await cron.update_settings(CronSettingsPatch(enabled=settings.enabled))
        await cron.delete(job.id)
    finally:
        await quietly(lambda: cron.delete(job.id))


async def test_live_memory(live_client: Client, agent: str) -> None:
    memory = live_client.memory
    try:
        await memory.store(LIVE_NAME, "written by the Python SDK live test", None, agent)
        await memory.search(query="Python SDK live test", agent=agent)
        assert await memory.forget(LIVE_NAME, agent), "nothing forgotten"
    finally:
        await quietly(lambda: memory.forget(LIVE_NAME, agent))


# The smallest valid PNG: one transparent pixel.
PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N"
    b"\x00\x00\x00\x00IEND\xaeB`\x82"
)


async def test_live_files(live_client: Client, agent: str) -> None:
    files = live_client.files
    try:
        await files.make_dir(LIVE_NAME)
        await files.list(LIVE_NAME)
        await files.remove_dir(LIVE_NAME)
        try:
            up = await files.upload_image(agent, PNG)
        except ZeroClawError as exc:
            skip_unoffered("image upload", exc)
            raise
        print(f"uploaded to {up.path}")
    finally:
        await quietly(lambda: files.remove_dir(LIVE_NAME))


async def test_live_agent_workspace(live_client: Client, agent: str) -> None:
    a = live_client.agent(agent)
    directory, moved = LIVE_NAME, LIVE_NAME + "-moved"
    try:
        await a.make_dir(directory)
        await a.move_path(directory, moved)
        await a.remove_path(moved)
        soul = await a.personality("SOUL.md")
        if soul.exists and soul.content is not None and not soul.truncated:
            # Writes the same content back: exercises the drift guard without
            # changing the agent.
            await a.write_personality("SOUL.md", soul.content, soul.mtime_ms)
        await a.personality_templates(PersonalityContext(agent_name=LIVE_NAME))
    finally:
        await quietly(lambda: a.remove_path(directory), lambda: a.remove_path(moved))


async def test_live_skills(live_client: Client) -> None:
    config, skills = live_client.config, live_client.skills
    bundle = LIVE_NAME.replace("-", "_")
    try:
        await config.create_map_key("skill_bundles", bundle)
        try:
            try:
                await skills.create(
                    bundle,
                    LIVE_NAME,
                    {"name": LIVE_NAME, "description": "Python SDK live test"},
                    "Say hi.",
                )
            except ZeroClawError as exc:
                skip_unoffered("skill authoring", exc)
                raise
            await skills.read(bundle, LIVE_NAME)
            await skills.write(
                bundle,
                LIVE_NAME,
                {"name": LIVE_NAME, "description": "Python SDK live test, edited"},
                "Say hello.",
            )
            await skills.list(bundle)
            await skills.delete(bundle, LIVE_NAME, True)
        finally:
            await quietly(lambda: skills.delete(bundle, LIVE_NAME, True))
    finally:
        await quietly(lambda: config.delete_map_key("skill_bundles", bundle))


async def test_live_canvas(live_client: Client) -> None:
    canvas = live_client.canvas
    try:
        async with await canvas.watch(LIVE_NAME) as feed:
            await canvas.publish(LIVE_NAME, "markdown", f"# {LIVE_NAME}")
            async with asyncio.timeout(10):
                while True:
                    frame = await feed.next()
                    assert frame is not None, "watch: the feed closed"
                    if f"# {LIVE_NAME}" in json.dumps(frame):
                        break
        await canvas.current(LIVE_NAME)
        assert await canvas.history(LIVE_NAME), "empty history"
        await canvas.clear(LIVE_NAME)
    finally:
        await quietly(lambda: canvas.clear(LIVE_NAME))


async def test_live_pairing(live_client: Client) -> None:
    client, pairing = live_client, live_client.pairing
    try:
        code = await pairing.new_code()
    except ZeroClawError as exc:
        skip_unoffered("minting pairing codes", exc)
        raise
    paired = await pairing.pair(code, LIVE_NAME, "service")
    device = client.with_token(paired.token)
    devices = await device.pairing.devices()
    ids = [d.id for d in devices if d.name == LIVE_NAME]
    assert ids, f"the new device is not listed: {devices}"
    device_id = ids[0]
    try:
        await device.pairing.set_capabilities(["chat"])

        # Rotating revokes the device and mints a code to pair it again.
        again = await pairing.rotate_device_token(device_id)
        with pytest.raises(ZeroClawError) as rotated:
            await device.pairing.devices()
        assert is_unauthorized(rotated.value), f"a rotated token still works: {rotated.value}"
        assert again, "rotate minted no code"
        repaired = await pairing.pair(again, LIVE_NAME, "service")
        devices = await pairing.devices()
        ids = [d.id for d in devices if d.name == LIVE_NAME]
        assert ids, f"the re-paired device is not listed: {devices}"
        device_id = ids[0]
        await pairing.revoke_device(device_id)
        with pytest.raises(ZeroClawError) as revoked:
            await client.with_token(repaired.token).pairing.devices()
        assert is_unauthorized(revoked.value), f"a revoked token still works: {revoked.value}"
    finally:
        await quietly(lambda: pairing.revoke_device(device_id))


async def test_live_system(live_client: Client, agent: str) -> None:
    system = live_client.system
    await system.doctor()
    await system.cli_tools()
    await system.logs(LogQuery(limit=5))
    await system.openapi()
    try:
        print(f"version check: {await system.version_check(False, None)}")
    except ZeroClawError as exc:
        print(f"version check (needs internet): {exc}")
    await system.upgrade_status()
    try:
        opts = await system.tool_param_options("channel_refs", agent, None)
    except ZeroClawError as exc:
        skip_unoffered("tool parameter options", exc)
        raise
    print(f"tool parameter options: {len(opts)}")


async def test_live_quickstart(live_client: Client) -> None:
    q = live_client.quickstart
    await q.state()
    await q.fields("model_provider", "openai")
    try:
        await q.validate({})
    except ZeroClawError as exc:
        if status_code(exc) == 0:
            raise  # a refusal of an empty submission is the expected answer


async def wait_healthy(client: Client) -> None:
    """Wait up to a minute for the gateway to answer again."""
    await asyncio.sleep(2)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        with contextlib.suppress(ZeroClawError):
            await client.system.health()
            return
        await asyncio.sleep(1)
    pytest.fail("the gateway did not come back after the reload")


async def test_live_sops(live_client: Client) -> None:
    client, sops = live_client, live_client.sops
    sop: dict[str, Any] = {
        "name": LIVE_NAME,
        "description": "Python SDK live test",
        "version": "1.0.0",
        "priority": "low",
        "execution_mode": "supervised",
        "triggers": [{"type": "manual"}],
        "steps": [
            {"number": 1, "title": "Greet", "body": "Reply with hi.", "requires_confirmation": True}
        ],
    }
    try:
        await sops.create(sop)
    except ZeroClawError as exc:
        skip_unoffered("SOPs", exc)
        raise
    run_ids: list[str] = []
    try:
        await sops.get(LIVE_NAME)
        sop["description"] = "Python SDK live test, saved"
        await sops.save(LIVE_NAME, sop)
        await sops.graph(LIVE_NAME)
        await sops.graph_draft(sop)
        await sops.graph_legend()
        await sops.trigger_sources()
        try:
            await sops.wire_draft(sop, {"op": "noop"})
        except ZeroClawError as exc:
            if status_code(exc) == 0:
                raise  # the gateway may refuse an edit it does not know

        # The engine loads SOPs when the daemon starts: reload it (an admin
        # route, gateway host only) and wait for the gateway to come back.
        try:
            await client.system.reload()
        except ZeroClawError as exc:
            skip_unoffered("running SOPs (needs a daemon reload)", exc)
            raise
        await wait_healthy(client)

        async with await sops.watch_runs() as feed:
            try:
                run_id = await sops.run(LIVE_NAME, json.dumps({"from": LIVE_NAME}))
            except ZeroClawError as exc:
                # Runs need the engine: sop.sops_dir set, then a reload.
                skip_unoffered("running SOPs", exc)
                raise
            # The engine audits every run into memory as sop_run_<id>.
            run_ids.append(run_id)
            async with asyncio.timeout(10):
                while True:
                    frame = await feed.next()
                    assert frame is not None, "watch runs: the feed closed"
                    if run_id in json.dumps(frame):
                        break
        runs = await sops.runs(LIVE_NAME)
        assert any(r.run_id == run_id for r in runs), f"run {run_id} not listed"
        await sops.run_overlay(LIVE_NAME, run_id)

        # The supervised run waits for an operator before its first step.
        try:
            print(f"pending approvals: {len(await sops.pending())}")
        except ZeroClawError as exc:
            print(f"pending (admin, gateway host only): {exc}")
        try:
            await sops.decide(LIVE_NAME, run_id, Decision.deny(LIVE_NAME))
        except ZeroClawError as exc:
            print(f"decide: {exc}")
        try:
            await sops.cancel(LIVE_NAME, run_id, LIVE_NAME)
        except ZeroClawError as exc:
            print(f"cancel (the run may have ended): {exc}")
        # A second run, for the host-only approve and deny routes.
        second = await sops.run(LIVE_NAME)
        run_ids.append(second)
        try:
            await sops.deny(second, LIVE_NAME)
        except ZeroClawError as exc:
            print(f"deny (admin, gateway host only): {exc}")
            await quietly(lambda: sops.cancel(LIVE_NAME, second, LIVE_NAME))
        await sops.delete(LIVE_NAME)
    finally:
        await quietly(lambda: sops.delete(LIVE_NAME))
        for rid in run_ids:
            await quietly(partial(client.memory.forget, f"sop_run_{rid}"))


async def test_live_admin(live_client: Client) -> None:
    client, pairing = live_client, live_client.pairing
    try:
        await pairing.admin_code()
    except ZeroClawError as exc:
        skip_unoffered("admin routes", exc)
        raise
    await pairing.initial_code()
    await pairing.admin_new_code()

    # The legacy pairing route, with a code minted for it. The new device is
    # the one the list did not have before.
    before = {d.id for d in await pairing.devices()}
    code = await pairing.new_code()
    legacy = await pairing.pair_legacy(code)
    after = await client.with_token(legacy.token).pairing.devices()
    for d in after:
        if d.id not in before:
            await pairing.revoke_device(d.id)

    # Already on the current schema: nothing to migrate.
    m = await client.config.migrate()
    print(f"migrate: migrated={m.migrated} schema={m.schema_version}")


def b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


@dataclass
class SoftKey:
    """A software WebAuthn authenticator: an ES256 key that signs as a hardware key would."""

    origin: str
    rp_id: str
    key: ec.EllipticCurvePrivateKey = field(
        default_factory=lambda: ec.generate_private_key(ec.SECP256R1())
    )
    count: int = 0

    @property
    def id(self) -> str:
        x = self.key.public_key().public_numbers().x.to_bytes(32, "big")
        return b64(f"{LIVE_NAME}-".encode() + x[:8])

    def client_data(self, kind: str, challenge: str) -> bytes:
        data = {"type": kind, "challenge": challenge, "origin": self.origin, "crossOrigin": False}
        return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()

    def register(self, challenge: str) -> dict[str, Any]:
        """Answer a creation challenge in the attestation form the gateway's enrollment accepts."""
        point = self.key.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
        attestation = json.dumps({"public_key": b64(point), "sign_count": 0}).encode()
        return {
            "challenge": challenge,
            "id": self.id,
            "attestation_object": b64(attestation),
            "client_data_json": b64(self.client_data("webauthn.create", challenge)),
            "label": LIVE_NAME,
        }

    def sign(self, challenge: str, valid: bool) -> dict[str, Any]:
        """Answer a request challenge; without ``valid``, the signature is over other data."""
        self.count += 1
        rp_hash = hashlib.sha256(self.rp_id.encode()).digest()
        # User present + verified, then the counter.
        auth_data = rp_hash + b"\x05" + self.count.to_bytes(4, "big")
        client_data = self.client_data("webauthn.get", challenge)
        digest = hashlib.sha256(auth_data + hashlib.sha256(client_data).digest()).digest()
        if not valid:
            digest = hashlib.sha256(b"forged").digest()
        sig = self.key.sign(digest, ec.ECDSA(Prehashed(hashes.SHA256())))
        return {
            "challenge": challenge,
            "id": self.id,
            "authenticator_data": b64(auth_data),
            "client_data_json": b64(client_data),
            "signature": b64(sig),
        }


def challenge_of(options: Any) -> str:
    """Return the challenge of a ceremony's options."""
    challenge = options.get("challenge") if isinstance(options, dict) else None
    if not isinstance(challenge, str) or not challenge:
        pytest.fail(f"no challenge in {options}")
    return challenge


async def test_live_webauthn(live_client: Client) -> None:
    client, w = live_client, live_client.webauthn
    try:
        await w.credentials(LIVE_NAME)
    except ZeroClawError as exc:
        skip_unoffered("WebAuthn", exc)
        raise
    origin = (await client.config.get("security.webauthn.rp_origin")).value
    rp_id = (await client.config.get("security.webauthn.rp_id")).value
    key = SoftKey(
        origin if isinstance(origin, str) else "", rp_id if isinstance(rp_id, str) else ""
    )
    try:
        # Registration: the gateway's challenge, signed into a credential.
        creation = await w.register_start(LIVE_NAME, LIVE_NAME)
        await w.register_finish(key.register(challenge_of(creation)))
        creds = json.dumps(await w.credentials(LIVE_NAME))
        assert key.id in creds, f"the new key is not listed: {creds}"

        # Authentication, twice: the sign counter must rise each time.
        for _ in range(2):
            request = await w.auth_start(LIVE_NAME)
            await w.auth_finish(key.sign(challenge_of(request), True))
        # A replayed counter (a cloned key) and a forged signature are refused.
        request = await w.auth_start(LIVE_NAME)
        key.count -= 1
        with pytest.raises(ZeroClawError) as replayed:
            await w.auth_finish(key.sign(challenge_of(request), True))
        assert is_unauthorized(replayed.value), f"a counter that did not rise: {replayed.value}"
        request = await w.auth_start(LIVE_NAME)
        with pytest.raises(ZeroClawError) as forged:
            await w.auth_finish(key.sign(challenge_of(request), False))
        assert is_unauthorized(forged.value), f"a forged signature: {forged.value}"

        await w.delete_credential(LIVE_NAME, key.id)
        creds = json.dumps(await w.credentials(LIVE_NAME))
        assert key.id not in creds, f"the key is still listed: {creds}"
    finally:
        await quietly(lambda: w.delete_credential(LIVE_NAME, key.id))


async def test_live_a2a(live_client: Client, agent: str) -> None:
    webhook = live_client.webhook
    try:
        await webhook.agent_card(agent)
    except ZeroClawError as exc:
        skip_unoffered("A2A", exc)
        raise
    if not TURNS:
        pytest.skip("ZEROCLAW_TURNS=1 to send an A2A message")
    reply = await webhook.a2a_send(agent, "Reply with the single word: pong")
    print(f"a2a reply: {reply!r}")


async def test_live_turns(live_client: Client, agent: str) -> None:
    if not TURNS:
        pytest.skip("ZEROCLAW_TURNS=1 to start agent turns (they spend tokens)")
    client = live_client
    async with await client.chat(agent, name=LIVE_NAME) as chat:
        reply = await chat.ask("Reply with the single word: pong")
        print(f"chat reply: {reply.full_response!r} ({reply.model})")
        await chat.send("Reply with the single word: ping")
        while True:
            frame = await chat.next_frame()
            assert frame is not None, "next frame: the chat closed"
            if frame.type in (FRAME_DONE, FRAME_ERROR):
                break
        session_id = chat.session_id

    sessions = client.sessions
    key = f"gw_{session_id}"
    try:
        await sessions.messages(key)
        await sessions.state(key)
        await sessions.rename(key, f"{LIVE_NAME}-renamed")
        try:
            await sessions.add_message(key, f"note from {LIVE_NAME}")
        except ZeroClawError as exc:
            skip_unoffered("adding messages", exc)
            raise
        await sessions.abort(key)
        await sessions.delete(key)
    finally:
        await quietly(lambda: sessions.delete(key))

    # A webhook turn, then the same idempotency key again: the gateway must
    # not run it twice.
    webhook = client.webhook
    idempotency_key = f"{LIVE_NAME}-{time.strftime('%H%M%S')}.{int(time.time() * 1000) % 1000:03d}"
    try:
        first = await webhook.send(
            "Reply with the single word: pong", agent=agent, idempotency_key=idempotency_key
        )
    except ZeroClawError as exc:
        skip_unoffered("webhook", exc)
        raise
    assert not first.duplicate, f"first webhook: {first}"
    assert first.reply is not None, f"first webhook: {first}"
    again = await webhook.send(
        "Reply with the single word: pong", agent=agent, idempotency_key=idempotency_key
    )
    assert again.duplicate, f"the duplicate ran again: {again}"


async def test_live_events(live_client: Client, agent: str) -> None:
    # A manual cron run publishes a cron_result: subscribe, run, wait.
    client, cron = live_client, live_client.cron
    job = await cron.create(
        NewCronJob(
            agent=agent,
            name=f"{LIVE_NAME}-events",
            schedule="0 0 1 1 *",
            job_type="shell",
            command=f"echo {LIVE_NAME}",
        )
    )
    run: asyncio.Task[Any] | None = None
    try:
        async with asyncio.timeout(30), await client.events.subscribe() as events:
            run = asyncio.create_task(cron.run(job.id))
            while True:
                try:
                    e = await events.next()
                except DecodeError:
                    continue
                assert e is not None, f"no cron_result for {job.id}: the stream ended"
                if e.kind == "cron_result" and e.get("job_id") == job.id:
                    print(f"cron_result for {job.id}")
                    break
    finally:
        if run is not None:
            run.cancel()
            with contextlib.suppress(asyncio.CancelledError, ZeroClawError):
                await run
        await quietly(lambda: cron.delete(job.id))
