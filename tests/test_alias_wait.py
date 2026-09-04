from __future__ import annotations

import pytest

from moolias.alias_wait import AliasWaitService, is_manual_alias_wait
from moolias.alias_workflows import AliasWorkflowStore


async def test_wait_reuses_completed_creation_workflow(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    original = await store.create_creation(
        mailbox="user@example.org",
        new_address="hotel@example.org",
        alias_name="Hotel",
        alias_description="Booking",
        started_at=1000,
        bypass_expires_at=1900,
    )
    await store.mark_bypass_provisioned(original.id, now=1001)
    changed = await store.record_deliveries([("hotel@example.org", 1010)])
    assert changed[0].waiting_state == "received"

    restarted = await AliasWaitService(store).start(
        mailbox="USER@example.org",
        alias_id=42,
        address="HOTEL@example.org",
        alias_name="Hotel",
        alias_description="Booking",
        started_at=2000,
        bypass_expires_at=2900,
    )

    assert restarted.id == original.id
    assert restarted.old_alias_id == 42
    assert is_manual_alias_wait(restarted) is True
    assert restarted.started_at == 2000
    assert restarted.bypass_expires_at == 2900
    assert restarted.watcher_active is True
    assert restarted.new_mail_received_at is None
    assert restarted.bypass_provisioned_at is None
    assert restarted.bypass_clear_requested_at is None
    assert restarted.bypass_cleared_at is None


async def test_retrigger_restarts_one_wait_session(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    waits = AliasWaitService(store)

    first = await waits.start(
        mailbox="user@example.org",
        alias_id=42,
        address="hotel@example.org",
        alias_name="Hotel",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )
    await store.mark_bypass_provisioned(first.id, now=1001)

    second = await waits.start(
        mailbox="user@example.org",
        alias_id=42,
        address="hotel@example.org",
        alias_name="Hotel",
        alias_description="",
        started_at=1200,
        bypass_expires_at=2100,
    )

    assert second.id == first.id
    assert second.started_at == 1200
    assert second.bypass_expires_at == 2100
    assert second.bypass_provisioned_at is None
    active = await waits.active_for_mailbox("user@example.org", now=1201)
    assert [(item.address, item.workflow_id, item.expires_at) for item in active] == [
        ("hotel@example.org", first.id, 2100)
    ]


@pytest.mark.parametrize("address", ["old@example.org", "new@example.org"])
async def test_wait_rejects_alias_in_active_replacement(tmp_path, address):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    await store.create_replacement(
        mailbox="user@example.org",
        old_alias_id=7,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )

    with pytest.raises(ValueError, match="active replacement"):
        await AliasWaitService(store).start(
            mailbox="user@example.org",
            alias_id=42,
            address=address,
            alias_name="Shop",
            alias_description="",
            started_at=1100,
            bypass_expires_at=2000,
        )


async def test_manual_wait_expiry_stops_watcher_and_requests_bypass_clear(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    waits = AliasWaitService(store)
    workflow = await waits.start(
        mailbox="user@example.org",
        alias_id=42,
        address="hotel@example.org",
        alias_name="Hotel",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )
    await store.mark_bypass_provisioned(workflow.id, now=1001)

    assert await waits.expire_due(now=1899) == 0
    assert await waits.expire_due(now=1900) == 1

    expired = await store.get("user@example.org", workflow.id)
    assert expired is not None
    assert expired.watcher_active is False
    assert expired.new_mail_received_at is None
    assert expired.bypass_clear_requested_at == 1900
    assert [item.id for item in await store.bypass_clear_due()] == [workflow.id]
    assert await waits.active_for_mailbox("user@example.org", now=1900) == []


async def test_manual_expiry_does_not_change_original_creation_semantics(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    original = await store.create_creation(
        mailbox="user@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )

    assert is_manual_alias_wait(original) is False
    assert await AliasWaitService(store).expire_due(now=2000) == 0

    unchanged = await store.get("user@example.org", original.id)
    assert unchanged is not None
    assert unchanged.watcher_active is True
    assert unchanged.bypass_clear_requested_at is None
