import os

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from fastapi.testclient import TestClient

import moolias.main as main_module
from moolias.aliases import RESERVED_COMMENT, USED_RESERVED_COMMENT, AliasRecord
from moolias.config import Settings
from moolias.stats import AliasUsage


def settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MOOLIAS_USAGE_STATS=False,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self) -> None:
        self.deleted: list[int] = []
        self.alias = AliasRecord(
            id=42,
            address="feder-hafen-27@example.org",
            goto="hidden@example.org",
            domain="example.org",
            active=True,
            private_comment=RESERVED_COMMENT,
            public_comment="",
            sogo_visible=False,
        )

    async def close(self) -> None:
        pass

    async def get_mailbox(self, email: str):
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": [],
        }

    async def get_alias(self, alias_id: int) -> AliasRecord:
        assert alias_id == self.alias.id
        return self.alias

    async def list_aliases(self) -> list[AliasRecord]:
        return [self.alias]

    async def delete_alias(self, alias_id: int) -> None:
        self.deleted.append(alias_id)


class FakeStatsStore:
    def __init__(self, usage: AliasUsage | None) -> None:
        self.usage = usage

    async def alias_usage(self, mailbox: str, aliases: list[str]):
        assert mailbox == "hidden@example.org"
        assert aliases == ["feder-hafen-27@example.org"]
        if self.usage is None:
            return {}
        return {"feder-hafen-27@example.org": self.usage}


def make_client(monkeypatch, usage: AliasUsage | None):
    mailcow = FakeMailcow()

    async def fake_exchange_code(_settings, _code):
        return {"email": "hidden@example.org"}

    monkeypatch.setattr(main_module, "MailcowClient", lambda _: mailcow)
    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)
    monkeypatch.setattr(main_module, "validate_csrf", lambda _request, _token: None)

    app = main_module.create_app(settings())
    client = TestClient(app)
    client.__enter__()
    app.state.stats_store = FakeStatsStore(usage)

    login = client.get(
        "/oauth/callback?code=test&state=test",
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/overview"
    return client, mailcow


def test_received_offline_alias_cannot_be_deleted(monkeypatch):
    client, mailcow = make_client(
        monkeypatch,
        AliasUsage(received_count=1, sent_count=0),
    )
    try:
        response = client.post(
            "/aliases/42/delete-reserved",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert mailcow.deleted == []


def test_sent_offline_alias_cannot_be_deleted(monkeypatch):
    client, mailcow = make_client(
        monkeypatch,
        AliasUsage(received_count=0, sent_count=1),
    )
    try:
        response = client.post(
            "/aliases/42/delete-reserved",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert mailcow.deleted == []


def test_used_marker_blocks_deletion_without_usage_counters(monkeypatch):
    client, mailcow = make_client(monkeypatch, None)
    mailcow.alias = AliasRecord(
        id=42,
        address="feder-hafen-27@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment=USED_RESERVED_COMMENT,
        public_comment="",
        sogo_visible=False,
    )
    try:
        response = client.post(
            "/aliases/42/delete-reserved",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 409
    assert mailcow.deleted == []


def test_unused_offline_alias_can_still_be_deleted(monkeypatch):
    client, mailcow = make_client(
        monkeypatch,
        AliasUsage(received_count=0, sent_count=0),
    )
    try:
        response = client.post(
            "/aliases/42/delete-reserved",
            data={"csrf_token": "test"},
            follow_redirects=False,
        )
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 303
    assert response.headers["location"] == "/aliases#pool"
    assert mailcow.deleted == [42]


def test_pool_export_excludes_alias_with_used_marker(monkeypatch):
    client, mailcow = make_client(monkeypatch, None)
    mailcow.alias = AliasRecord(
        id=42,
        address="feder-hafen-27@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment=USED_RESERVED_COMMENT,
        public_comment="",
        sogo_visible=False,
    )
    try:
        response = client.get("/aliases/pool.txt")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.text == ""


def test_pool_export_excludes_alias_with_recorded_usage(monkeypatch):
    client, _ = make_client(
        monkeypatch,
        AliasUsage(received_count=0, sent_count=1),
    )
    try:
        response = client.get("/aliases/pool.txt")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.text == ""


def test_pool_export_keeps_unused_alias(monkeypatch):
    client, _ = make_client(
        monkeypatch,
        AliasUsage(received_count=0, sent_count=0),
    )
    try:
        response = client.get("/aliases/pool.txt")
    finally:
        client.__exit__(None, None, None)

    assert response.status_code == 200
    assert response.text == "feder-hafen-27@example.org\n"
