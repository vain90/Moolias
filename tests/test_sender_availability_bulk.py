from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import moolias.alias_bulk_ui as bulk_module
from moolias.aliases import AliasRecord


def alias_record(sender_allowed: bool | None) -> AliasRecord:
    return AliasRecord(
        id=42,
        address="shop@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="Shop",
        sogo_visible=False,
        sender_allowed=sender_allowed,
    )


class FakeMailcow:
    def __init__(self, alias: AliasRecord) -> None:
        self.alias = alias
        self.sogo_calls: list[tuple[list[int], bool]] = []

    async def list_aliases(self) -> list[AliasRecord]:
        return [self.alias]

    async def set_sogo_visible_many(self, alias_ids: list[int], visible: bool) -> None:
        self.sogo_calls.append((list(alias_ids), visible))


@pytest.fixture(autouse=True)
def auth(monkeypatch):
    monkeypatch.setattr(bulk_module, "validate_csrf", lambda _request, _token: None)
    monkeypatch.setattr(bulk_module, "require_user", lambda _request: "hidden@example.org")


async def test_bulk_sogo_on_rejects_explicitly_non_sendable_alias() -> None:
    mailcow = FakeMailcow(alias_record(False))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(mailcow=mailcow)))

    with pytest.raises(HTTPException) as exc_info:
        await bulk_module.bulk_aliases(
            request,
            action="sogo-on",
            alias_ids=[42],
            csrf_token="test",
        )

    assert exc_info.value.status_code == 409
    assert mailcow.sogo_calls == []


async def test_bulk_sogo_on_keeps_unknown_sender_permission_distinct_from_false() -> None:
    mailcow = FakeMailcow(alias_record(None))
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(mailcow=mailcow)))

    response = await bulk_module.bulk_aliases(
        request,
        action="sogo-on",
        alias_ids=[42],
        csrf_token="test",
    )

    assert response.body == b"ok\n"
    assert mailcow.sogo_calls == [([42], True)]
