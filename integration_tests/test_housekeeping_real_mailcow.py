from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import httpx
import pytest

from moolias.config import Settings
from moolias.housekeeping import load_mailcow_inventory, run_housekeeping
from moolias.mailcow import MailcowClient
from moolias.usage_evidence import UsageEvidenceEvent, UsageEvidenceStore

DOMAIN = "housekeeping.moolias-ci.test"
MAILBOX = f"owner@{DOMAIN}"
VALID_ALIAS = f"current@{DOMAIN}"
STALE_ALIAS = f"removed@{DOMAIN}"
PASSWORD = "Moolias-Housekeeping-CI-4f9d!A7"


async def _post_success(
    admin: httpx.AsyncClient,
    path: str,
    payload: dict[str, object],
) -> object:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    entries = body if isinstance(body, list) else [body]
    if not any(
        isinstance(entry, dict) and str(entry.get("type", "")).casefold() == "success"
        for entry in entries
    ):
        raise AssertionError(f"Mailcow {path} did not report success: {body!r}")
    return body


def _settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="http://moolias-housekeeping-ci.test",
        MOOLIAS_SESSION_SECRET="h" * 64,
        MAILCOW_URL=os.environ["MAILCOW_URL"],
        MAILCOW_API_KEY=os.environ["MAILCOW_API_KEY"],
        MAILCOW_OAUTH_CLIENT_ID="integration-not-used",
        MAILCOW_OAUTH_CLIENT_SECRET="integration-not-used",
        MAILCOW_VERIFY_TLS=False,
    )


@pytest.fixture(scope="module")
async def housekeeping_mailcow_inventory() -> frozenset[str]:
    base_url = os.environ.get("MAILCOW_URL")
    api_key = os.environ.get("MAILCOW_API_KEY")
    if not base_url or not api_key:
        pytest.skip("real Mailcow integration environment is not configured")

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={"X-API-Key": api_key, "Accept": "application/json"},
        timeout=30.0,
        trust_env=False,
    ) as admin:
        await _post_success(
            admin,
            "/api/v1/add/domain",
            {
                "active": 1,
                "aliases": 20,
                "backupmx": 0,
                "defquota": 128,
                "description": "Disposable Moolias housekeeping domain",
                "domain": DOMAIN,
                "mailboxes": 5,
                "maxquota": 512,
                "quota": 1024,
                "relay_all_recipients": 0,
                "rl_frame": "s",
                "rl_value": 10,
                "restart_sogo": 0,
            },
        )
        await _post_success(
            admin,
            "/api/v1/add/mailbox",
            {
                "active": 1,
                "domain": DOMAIN,
                "local_part": "owner",
                "name": "Moolias Housekeeping CI",
                "password": PASSWORD,
                "password2": PASSWORD,
                "quota": 128,
                "force_pw_update": 0,
                "tls_enforce_in": 0,
                "tls_enforce_out": 0,
            },
        )
        await _post_success(
            admin,
            "/api/v1/add/alias",
            {
                "active": 1,
                "address": VALID_ALIAS,
                "goto": MAILBOX,
                "goto_ham": 0,
                "goto_null": 0,
                "goto_spam": 0,
                "private_comment": "",
                "public_comment": "Housekeeping current alias",
                "sender_allowed": 1,
                "sogo_visible": 0,
            },
        )

    client = MailcowClient(_settings())
    try:
        inventory = await load_mailcow_inventory(client)
    finally:
        await client.close()

    assert MAILBOX in inventory.addresses
    assert VALID_ALIAS in inventory.addresses
    assert STALE_ALIAS not in inventory.addresses
    return inventory.addresses


async def test_housekeeping_dry_run_and_apply_against_real_mailcow(
    housekeeping_mailcow_inventory: frozenset[str],
    tmp_path: Path,
) -> None:
    stats_db = tmp_path / "moolias-stats.sqlite3"
    newsletter_db = tmp_path / "moolias-newsletters.sqlite3"
    evidence = UsageEvidenceStore(stats_db)

    await evidence.record_events(
        [
            UsageEvidenceEvent(
                mailbox=MAILBOX,
                alias=VALID_ALIAS,
                event_at=100,
            ),
            UsageEvidenceEvent(
                mailbox=MAILBOX,
                alias=STALE_ALIAS,
                event_at=101,
            ),
        ],
        source="live",
    )

    dry_run = run_housekeeping(
        stats_db=stats_db,
        newsletter_db=newsletter_db,
        valid_addresses=housekeeping_mailcow_inventory,
    )
    assert [entry.address for entry in dry_run.candidates] == [STALE_ALIAS]

    with sqlite3.connect(stats_db) as connection:
        before = connection.execute(
            "SELECT COUNT(*) FROM alias_usage_evidence"
        ).fetchone()[0]
    assert before == 2

    applied = run_housekeeping(
        stats_db=stats_db,
        newsletter_db=newsletter_db,
        valid_addresses=housekeeping_mailcow_inventory,
        apply=True,
    )
    assert [entry.address for entry in applied.candidates] == [STALE_ALIAS]

    with sqlite3.connect(stats_db) as connection:
        rows = connection.execute(
            "SELECT alias FROM alias_usage_evidence ORDER BY alias"
        ).fetchall()
    assert rows == [(VALID_ALIAS,)]

    client = MailcowClient(_settings())
    try:
        aliases = await client.list_aliases()
    finally:
        await client.close()
    assert any(alias.address == VALID_ALIAS for alias in aliases)
