from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from moolias.alias_delivery_agent import AliasDeliveryAgentClient, AliasDeliveryAgentError
from moolias.alias_wait import AliasWaitService
from moolias.alias_workflows import AliasWorkflowStore

DOMAIN = "moolias-agent.test"
MAILBOX = f"owner@{DOMAIN}"
ALIAS = f"service@{DOMAIN}"
MAP_RELATIVE_PATH = Path(
    "data/conf/rspamd/custom/moolias-agent/moolias_firstmail_recipients.map"
)
RSPAMD_MAP_PATH = "/etc/rspamd/custom/moolias-agent/moolias_firstmail_recipients.map"


def _agent_secret(mailcow_dir: Path) -> str:
    env_path = mailcow_dir / "data/conf/moolias-agent/agent.env"
    result = subprocess.run(
        ["sudo", "cat", str(env_path)],
        check=True,
        text=True,
        capture_output=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("MOOLIAS_AGENT_SECRET="):
            return line.split("=", 1)[1].strip()
    raise AssertionError("Mailcow Agent secret is missing")


def _map_recipients(mailcow_dir: Path) -> set[str]:
    path = mailcow_dir / MAP_RELATIVE_PATH
    return {
        line.strip().casefold()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def _rspamd_map_contains(mailcow_dir: Path, recipient: str) -> bool:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "rspamd-mailcow",
            "grep",
            "-Fx",
            recipient,
            RSPAMD_MAP_PATH,
        ],
        cwd=mailcow_dir,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode not in {0, 1}:
        raise AssertionError(
            f"Rspamd recipient-map lookup failed: {result.stderr or result.stdout}"
        )
    return result.returncode == 0


async def _wait_for_agent(client: AliasDeliveryAgentClient, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            await client.probe()
            return
        except AliasDeliveryAgentError as exc:
            last_error = exc
            time.sleep(0.5)
    raise AssertionError(f"Mailcow Agent did not become ready: {last_error!r}")


def _real_agent() -> tuple[Path, AliasDeliveryAgentClient] | None:
    base_url = os.environ.get("MAILCOW_URL")
    mailcow_dir_value = os.environ.get("MAILCOW_DIR")
    if not base_url or not mailcow_dir_value:
        return None

    mailcow_dir = Path(mailcow_dir_value)
    return (
        mailcow_dir,
        AliasDeliveryAgentClient(
            f"{base_url.rstrip('/')}/moolias-agent",
            _agent_secret(mailcow_dir),
            verify_tls=False,
            timeout=10.0,
        ),
    )


async def test_exact_first_delivery_bypass_updates_rspamd_map_and_survives_restart() -> None:
    real_agent = _real_agent()
    if real_agent is None:
        pytest.skip("real Mailcow integration environment is not configured")
    mailcow_dir, client = real_agent

    try:
        await client.probe()

        await client.set_bypass((ALIAS, MAILBOX), int(time.time()) + 60)
        assert _map_recipients(mailcow_dir) == {ALIAS.casefold(), MAILBOX.casefold()}
        assert _rspamd_map_contains(mailcow_dir, ALIAS)
        assert _rspamd_map_contains(mailcow_dir, MAILBOX)

        await client.clear_bypass((ALIAS, MAILBOX))
        assert _map_recipients(mailcow_dir) == set()
        assert not _rspamd_map_contains(mailcow_dir, ALIAS)
        assert not _rspamd_map_contains(mailcow_dir, MAILBOX)

        await client.set_bypass((ALIAS,), int(time.time()) + 5)
        assert _map_recipients(mailcow_dir) == {ALIAS.casefold()}

        subprocess.run(
            ["docker", "compose", "restart", "moolias-agent"],
            cwd=mailcow_dir,
            check=True,
            text=True,
            capture_output=True,
        )
        await _wait_for_agent(client)

        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and ALIAS.casefold() in _map_recipients(mailcow_dir):
            time.sleep(0.5)

        assert _map_recipients(mailcow_dir) == set()
        assert not _rspamd_map_contains(mailcow_dir, ALIAS)
    finally:
        await client.close()


async def test_existing_alias_wait_reuses_exact_agent_bypass(tmp_path) -> None:
    real_agent = _real_agent()
    if real_agent is None:
        pytest.skip("real Mailcow integration environment is not configured")
    mailcow_dir, client = real_agent

    store = AliasWorkflowStore(tmp_path / "alias-wait.sqlite3")
    await store.initialize()
    waits = AliasWaitService(store)
    now = int(time.time())

    try:
        await client.probe()
        workflow = await waits.start(
            mailbox=MAILBOX,
            alias_id=77,
            address=ALIAS,
            alias_name="Service",
            alias_description="Verification",
            started_at=now,
            bypass_expires_at=now + 60,
        )
        assert workflow.bypass_recipients == (ALIAS,)

        await client.set_bypass(workflow.bypass_recipients, workflow.bypass_expires_at)
        assert _map_recipients(mailcow_dir) == {ALIAS.casefold()}
        assert _rspamd_map_contains(mailcow_dir, ALIAS)

        restarted = await waits.start(
            mailbox=MAILBOX,
            alias_id=77,
            address=ALIAS,
            alias_name="Service",
            alias_description="Verification",
            started_at=now + 1,
            bypass_expires_at=now + 90,
        )
        assert restarted.id == workflow.id
        assert restarted.bypass_recipients == (ALIAS,)
        assert restarted.bypass_expires_at == now + 90

        await client.set_bypass(restarted.bypass_recipients, restarted.bypass_expires_at)
        assert _map_recipients(mailcow_dir) == {ALIAS.casefold()}

        await client.clear_bypass(restarted.bypass_recipients)
        assert _map_recipients(mailcow_dir) == set()
        assert not _rspamd_map_contains(mailcow_dir, ALIAS)
    finally:
        await client.close()
