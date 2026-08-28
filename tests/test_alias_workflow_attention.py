from moolias.alias_table_ui import _replacement_needs_attention
from moolias.alias_workflows import DEACTIVATION_LATER, AliasWorkflow, WORKFLOW_REPLACEMENT


def _replacement(
    *,
    started_at: int,
    new_mail_received_at: int | None = None,
    deactivation_mode: str = DEACTIVATION_LATER,
    scheduled_deactivation_at: int | None = None,
) -> AliasWorkflow:
    return AliasWorkflow(
        id=1,
        kind=WORKFLOW_REPLACEMENT,
        mailbox="user@example.org",
        old_alias_id=7,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=started_at,
        watcher_active=new_mail_received_at is None,
        old_mail_received_at=None,
        new_mail_received_at=new_mail_received_at,
        deactivation_mode=deactivation_mode,
        scheduled_deactivation_at=scheduled_deactivation_at,
        bypass_expires_at=started_at + 30 * 86400,
        bypass_provisioned_at=started_at,
        bypass_clear_requested_at=new_mail_received_at,
        bypass_cleared_at=None,
        cancelled_at=None,
        completed_at=None,
    )


def test_first_mail_requires_immediate_attention_for_manual_deactivation():
    now = 2_000_000
    workflow = _replacement(
        started_at=now - 60,
        new_mail_received_at=now - 1,
    )

    assert _replacement_needs_attention(workflow, now=now, reminder_days=7)


def test_fresh_replacement_without_mail_waits_for_reminder():
    now = 2_000_000
    workflow = _replacement(started_at=now - 60)

    assert not _replacement_needs_attention(workflow, now=now, reminder_days=7)


def test_old_manual_replacement_still_uses_reminder_threshold():
    now = 2_000_000
    workflow = _replacement(started_at=now - 7 * 86400)

    assert _replacement_needs_attention(workflow, now=now, reminder_days=7)


def test_received_mail_does_not_override_future_scheduled_deactivation():
    now = 2_000_000
    workflow = _replacement(
        started_at=now - 60,
        new_mail_received_at=now - 1,
        deactivation_mode="7d",
        scheduled_deactivation_at=now + 7 * 86400,
    )

    assert not _replacement_needs_attention(workflow, now=now, reminder_days=7)
