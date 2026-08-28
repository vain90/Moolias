from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import moolias.alias_bulk_ui as bulk_module
import moolias.main as main_module
from moolias.alias_workflows import AliasWorkflowStore
from moolias.aliases import AliasRecord
from moolias.config import Settings


def alias_record(alias_id: int, address: str) -> AliasRecord:
    return AliasRecord(
        id=alias_id,
        address=address,
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment=address.split("@", 1)[0],
        sogo_visible=False,
    )


class FakeMailcow:
    def __init__(self, aliases: list[AliasRecord]) -> None:
        self.aliases = aliases
        self.active_many_calls: list[tuple[list[int], bool]] = []
        self.sogo_many_calls: list[tuple[list[int], bool]] = []

    async def list_aliases(self) -> list[AliasRecord]:
        return self.aliases

    async def set_active_many(self, alias_ids: list[int], active: bool) -> None:
        self.active_many_calls.append((list(alias_ids), active))

    async def set_sogo_visible_many(self, alias_ids: list[int], visible: bool) -> None:
        self.sogo_many_calls.append((list(alias_ids), visible))


async def workflow_request(tmp_path, aliases: list[AliasRecord]):
    store = AliasWorkflowStore(tmp_path / "state.sqlite3")
    await store.initialize()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                mailcow=FakeMailcow(aliases),
                settings=SimpleNamespace(usage_db_path=str(tmp_path / "state.sqlite3")),
                alias_workflow_store=store,
            )
        )
    )
    return request, store


@pytest.fixture(autouse=True)
def auth(monkeypatch):
    monkeypatch.setattr(bulk_module, "validate_csrf", lambda _request, _token: None)
    monkeypatch.setattr(bulk_module, "require_user", lambda _request: "hidden@example.org")


async def test_bulk_disable_rejects_new_alias_before_any_mailcow_change(tmp_path):
    aliases = [
        alias_record(1, "old@example.org"),
        alias_record(2, "new@example.org"),
        alias_record(3, "other@example.org"),
    ]
    request, store = await workflow_request(tmp_path, aliases)
    workflow = await store.create_replacement(
        mailbox="hidden@example.org",
        old_alias_id=1,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )

    with pytest.raises(HTTPException) as exc_info:
        await bulk_module.bulk_aliases(
            request,
            action="disable",
            alias_ids=[2, 3],
            csrf_token="test",
        )

    assert exc_info.value.status_code == 409
    assert request.app.state.mailcow.active_many_calls == []
    current = await store.get("hidden@example.org", workflow.id)
    assert current is not None
    assert current.completed_at is None
    assert current.cancelled_at is None


async def test_bulk_disable_old_alias_completes_replacement_after_mailcow_change(tmp_path):
    aliases = [
        alias_record(1, "old@example.org"),
        alias_record(2, "new@example.org"),
        alias_record(3, "other@example.org"),
    ]
    request, store = await workflow_request(tmp_path, aliases)
    workflow = await store.create_replacement(
        mailbox="hidden@example.org",
        old_alias_id=1,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )

    response = await bulk_module.bulk_aliases(
        request,
        action="disable",
        alias_ids=[1, 3],
        csrf_token="test",
    )

    assert response.body == b"ok\n"
    assert request.app.state.mailcow.active_many_calls == [([1, 3], False)]
    current = await store.get("hidden@example.org", workflow.id)
    assert current is not None
    assert current.completed_at is not None
    assert current.cancelled_at is None
    assert await store.pending_replacements("hidden@example.org") == []


async def test_bulk_enable_does_not_end_pending_replacement(tmp_path):
    aliases = [alias_record(2, "new@example.org")]
    request, store = await workflow_request(tmp_path, aliases)
    workflow = await store.create_replacement(
        mailbox="hidden@example.org",
        old_alias_id=1,
        old_address="old@example.org",
        new_address="new@example.org",
        alias_name="Shop",
        alias_description="",
        started_at=1000,
        bypass_expires_at=1900,
    )

    response = await bulk_module.bulk_aliases(
        request,
        action="enable",
        alias_ids=[2],
        csrf_token="test",
    )

    assert response.body == b"ok\n"
    assert request.app.state.mailcow.active_many_calls == [([2], True)]
    current = await store.get("hidden@example.org", workflow.id)
    assert current is not None
    assert current.completed_at is None


def test_workflow_aware_bulk_route_is_the_registered_bulk_route():
    settings = Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MOOLIAS_USAGE_DB_PATH="/tmp/moolias-test-state.sqlite3",
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )
    app = main_module.create_app(settings)
    bulk_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/aliases/bulk"
        and "POST" in getattr(route, "methods", set())
    ]

    assert len(bulk_routes) == 1
    assert bulk_routes[0].endpoint is bulk_module.bulk_aliases
