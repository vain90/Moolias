from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest

from moolias.alias_delivery_agent import AliasDeliveryAgentClient, AliasDeliveryAgentError

DOMAIN = "moolias-sender-agent.test"
MAILBOX = f"owner@{DOMAIN}"
ALIAS = f"service@{DOMAIN}"
MAP_RELATIVE_PATH = Path(
    "data/conf/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map"
)
RSPAMD_MAP_PATH = "/etc/rspamd/custom/moolias-sender-agent/moolias_firstmail_recipients.map"


def _agent_secret(mailcow_dir: Path) -> str:
    env_path = mailcow_dir / "data/conf/moolias-sender-agent/agent.env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
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


async def test_exact_first_delivery_bypass_updates_rspamd_map_and_survives_restart() -> None:
    base_url = os.environ.get("MAILCOW_URL")
    mailcow_dir_value = os.environ.get("MAILCOW_DIR")
    if not base_url or not mailcow_dir_value:
        pytest.skip("real Mailcow integration environment is not configured")

    mailcow_dir = Path(mailcow_dir_value)
    secret = _agent_secret(mailcow_dir)
    client = AliasDeliveryAgentClient(
        f"{base_url.rstrip('/')}/moolias-agent",
        secret,
        verify_tls=False,
        timeout=10.0,
    )

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
            ["docker", "compose", "restart", "moolias-sender-agent"],
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
