from __future__ import annotations

import json
import os
import re
import smtplib
import ssl
import subprocess
import time

import httpx
import pytest

from moolias.sender_protection import (
    SenderAgentClient,
    SenderAgentExternalPolicy,
)

DOMAIN = "moolias-sender-agent.test"
MAILBOX = f"owner@{DOMAIN}"
ALIAS = f"service@{DOMAIN}"
PASSWORD = "Moolias-Sender-Agent-CI-4f9d!A7"
LEGACY_MAILBOX = "legacy.blocked@example.org"
LEGACY_MAILBOX_2 = "legacy.second@example.org"
BLOCKED_OWNER = "__moolias_blocked_primary_sender__"
PCRE_MAP = "pcre:/opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre"
LEGACY_MAP = "pcre:/opt/postfix/conf/blocked_sender_login.pcre"
POLICY_PATH = "/opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre"


def _scenario() -> str:
    value = os.environ.get("MOOLIAS_TEST_SCENARIO", "fresh")
    if value not in {"fresh", "legacy-import", "legacy-keep"}:
        raise AssertionError(f"Unknown sender protection integration scenario: {value}")
    return value


def _result_types(body: object) -> list[str]:
    entries = body if isinstance(body, list) else [body]
    return [
        str(entry.get("type", "")).strip().casefold()
        for entry in entries
        if isinstance(entry, dict)
    ]


async def _post_success(
    admin: httpx.AsyncClient,
    path: str,
    payload: dict[str, object],
) -> None:
    response = await admin.post(path, json=payload)
    response.raise_for_status()
    body = response.json()
    if "success" not in _result_types(body):
        raise AssertionError(f"Mailcow {path} did not report success: {body!r}")


def _smtp_envelope(sender: str) -> tuple[int, str, int, str]:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE

    with smtplib.SMTP("127.0.0.1", 587, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(MAILBOX, PASSWORD)
        mail_code, mail_response = smtp.mail(sender)
        rcpt_code, rcpt_response = smtp.rcpt(MAILBOX)
        return (
            mail_code,
            mail_response.decode("utf-8", errors="replace"),
            rcpt_code,
            rcpt_response.decode("utf-8", errors="replace"),
        )


def _smtp_envelope_when_ready(sender: str) -> tuple[int, str, int, str]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            return _smtp_envelope(sender)
        except (OSError, smtplib.SMTPException) as exc:
            last_error = exc
            time.sleep(1)
    raise AssertionError(f"Mailcow submission did not become ready: {last_error!r}")


def _sogo_envelope(mailcow_dir: str, sender: str) -> tuple[int, str, int, str]:
    script = r"""
import json
import smtplib
import ssl
import sys

mailbox, password, sender = sys.argv[1:4]
context = ssl.create_default_context()
context.check_hostname = False
context.verify_mode = ssl.CERT_NONE

with smtplib.SMTP("postfix-mailcow", 588, timeout=20) as smtp:
    smtp.ehlo()
    smtp.starttls(context=context)
    smtp.ehlo()
    smtp.login(mailbox, password)
    mail_code, mail_response = smtp.mail(sender)
    rcpt_code, rcpt_response = smtp.rcpt(mailbox)

print(json.dumps([
    mail_code,
    mail_response.decode("utf-8", errors="replace"),
    rcpt_code,
    rcpt_response.decode("utf-8", errors="replace"),
]))
"""
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "moolias-sender-agent",
            "python",
            "-c",
            script,
            MAILBOX,
            PASSWORD,
            sender,
        ],
        cwd=mailcow_dir,
        check=False,
        text=True,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(
            "SOGo-path SMTP client failed:\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    payload = json.loads(result.stdout)
    return (
        int(payload[0]),
        str(payload[1]),
        int(payload[2]),
        str(payload[3]),
    )


def _postfix_container_id(mailcow_dir: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", "postfix-mailcow"],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _agent_container_id(mailcow_dir: str) -> str:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", "moolias-sender-agent"],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout.strip()


def _postfix_map_query(mailcow_dir: str, mailbox: str) -> tuple[str, str]:
    lookup_result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "postmap",
            "-q",
            mailbox,
            PCRE_MAP,
        ],
        cwd=mailcow_dir,
        check=False,
        text=True,
        capture_output=True,
    )
    if lookup_result.returncode not in {0, 1}:
        raise AssertionError(
            "Postfix PCRE lookup failed unexpectedly: "
            f"exit={lookup_result.returncode}, stderr={lookup_result.stderr!r}"
        )
    rendered = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "cat",
            POLICY_PATH,
        ],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    return lookup_result.stdout.strip(), rendered


def _prepare_existing_compose_override(mailcow_dir: str) -> None:
    override = os.path.join(mailcow_dir, "docker-compose.override.yml")
    subprocess.run(
        ["sudo", "tee", override],
        input=(
            "services:\n"
            "    unrelated-test-service:\n"
            "      image: busybox:1.36\n"
            "      command: [\"true\"]\n"
        ),
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
    )


def _prepare_legacy_sender_block(mailcow_dir: str) -> None:
    postfix_dir = os.path.join(mailcow_dir, "data", "conf", "postfix")
    legacy_pcre = os.path.join(postfix_dir, "blocked_sender_login.pcre")
    extra_cf = os.path.join(postfix_dir, "extra.cf")

    subprocess.run(
        ["sudo", "install", "-d", "-m", "0755", postfix_dir],
        check=True,
    )
    subprocess.run(
        ["sudo", "tee", legacy_pcre],
        input=(
            r"/^legacy\.blocked@example\.org$/    __blocked_hidden_sender__" + "\n"
            r"/^legacy\.second@example\.org$/     __blocked_hidden_sender_2__" + "\n"
            r"/^special\..*@example\.net$/        __custom_external_rule__" + "\n"
        ),
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(
        ["sudo", "tee", "-a", extra_cf],
        input=(
            "\nsmtpd_sender_login_maps = "
            f"{LEGACY_MAP}, "
            "proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf\n"
        ),
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
    )


def _installer_env(mailcow_dir: str) -> dict[str, str]:
    scenario = _scenario()
    env = os.environ.copy()
    env["MAILCOW_DIR"] = mailcow_dir
    env["MOOLIAS_AGENT_IMAGE"] = os.environ.get(
        "MOOLIAS_AGENT_IMAGE",
        "moolias:sender-agent-ci",
    )
    env["MOOLIAS_AGENT_COOLDOWN_SECONDS"] = "1"
    env["MOOLIAS_IMPORT_EXISTING_SENDER_RULES"] = (
        "yes" if scenario == "legacy-import" else "no"
    )
    return env


def _run_installer(mailcow_dir: str) -> subprocess.CompletedProcess[str]:
    env = _installer_env(mailcow_dir)
    return subprocess.run(
        [
            "sudo",
            "--preserve-env="
            "MAILCOW_DIR,MOOLIAS_AGENT_IMAGE,MOOLIAS_AGENT_COOLDOWN_SECONDS,"
            "MOOLIAS_IMPORT_EXISTING_SENDER_RULES",
            "bash",
            "scripts/install-mailcow-agent.sh",
        ],
        check=False,
        text=True,
        capture_output=True,
        env=env,
    )


def _install_agent(mailcow_dir: str) -> str:
    result = _run_installer(mailcow_dir)
    if result.returncode != 0:
        raise AssertionError(
            "Moolias Mailcow Agent installer failed:\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}"
        )
    match = re.search(r"^MOOLIAS_SENDER_AGENT_SECRET=(.+)$", result.stdout, re.MULTILINE)
    if match is None:
        raise AssertionError(f"Installer did not print the agent secret:\n{result.stdout}")
    return match.group(1).strip()


def _assert_agent_runtime_hardening(mailcow_dir: str) -> None:
    container_id = _agent_container_id(mailcow_dir)
    assert container_id

    result = subprocess.run(
        ["docker", "inspect", container_id],
        check=True,
        text=True,
        capture_output=True,
    )
    inspected = json.loads(result.stdout)
    container = inspected[0]

    assert container["Config"]["User"] == "10001:10001"
    host_config = container["HostConfig"]
    assert host_config["ReadonlyRootfs"] is True
    assert "ALL" in (host_config.get("CapDrop") or [])
    assert any(
        value.startswith("no-new-privileges")
        for value in (host_config.get("SecurityOpt") or [])
    )
    assert not host_config.get("PortBindings")

    mounts = {mount["Destination"]: mount for mount in container.get("Mounts", [])}
    assert set(mounts) == {"/state", "/postfix-policy", "/rspamd-custom"}, mounts
    assert mounts["/state"]["RW"] is True
    assert mounts["/postfix-policy"]["RW"] is True
    assert mounts["/rspamd-custom"]["RW"] is True
    assert mounts["/postfix-policy"]["Source"].endswith(
        "/data/conf/postfix/moolias-sender-agent"
    )
    assert mounts["/rspamd-custom"]["Source"].endswith(
        "/data/conf/rspamd/custom/moolias-sender-agent"
    )
    assert "/var/run/docker.sock" not in mounts


def _assert_compose_override_preserved(mailcow_dir: str) -> None:
    override = os.path.join(mailcow_dir, "docker-compose.override.yml")
    with open(override, encoding="utf-8") as handle:
        content = handle.read()
    assert "unrelated-test-service:" in content
    assert "# BEGIN MOOLIAS SENDER AGENT" in content
    assert "moolias-sender-agent:" in content
    assert "postfix-mailcow:" not in content


async def test_sender_protection_on_disposable_mailcow() -> None:
    base_url = os.environ.get("MAILCOW_URL")
    api_key = os.environ.get("MAILCOW_API_KEY")
    mailcow_dir = os.environ.get("MAILCOW_DIR")
    if not base_url or not api_key or not mailcow_dir:
        pytest.skip("real Mailcow integration environment is not configured")

    scenario = _scenario()
    _prepare_existing_compose_override(mailcow_dir)
    if scenario.startswith("legacy-"):
        _prepare_legacy_sender_block(mailcow_dir)

    secret = _install_agent(mailcow_dir)
    _assert_agent_runtime_hardening(mailcow_dir)
    _assert_compose_override_preserved(mailcow_dir)

    extra_cf = os.path.join(mailcow_dir, "data", "conf", "postfix", "extra.cf")
    with open(extra_cf, encoding="utf-8") as handle:
        extra_content = handle.read()
    assert PCRE_MAP in extra_content
    assert "proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf" in extra_content

    if scenario.startswith("legacy-"):
        assert LEGACY_MAP in extra_content
        legacy_path = os.path.join(
            mailcow_dir,
            "data",
            "conf",
            "postfix",
            "blocked_sender_login.pcre",
        )
        with open(legacy_path, encoding="utf-8") as handle:
            legacy_content = handle.read()
        assert r"/^special\..*@example\.net$/" in legacy_content
        if scenario == "legacy-import":
            assert "legacy\\.blocked@example\\.org" not in legacy_content
            assert "legacy\\.second@example\\.org" not in legacy_content
        else:
            assert "legacy\\.blocked@example\\.org" in legacy_content
            assert "legacy\\.second@example\\.org" in legacy_content
    else:
        assert LEGACY_MAP not in extra_content

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
                "aliases": 10,
                "backupmx": 0,
                "defquota": 128,
                "description": "Moolias sender agent integration",
                "domain": DOMAIN,
                "mailboxes": 2,
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
                "name": "Moolias Sender Agent CI",
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
                "address": ALIAS,
                "goto": MAILBOX,
                "private_comment": "moolias-sender-agent-integration",
                "public_comment": "",
                "sender_allowed": 1,
                "sogo_visible": 1,
            },
        )

    baseline_primary = _smtp_envelope_when_ready(MAILBOX)
    baseline_alias = _smtp_envelope_when_ready(ALIAS)
    assert baseline_primary[0] == 250 and baseline_primary[2] == 250, baseline_primary
    assert baseline_alias[0] == 250 and baseline_alias[2] == 250, baseline_alias

    public_agent_url = f"{base_url.rstrip('/')}/moolias-agent"
    async with httpx.AsyncClient(
        base_url=f"{public_agent_url}/",
        timeout=10.0,
        trust_env=False,
    ) as unauthenticated:
        health = await unauthenticated.get("healthz")
        assert health.status_code == 200
        unsigned = await unauthenticated.post(
            "v1/protection",
            json={"mailbox": MAILBOX, "blocked": True},
        )
        assert unsigned.status_code == 401

    postfix_id = _postfix_container_id(mailcow_dir)
    assert postfix_id

    active_maps = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "postconf",
            "-c",
            "/opt/postfix/conf",
            "smtpd_sender_login_maps",
        ],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout
    assert PCRE_MAP in active_maps
    if scenario.startswith("legacy-"):
        assert LEGACY_MAP in active_maps

    for service in ("smtps", "submission", "588"):
        max_use = subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "postfix-mailcow",
                "postconf",
                "-c",
                "/opt/postfix/conf",
                "-P",
                f"{service}/inet/max_use",
            ],
            cwd=mailcow_dir,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        assert re.search(r"=\s*1\s*$", max_use), max_use

    async with SenderAgentClient(
        public_agent_url,
        secret,
        verify_tls=False,
    ) as agent:
        await agent.probe()

        if scenario == "legacy-import":
            migrated = await agent.status(LEGACY_MAILBOX)
            migrated_2 = await agent.status(LEGACY_MAILBOX_2)
            assert migrated.blocked is True and migrated.managed is True
            assert migrated_2.blocked is True and migrated_2.managed is True
        elif scenario == "legacy-keep":
            external = await agent.status(LEGACY_MAILBOX)
            assert external.blocked is True
            assert external.managed is False
            with pytest.raises(SenderAgentExternalPolicy):
                await agent.set_blocked(LEGACY_MAILBOX, False)

        initial = await agent.status(MAILBOX)
        assert initial.blocked is False
        assert initial.managed is True

        blocked, changed = await agent.set_blocked(MAILBOX, True)
        assert changed is True
        assert blocked.blocked is True

        lookup, rendered = _postfix_map_query(mailcow_dir, MAILBOX)
        assert lookup == BLOCKED_OWNER, rendered

        blocked_primary = _smtp_envelope_when_ready(MAILBOX)
        allowed_alias = _smtp_envelope_when_ready(ALIAS)
        assert blocked_primary[0] == 250 and blocked_primary[2] >= 500, blocked_primary
        assert allowed_alias[0] == 250 and allowed_alias[2] == 250, allowed_alias

        blocked_sogo = _sogo_envelope(mailcow_dir, MAILBOX)
        allowed_sogo_alias = _sogo_envelope(mailcow_dir, ALIAS)
        assert blocked_sogo[0] == 250 and blocked_sogo[2] >= 500, blocked_sogo
        assert allowed_sogo_alias[0] == 250 and allowed_sogo_alias[2] == 250, allowed_sogo_alias
        assert _postfix_container_id(mailcow_dir) == postfix_id

        time.sleep(1.1)
        unblocked, changed = await agent.set_blocked(MAILBOX, False)
        assert changed is True
        assert unblocked.blocked is False

        lookup, rendered = _postfix_map_query(mailcow_dir, MAILBOX)
        assert lookup == "", rendered

    allowed_primary = _smtp_envelope_when_ready(MAILBOX)
    assert allowed_primary[0] == 250 and allowed_primary[2] == 250, allowed_primary
    assert _postfix_container_id(mailcow_dir) == postfix_id

    rerun = _run_installer(mailcow_dir)
    assert rerun.returncode == 0, rerun.stderr
    _assert_compose_override_preserved(mailcow_dir)
