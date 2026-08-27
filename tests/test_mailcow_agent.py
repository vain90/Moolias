from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import pytest

from moolias.mailcow_agent import (
    AgentCooldownError,
    AgentExternalPolicyError,
    AgentStateStore,
    create_agent_app,
)
from moolias.sender_protocol import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    request_signature,
)

SECRET = "a" * 64


def _signed_headers(
    path: str,
    body: bytes,
    *,
    timestamp: int,
    nonce: str,
) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: str(timestamp),
        NONCE_HEADER: nonce,
        SIGNATURE_HEADER: request_signature(
            SECRET,
            "POST",
            path,
            timestamp,
            nonce,
            body,
        ),
    }


def test_state_store_blocks_exact_mailbox_and_enforces_per_mailbox_cooldown(tmp_path):
    now = [1000.0]
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "postfix-policy" / "blocked_sender_login.pcre"
    store = AgentStateStore(
        state_dir,
        cooldown_seconds=10,
        policy_path=policy_path,
        clock=lambda: now[0],
    )
    store.ensure_files()

    changed = store.set_blocked("User+tag@example.org", True)
    assert changed["blocked"] is True
    assert changed["managed"] is True
    assert changed["changed"] is True
    assert changed["retry_after"] == 10

    pcre = policy_path.read_text(encoding="utf-8")
    assert "/^user\\+tag@example\\.org$/" in pcre
    assert "__moolias_blocked_primary_sender__" in pcre
    assert not (state_dir / "blocked_sender_login.pcre").exists()

    with pytest.raises(AgentCooldownError) as error:
        store.set_blocked("user+tag@example.org", False)
    assert error.value.retry_after == 10

    # Cooldowns are isolated per mailbox, so another user is not delayed.
    second = store.set_blocked("other@example.org", True)
    assert second["changed"] is True

    now[0] += 10
    cleared = store.set_blocked("USER+TAG@example.org", False)
    assert cleared["blocked"] is False

    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert "user+tag@example.org" not in state["blocked"]
    assert "other@example.org" in state["blocked"]


def test_external_sender_rule_is_reported_but_not_modified(tmp_path):
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "state.json").write_text(
        json.dumps(
            {
                "version": 1,
                "blocked": [],
                "external_blocked": ["external@example.org"],
                "last_changed": {},
            }
        ),
        encoding="utf-8",
    )
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    store = AgentStateStore(state_dir, policy_path=policy_path)
    store.ensure_files()

    status = store.status("EXTERNAL@example.org")
    assert status["blocked"] is True
    assert status["managed"] is False
    assert status["retry_after"] == 0

    already_blocked = store.set_blocked("external@example.org", True)
    assert already_blocked["blocked"] is True
    assert already_blocked["managed"] is False
    assert already_blocked["changed"] is False

    with pytest.raises(AgentExternalPolicyError):
        store.set_blocked("external@example.org", False)

    assert "external@example" not in policy_path.read_text(encoding="utf-8")


def test_same_state_is_idempotent_without_rewriting_policy(tmp_path):
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    store = AgentStateStore(
        state_dir,
        cooldown_seconds=10,
        policy_path=policy_path,
        clock=lambda: 1000.0,
    )
    store.ensure_files()

    first = store.set_blocked("same@example.org", True)
    assert first["changed"] is True
    before_content = policy_path.read_bytes()
    before_stat = policy_path.stat()

    repeated = store.set_blocked("SAME@example.org", True)
    assert repeated["blocked"] is True
    assert repeated["changed"] is False
    assert policy_path.read_bytes() == before_content

    after_stat = policy_path.stat()
    assert after_stat.st_ino == before_stat.st_ino
    assert after_stat.st_mtime_ns == before_stat.st_mtime_ns


def test_concurrent_mailbox_changes_do_not_lose_state(tmp_path):
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    first_store = AgentStateStore(
        state_dir,
        cooldown_seconds=10,
        policy_path=policy_path,
        clock=lambda: 1000.0,
    )
    second_store = AgentStateStore(
        state_dir,
        cooldown_seconds=10,
        policy_path=policy_path,
        clock=lambda: 1000.0,
    )
    first_store.ensure_files()

    barrier = threading.Barrier(2)

    def block(store: AgentStateStore, mailbox: str) -> dict[str, object]:
        barrier.wait(timeout=5)
        return store.set_blocked(mailbox, True)

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(block, first_store, "first@example.org")
        second_future = executor.submit(block, second_store, "second@example.org")
        first_result = first_future.result(timeout=5)
        second_result = second_future.result(timeout=5)

    assert first_result["changed"] is True
    assert second_result["changed"] is True

    state = json.loads((state_dir / "state.json").read_text(encoding="utf-8"))
    assert state["blocked"] == ["first@example.org", "second@example.org"]

    policy = policy_path.read_text(encoding="utf-8")
    assert "/^first@example\\.org$/" in policy
    assert "/^second@example\\.org$/" in policy


async def test_agent_requires_valid_signature_and_rejects_replay(tmp_path):
    now = [2000.0]
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    bypass_map_path = tmp_path / "rspamd" / "moolias_firstmail_recipients.map"
    app = create_agent_app(
        secret=SECRET,
        state_dir=state_dir,
        policy_path=policy_path,
        bypass_map_path=bypass_map_path,
        cooldown_seconds=10,
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        unsigned = await client.post("/v1/status", json={"mailbox": "user@example.org"})
        assert unsigned.status_code == 401

        body = b'{"mailbox":"user@example.org"}'
        headers = _signed_headers(
            "/v1/status",
            body,
            timestamp=2000,
            nonce="nonce-abcdefghijklmnop",
        )
        signed = await client.post("/v1/status", content=body, headers=headers)
        assert signed.status_code == 200
        assert signed.json()["mailbox"] == "user@example.org"
        assert signed.json()["managed"] is True

        replay = await client.post("/v1/status", content=body, headers=headers)
        assert replay.status_code == 401


async def test_agent_rejects_client_supplied_regex_and_rate_limits_changes(tmp_path):
    now = [3000.0]
    state_dir = tmp_path / "state"
    policy_path = tmp_path / "policy" / "blocked_sender_login.pcre"
    bypass_map_path = tmp_path / "rspamd" / "moolias_firstmail_recipients.map"
    app = create_agent_app(
        secret=SECRET,
        state_dir=state_dir,
        policy_path=policy_path,
        bypass_map_path=bypass_map_path,
        cooldown_seconds=10,
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)

    async def post(client, path, payload, nonce):
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        headers = _signed_headers(path, body, timestamp=int(now[0]), nonce=nonce)
        return await client.post(path, content=body, headers=headers)

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        extra = await post(
            client,
            "/v1/protection",
            {
                "mailbox": "user@example.org",
                "blocked": True,
                "pattern": "/.*/",
            },
            "nonce-extra-abcdefghijkl",
        )
        assert extra.status_code == 400

        blocked = await post(
            client,
            "/v1/protection",
            {"mailbox": "user@example.org", "blocked": True},
            "nonce-block-abcdefghijkl",
        )
        assert blocked.status_code == 200
        assert blocked.json()["blocked"] is True

        too_fast = await post(
            client,
            "/v1/protection",
            {"mailbox": "user@example.org", "blocked": False},
            "nonce-unblock-abcdefghij",
        )
        assert too_fast.status_code == 429
        assert too_fast.headers["Retry-After"] == "10"

        # A malicious mailbox string cannot become a PCRE expression.
        invalid = await post(
            client,
            "/v1/protection",
            {"mailbox": "victim@example.org\n/.*/", "blocked": True},
            "nonce-invalid-abcdefghij",
        )
        assert invalid.status_code == 400

    pcre = Path(policy_path).read_text(encoding="utf-8")
    assert "/.*/" not in pcre
