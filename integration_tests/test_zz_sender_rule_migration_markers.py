from __future__ import annotations

import os
import subprocess

import pytest

LEGACY_MAILBOX = "legacy.blocked@example.org"
LEGACY_MAILBOX_2 = "legacy.second@example.org"
MOOLIAS_OWNER = "__moolias_blocked_primary_sender__"
LEGACY_OWNER = "__blocked_hidden_sender__"
LEGACY_OWNER_2 = "__blocked_hidden_sender_2__"
MOOLIAS_MAP = "pcre:/opt/postfix/conf/moolias-agent/blocked_sender_login.pcre"
LEGACY_MAP = "pcre:/opt/postfix/conf/blocked_sender_login.pcre"


def _query(mailcow_dir: str, map_name: str, mailbox: str) -> str:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postfix-mailcow",
            "postmap",
            "-q",
            mailbox,
            map_name,
        ],
        cwd=mailcow_dir,
        check=False,
        text=True,
        capture_output=True,
    )
    if result.returncode not in {0, 1}:
        raise AssertionError(
            f"Postfix map query failed for {mailbox}: "
            f"exit={result.returncode}, stderr={result.stderr!r}"
        )
    return result.stdout.strip()


def test_existing_rule_ownership_after_install() -> None:
    scenario = os.environ.get("MOOLIAS_TEST_SCENARIO", "fresh")
    mailcow_dir = os.environ.get("MAILCOW_DIR")
    if not mailcow_dir or scenario == "fresh":
        pytest.skip("No legacy sender rule migration to verify")

    moolias_first = _query(mailcow_dir, MOOLIAS_MAP, LEGACY_MAILBOX)
    moolias_second = _query(mailcow_dir, MOOLIAS_MAP, LEGACY_MAILBOX_2)
    legacy_first = _query(mailcow_dir, LEGACY_MAP, LEGACY_MAILBOX)
    legacy_second = _query(mailcow_dir, LEGACY_MAP, LEGACY_MAILBOX_2)

    if scenario == "legacy-import":
        assert moolias_first == MOOLIAS_OWNER
        assert moolias_second == MOOLIAS_OWNER
        assert legacy_first == ""
        assert legacy_second == ""
        return

    if scenario == "legacy-keep":
        assert moolias_first == ""
        assert moolias_second == ""
        assert legacy_first == LEGACY_OWNER
        assert legacy_second == LEGACY_OWNER_2
        return

    raise AssertionError(f"Unknown integration scenario: {scenario}")
