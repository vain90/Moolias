from __future__ import annotations

import glob
import json
import os
import re
import subprocess

import pytest

PREVIOUS_SECRET = "moolias-v121-agent-secret-000000000001"
PREVIOUS_BLOCKED = "legacy.upgrade@example.org"
PREVIOUS_PCRE_MAP = (
    "pcre:/opt/postfix/conf/moolias-sender-agent/blocked_sender_login.pcre"
)
CURRENT_PCRE_MAP = "pcre:/opt/postfix/conf/moolias-agent/blocked_sender_login.pcre"
SQL_SENDER_MAP = "proxy:mysql:/opt/postfix/conf/sql/mysql_virtual_sender_acl.cf"


def _sudo_write(path: str, content: str, mode: str = "0644") -> None:
    subprocess.run(
        ["sudo", "tee", path],
        input=content,
        check=True,
        text=True,
        stdout=subprocess.DEVNULL,
    )
    subprocess.run(["sudo", "chmod", mode, path], check=True)


def _sudo_read(path: str) -> str:
    return subprocess.run(
        ["sudo", "cat", path],
        check=True,
        text=True,
        capture_output=True,
    ).stdout


def _prepare_v121_layout(mailcow_dir: str, image: str) -> str:
    postfix_dir = os.path.join(mailcow_dir, "data", "conf", "postfix")
    nginx_dir = os.path.join(mailcow_dir, "data", "conf", "nginx")
    previous_agent_dir = os.path.join(mailcow_dir, "data", "conf", "moolias-sender-agent")
    previous_state_dir = os.path.join(previous_agent_dir, "state")
    previous_policy_dir = os.path.join(postfix_dir, "moolias-sender-agent")

    subprocess.run(
        ["sudo", "install", "-d", "-m", "0755", previous_agent_dir],
        check=True,
    )
    subprocess.run(
        [
            "sudo",
            "install",
            "-d",
            "-m",
            "0700",
            "-o",
            "10001",
            "-g",
            "10001",
            previous_state_dir,
        ],
        check=True,
    )
    subprocess.run(
        [
            "sudo",
            "install",
            "-d",
            "-m",
            "0755",
            "-o",
            "10001",
            "-g",
            "10001",
            previous_policy_dir,
        ],
        check=True,
    )

    _sudo_write(
        os.path.join(previous_agent_dir, "agent.env"),
        (
            f"MOOLIAS_AGENT_SECRET={PREVIOUS_SECRET}\n"
            "MOOLIAS_AGENT_STATE_DIR=/state\n"
            "MOOLIAS_AGENT_POLICY_PATH=/postfix-policy/blocked_sender_login.pcre\n"
            "MOOLIAS_AGENT_COOLDOWN_SECONDS=10\n"
        ),
        "0600",
    )
    state_path = os.path.join(previous_state_dir, "state.json")
    _sudo_write(
        state_path,
        json.dumps(
            {
                "blocked": [PREVIOUS_BLOCKED],
                "external_blocked": [],
                "last_changed": {},
                "version": 1,
            },
            separators=(",", ":"),
        )
        + "\n",
        "0600",
    )
    subprocess.run(["sudo", "chown", "10001:10001", state_path], check=True)

    previous_policy = os.path.join(previous_policy_dir, "blocked_sender_login.pcre")
    _sudo_write(
        previous_policy,
        (
            "# Managed by Moolias Mailcow Agent. Do not edit manually.\n"
            r"/^legacy\.upgrade@example\.org$/    __moolias_blocked_primary_sender__"
            "\n"
        ),
    )
    subprocess.run(["sudo", "chown", "10001:10001", previous_policy], check=True)

    _sudo_write(
        os.path.join(postfix_dir, "extra.cf"),
        (
            "# BEGIN MOOLIAS SENDER PROTECTION\n"
            "# Moolias rules are evaluated before Mailcow's normal SQL sender ACL.\n"
            "smtpd_sender_login_maps =\n"
            f"  {PREVIOUS_PCRE_MAP},\n"
            f"  {SQL_SENDER_MAP}\n"
            "# END MOOLIAS SENDER PROTECTION\n"
        ),
    )

    _sudo_write(
        os.path.join(nginx_dir, "site.moolias-sender-agent.custom"),
        (
            "# Managed by Moolias Sender Protection.\n"
            "location ^~ /moolias-agent/ {\n"
            "    proxy_pass http://moolias-sender-agent:8081/;\n"
            "}\n"
        ),
    )

    override = os.path.join(mailcow_dir, "docker-compose.override.yml")
    _sudo_write(
        override,
        (
            "services:\n"
            "    unrelated-test-service:\n"
            "      image: busybox:1.36\n"
            "      command: [\"true\"]\n"
            "\n"
            "    # BEGIN MOOLIAS SENDER AGENT\n"
            "    moolias-sender-agent:\n"
            f"      image: {image}\n"
            "      command: [\"/bin/sh\", \"-c\", \"sleep 3600\"]\n"
            "      networks:\n"
            "        - mailcow-network\n"
            "    # END MOOLIAS SENDER AGENT\n"
        ),
    )

    subprocess.run(
        ["docker", "compose", "up", "-d", "moolias-sender-agent"],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    )
    previous_container = subprocess.run(
        ["docker", "compose", "ps", "-q", "moolias-sender-agent"],
        cwd=mailcow_dir,
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()
    assert previous_container
    return previous_container


def _run_installer(mailcow_dir: str, image: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["MAILCOW_DIR"] = mailcow_dir
    env["MOOLIAS_AGENT_IMAGE"] = image
    env["MOOLIAS_AGENT_COOLDOWN_SECONDS"] = "1"
    env["MOOLIAS_IMPORT_EXISTING_SENDER_RULES"] = "no"
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


def test_v121_agent_layout_is_migrated_without_losing_sender_state() -> None:
    if os.environ.get("MOOLIAS_TEST_SCENARIO", "fresh") != "fresh":
        pytest.skip("v1.2.1 agent migration is covered once in the fresh Mailcow scenario")

    mailcow_dir = os.environ.get("MAILCOW_DIR")
    if not mailcow_dir:
        pytest.skip("real Mailcow integration environment is not configured")

    image = os.environ.get("MOOLIAS_AGENT_IMAGE", "moolias:agent-ci")
    previous_container = _prepare_v121_layout(mailcow_dir, image)

    result = _run_installer(mailcow_dir, image)
    assert result.returncode == 0, (
        "Moolias Mailcow Agent migration failed:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )

    match = re.search(r"^MOOLIAS_MAILCOW_AGENT_SECRET=(.+)$", result.stdout, re.MULTILINE)
    assert match is not None, result.stdout
    assert match.group(1).strip() == PREVIOUS_SECRET

    new_state_path = os.path.join(
        mailcow_dir,
        "data",
        "conf",
        "moolias-agent",
        "state",
        "state.json",
    )
    state = json.loads(_sudo_read(new_state_path))
    assert state["version"] == 2
    assert PREVIOUS_BLOCKED in state["blocked"]

    new_policy = _sudo_read(
        os.path.join(
            mailcow_dir,
            "data",
            "conf",
            "postfix",
            "moolias-agent",
            "blocked_sender_login.pcre",
        )
    )
    assert r"/^legacy\.upgrade@example\.org$/" in new_policy

    override = _sudo_read(os.path.join(mailcow_dir, "docker-compose.override.yml"))
    assert "unrelated-test-service:" in override
    assert "# BEGIN MOOLIAS MAILCOW AGENT" in override
    assert "moolias-agent:" in override
    assert "# BEGIN MOOLIAS SENDER AGENT" not in override
    assert "moolias-sender-agent:" not in override

    extra_cf = _sudo_read(
        os.path.join(mailcow_dir, "data", "conf", "postfix", "extra.cf")
    )
    assert CURRENT_PCRE_MAP in extra_cf
    assert PREVIOUS_PCRE_MAP not in extra_cf

    assert not os.path.exists(
        os.path.join(mailcow_dir, "data", "conf", "nginx", "site.moolias-sender-agent.custom")
    )
    assert os.path.exists(
        os.path.join(mailcow_dir, "data", "conf", "nginx", "site.moolias-agent.custom")
    )

    assert subprocess.run(
        ["docker", "inspect", previous_container],
        check=False,
        text=True,
        capture_output=True,
    ).returncode != 0

    previous_agent_dir = os.path.join(mailcow_dir, "data", "conf", "moolias-sender-agent")
    previous_policy_dir = os.path.join(
        mailcow_dir,
        "data",
        "conf",
        "postfix",
        "moolias-sender-agent",
    )
    assert not os.path.exists(previous_agent_dir)
    assert not os.path.exists(previous_policy_dir)
    assert glob.glob(f"{previous_agent_dir}.before-moolias-agent-*.bak")
    assert glob.glob(f"{previous_policy_dir}.before-moolias-agent-*.bak")
