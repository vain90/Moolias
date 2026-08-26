from __future__ import annotations

from collections.abc import Iterator, Mapping
from typing import Any

from moolias.alias_workflow_coordinator import (
    AliasWorkflowCoordinator,
    accepted_delivery_metadata,
)
from moolias.alias_workflows import DEACTIVATION_7_DAYS, AliasWorkflowStore
from moolias.config import Settings


class PrivacyHistoryRow(Mapping[str, Any]):
    def __init__(self, values: dict[str, Any]) -> None:
        self.values = values

    def __getitem__(self, key: str) -> Any:
        if key not in {"action", "unix_time", "rcpt_smtp"}:
            raise AssertionError(f"workflow inspected forbidden mail field: {key}")
        return self.values[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self.values)

    def __len__(self) -> int:
        return len(self.values)

    def get(self, key: str, default: Any = None) -> Any:
        if key not in {"action", "unix_time", "rcpt_smtp"}:
            raise AssertionError(f"workflow inspected forbidden mail field: {key}")
        return self.values.get(key, default)


class FakeAgent:
    def __init__(self) -> None:
        self.set_calls: list[tuple[tuple[str, ...], int]] = []
        self.clear_calls: list[tuple[str, ...]] = []

    async def close(self) -> None:
        pass

    async def set_bypass(self, recipients: tuple[str, ...], expires_at: int) -> None:
        self.set_calls.append((recipients, expires_at))

    async def clear_bypass(self, recipients: tuple[str, ...]) -> None:
        self.clear_calls.append(recipients)


class FakeMailcow:
    def __init__(self) -> None:
        self.history: list[dict[str, Any]] = []
        self.disabled: list[int] = []

    async def get_rspamd_history(self, count: int) -> list[dict[str, Any]]:
        return self.history[:count]

    async def set_active(self, alias_id: int, active: bool) -> None:
        assert active is False
        self.disabled.append(alias_id)


def settings(tmp_path) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MOOLIAS_USAGE_DB_PATH=str(tmp_path / "state.sqlite3"),
        MOOLIAS_ALIAS_WORKFLOW_POLL_SECONDS=1,
        MOOLIAS_ALIAS_WORKFLOW_HISTORY_COUNT=100,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def test_delivery_parser_never_reads_mail_content_fields():
    row = PrivacyHistoryRow(
        {
            "action": "clean",
            "unix_time": 1010,
            "rcpt_smtp": ["new@example.org"],
            "subject": "must not be read",
            "body": "must not be read",
            "attachments": ["must-not-be-read.pdf"],
        }
    )

    assert accepted_delivery_metadata(
        [row],
        recipients={"new@example.org"},
        earliest_at=1000,
    ) == [("new@example.org", 1010)]


def test_delivery_parser_ignores_rejected_or_greylisted_mail():
    history = [
        {"action": "greylist", "unix_time": 1010, "rcpt_smtp": ["new@example.org"]},
        {"action": "soft reject", "unix_time": 1011, "rcpt_smtp": ["new@example.org"]},
        {"action": "reject", "unix_time": 1012, "rcpt_smtp": ["new@example.org"]},
    ]
    assert accepted_delivery_metadata(
        history,
        recipients={"new@example.org"},
        earliest_at=1000,
    ) == []


async def test_replacement_old_mail_keeps_waiting_new_mail_clears_both_bypasses(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await store.create_replacement(
        mailbox="user@example.org",
        old_alias_id=7,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1600,
    )
    mailcow = FakeMailcow()
    agent = FakeAgent()
    coordinator = AliasWorkflowCoordinator(
        settings(tmp_path),
        mailcow,  # type: ignore[arg-type]
        store,
        agent,  # type: ignore[arg-type]
        clock=lambda: 1005,
    )

    await coordinator.reconcile_once()
    assert agent.set_calls == [(('old@example.org', 'new@example.org'), 1600)]

    mailcow.history = [
        {"action": "clean", "unix_time": 1010, "rcpt_smtp": ["old@example.org"]}
    ]
    await coordinator.reconcile_once()
    current = await store.get("user@example.org", workflow.id)
    assert current is not None
    assert current.waiting_state == "old_received"
    assert current.watcher_active is True
    assert agent.clear_calls == []

    mailcow.history.insert(
        0,
        {"action": "clean", "unix_time": 1020, "rcpt_smtp": ["new@example.org"]},
    )
    await coordinator.reconcile_once()
    current = await store.get("user@example.org", workflow.id)
    assert current is not None
    assert current.waiting_state == "received"
    assert agent.clear_calls[-1] == ("old@example.org", "new@example.org")


async def test_scheduled_deactivation_runs_without_browser(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await store.create_replacement(
        mailbox="user@example.org",
        old_alias_id=7,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1600,
    )
    scheduled = await store.set_deactivation(
        "user@example.org", workflow.id, DEACTIVATION_7_DAYS, now=2000
    )
    assert scheduled.scheduled_deactivation_at is not None

    mailcow = FakeMailcow()
    coordinator = AliasWorkflowCoordinator(
        settings(tmp_path),
        mailcow,  # type: ignore[arg-type]
        store,
        FakeAgent(),  # type: ignore[arg-type]
        clock=lambda: scheduled.scheduled_deactivation_at,
    )
    await coordinator.reconcile_once()

    assert mailcow.disabled == [7]
    completed = await store.get("user@example.org", workflow.id)
    assert completed is not None
    assert completed.completed_at == scheduled.scheduled_deactivation_at
