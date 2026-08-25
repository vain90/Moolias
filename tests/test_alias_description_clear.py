import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from moolias.aliases import AliasRecord
from moolias.config import Settings

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

import moolias.alias_table_ui as alias_table_module  # noqa: E402
import moolias.main as main_module  # noqa: E402


def settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, alias: AliasRecord) -> None:
        self.alias = alias
        self.updated: dict[str, object] | None = None

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

    async def update_alias_preferences(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
        *,
        private_comment: str | None = None,
    ) -> None:
        self.updated = {
            "alias_id": alias_id,
            "public_comment": public_comment,
            "sogo_visible": sogo_visible,
            "private_comment": private_comment,
        }


def alias_record(private_comment: str) -> AliasRecord:
    return AliasRecord(
        id=42,
        address="amazon-k7@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment=private_comment,
        public_comment="Amazon",
        sogo_visible=True,
    )


@contextmanager
def make_client(monkeypatch, fake: FakeMailcow):
    async def fake_exchange_code(_settings, _code):
        return {"email": "hidden@example.org"}

    monkeypatch.setattr(main_module, "MailcowClient", lambda _: fake)
    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)
    monkeypatch.setattr(alias_table_module, "validate_csrf", lambda _request, _token: None)

    with TestClient(main_module.create_app(settings())) as client:
        login = client.get(
            "/oauth/callback?code=test&state=test",
            follow_redirects=False,
        )
        assert login.status_code == 303
        yield client


@pytest.mark.parametrize(
    ("original_private_comment", "expected_private_comment"),
    [
        ("Old description", ""),
        (
            "Old description\n[moolias:future-state]",
            "[moolias:future-state]",
        ),
    ],
)
def test_empty_submitted_description_clears_human_text_and_preserves_markers(
    monkeypatch,
    original_private_comment: str,
    expected_private_comment: str,
):
    fake = FakeMailcow(alias_record(original_private_comment))

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases/42/metadata",
            data={
                "description": "Amazon",
                "private_description": "",
                "sogo_visible": "1",
                "csrf_token": "test",
                "return_to": "/aliases",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/aliases"
    assert fake.updated == {
        "alias_id": 42,
        "public_comment": "Amazon",
        "sogo_visible": True,
        "private_comment": expected_private_comment,
    }


def test_missing_description_field_keeps_existing_private_comment(monkeypatch):
    original_private_comment = "Old description\n[moolias:future-state]"
    fake = FakeMailcow(alias_record(original_private_comment))

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases/42/metadata",
            data={
                "description": "Amazon",
                "sogo_visible": "1",
                "csrf_token": "test",
                "return_to": "/aliases",
            },
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert fake.updated == {
        "alias_id": 42,
        "public_comment": "Amazon",
        "sogo_visible": True,
        "private_comment": original_private_comment,
    }
