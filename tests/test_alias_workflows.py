from __future__ import annotations

from moolias.alias_workflows import (
    DEACTIVATION_30_DAYS,
    DEACTIVATION_7_DAYS,
    DEACTIVATION_LATER,
    AliasWorkflowStore,
)


async def test_creation_waiting_stops_without_clearing_bypass(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await store.create_creation(
        mailbox="user@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="Account",
        started_at=1000,
        bypass_expires_at=1600,
    )

    assert workflow.waiting_state == "waiting"
    stopped = await store.stop_waiting("USER@example.org", workflow.id)
    assert stopped is not None
    assert stopped.waiting_state == "stopped"
    assert stopped.bypass_clear_requested_at is None
    due = await store.bypass_provisioning_due(now=1100)
    assert [item.id for item in due] == [workflow.id]


async def test_new_delivery_finishes_waiting_and_requests_early_bypass_clear(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await store.create_creation(
        mailbox="user@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1600,
    )
    await store.mark_bypass_provisioned(workflow.id, now=1001)

    changed = await store.record_deliveries([("NEW@example.org", 1010)])

    assert len(changed) == 1
    assert changed[0].waiting_state == "received"
    assert changed[0].new_mail_received_at == 1010
    assert changed[0].bypass_clear_requested_at == 1010
    assert [item.id for item in await store.bypass_clear_due()] == [workflow.id]


async def test_replacement_tracks_old_and_new_independently(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await store.create_replacement(
        mailbox="user@example.org",
        old_alias_id=7,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="Account",
        started_at=1000,
        bypass_expires_at=1600,
    )

    old_changed = await store.record_deliveries([("old@example.org", 1010)])
    assert old_changed[0].waiting_state == "old_received"
    assert old_changed[0].old_mail_received_at == 1010
    assert old_changed[0].new_mail_received_at is None
    assert old_changed[0].watcher_active is True
    assert old_changed[0].bypass_clear_requested_at is None

    new_changed = await store.record_deliveries([("new@example.org", 1020)])
    assert new_changed[0].waiting_state == "received"
    assert new_changed[0].old_mail_received_at == 1010
    assert new_changed[0].new_mail_received_at == 1020
    assert new_changed[0].watcher_active is False
    assert new_changed[0].bypass_clear_requested_at == 1020
    assert new_changed[0].bypass_recipients == ("old@example.org", "new@example.org")


async def test_replacement_deactivation_modes_are_persistent_and_changeable(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = AliasWorkflowStore(path)
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

    seven = await store.set_deactivation(
        "user@example.org", workflow.id, DEACTIVATION_7_DAYS, now=2000
    )
    assert seven.scheduled_deactivation_at == 2000 + 7 * 86400

    restarted = AliasWorkflowStore(path)
    await restarted.initialize()
    loaded = await restarted.get("user@example.org", workflow.id)
    assert loaded is not None
    assert loaded.deactivation_mode == DEACTIVATION_7_DAYS
    assert loaded.scheduled_deactivation_at == seven.scheduled_deactivation_at

    thirty = await restarted.set_deactivation(
        "user@example.org", workflow.id, DEACTIVATION_30_DAYS, now=3000
    )
    assert thirty.scheduled_deactivation_at == 3000 + 30 * 86400

    later = await restarted.set_deactivation(
        "user@example.org", workflow.id, DEACTIVATION_LATER, now=4000
    )
    assert later.scheduled_deactivation_at is None
    assert await restarted.due_deactivations(now=10_000_000) == []


async def test_due_deactivation_and_completion_survive_restart(tmp_path):
    path = tmp_path / "state.sqlite3"
    store = AliasWorkflowStore(path)
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

    restarted = AliasWorkflowStore(path)
    await restarted.initialize()
    assert await restarted.due_deactivations(now=scheduled.scheduled_deactivation_at - 1) == []
    due = await restarted.due_deactivations(now=scheduled.scheduled_deactivation_at)
    assert [item.id for item in due] == [workflow.id]

    completed = await restarted.complete_replacement(
        "user@example.org", workflow.id, now=scheduled.scheduled_deactivation_at
    )
    assert completed is not None
    assert completed.completed_at == scheduled.scheduled_deactivation_at
    assert await restarted.pending_replacements("user@example.org") == []
