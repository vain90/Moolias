from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from moolias.aliases import AliasRecord
from moolias.alias_workflows import AliasWorkflowStore

import moolias.alias_table_ui as alias_table_module


class FakeMailcow:
    def __init__(self, alias: AliasRecord) -> None:
        self.alias = alias
        self.active_updates: list[tuple[int, bool]] = []

    async def get_alias(self, alias_id: int) -> AliasRecord:
        assert alias_id == self.alias.id
        return self.alias

    async def set_active(self, alias_id: int, active: bool) -> None:
        self.active_updates.append((alias_id, active))


def _alias(*, active: bool = True) -> AliasRecord:
    return AliasRecord(
        id=7,
        address="a@example.org",
        goto="user@example.org",
        domain="example.org",
        active=active,
        private_comment="",
        public_comment="Shop",
        sogo_visible=False,
    )


def _request(store: AliasWorkflowStore, mailcow: FakeMailcow):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                alias_workflow_store=store,
                mailcow=mailcow,
            )
        ),
        headers={},
    )


async def _replacement(
    store: AliasWorkflowStore,
    *,
    old_alias_id: int,
    old_address: str,
    new_address: str,
    started_at: int,
):
    return await store.create_replacement(
        mailbox="user@example.org",
        old_alias_id=old_alias_id,
        old_address=old_address,
        new_address=new_address,
        alias_name="Shop",
        alias_description="",
        started_at=started_at,
        bypass_expires_at=started_at + 900,
    )


async def test_replacement_can_be_disabled_immediately_before_new_mail(
    monkeypatch,
    tmp_path,
):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await _replacement(
        store,
        old_alias_id=7,
        old_address="a@example.org",
        new_address="b@example.org",
        started_at=1000,
    )
    assert workflow.new_mail_received_at is None

    mailcow = FakeMailcow(_alias())
    request = _request(store, mailcow)
    monkeypatch.setattr(alias_table_module, "require_user", lambda _request: "user@example.org")
    monkeypatch.setattr(alias_table_module, "validate_csrf", lambda _request, _token: None)

    await alias_table_module.update_replacement_deactivation(
        request,
        workflow.id,
        mode="now",
        csrf_token="test",
    )

    assert mailcow.active_updates == [(7, False)]
    assert await store.pending_replacements("user@example.org") == []
    completed = await store.get("user@example.org", workflow.id)
    assert completed is not None
    assert completed.completed_at is not None


async def test_manual_old_alias_deactivation_completes_replacement(
    monkeypatch,
    tmp_path,
):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    workflow = await _replacement(
        store,
        old_alias_id=7,
        old_address="a@example.org",
        new_address="b@example.org",
        started_at=1000,
    )

    mailcow = FakeMailcow(_alias())
    request = _request(store, mailcow)
    monkeypatch.setattr(alias_table_module, "require_user", lambda _request: "user@example.org")
    monkeypatch.setattr(alias_table_module, "validate_csrf", lambda _request, _token: None)

    await alias_table_module.toggle_alias(
        request,
        7,
        csrf_token="test",
        return_to="/aliases",
    )

    assert mailcow.active_updates == [(7, False)]
    assert await store.pending_replacements("user@example.org") == []
    completed = await store.get("user@example.org", workflow.id)
    assert completed is not None
    assert completed.completed_at is not None


async def test_completed_replacement_history_supports_chains(tmp_path):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()

    first = await _replacement(
        store,
        old_alias_id=7,
        old_address="a@example.org",
        new_address="b@example.org",
        started_at=1000,
    )
    await store.complete_replacement("user@example.org", first.id, now=1100)

    second = await _replacement(
        store,
        old_alias_id=8,
        old_address="b@example.org",
        new_address="c@example.org",
        started_at=1200,
    )
    await store.complete_replacement("user@example.org", second.id, now=1300)

    history = alias_table_module._replacement_history_sync(
        str(store.path),
        "USER@example.org",
    )

    assert history["a@example.org"] == [
        {"direction": "next", "address": "b@example.org"}
    ]
    assert history["b@example.org"] == [
        {"direction": "previous", "address": "a@example.org"},
        {"direction": "next", "address": "c@example.org"},
    ]
    assert history["c@example.org"] == [
        {"direction": "previous", "address": "b@example.org"}
    ]


def test_replacement_workflow_uses_shared_close_button_and_server_rendered_controls():
    root = Path(__file__).resolve().parents[1]
    template = (root / "moolias/templates/_alias_workflow.html").read_text()
    css = (root / "moolias/static/alias-workflow.css").read_text()

    assert ".alias-workflow-dialog .dialog-close" not in css
    assert 'class="alias-workflow-wait-spinner"' in template
    assert 'class="alias-workflow-deactivation-form"' in template
    assert 'name="mode" value="later"' in template
    assert 'name="mode" value="now"' in template
    assert 'name="mode" value="7d"' in template
    assert 'name="mode" value="30d"' in template
    assert 'name="confirm_now"' not in template
