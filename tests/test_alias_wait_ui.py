from __future__ import annotations

import os
from contextlib import contextmanager

from fastapi.testclient import TestClient

from moolias.aliases import RESERVED_COMMENT, AliasRecord
from moolias.config import Settings

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

import moolias.alias_wait_ui as wait_module  # noqa: E402
import moolias.main as main_module  # noqa: E402


class FakeMailcow:
    def __init__(self, alias: AliasRecord) -> None:
        self.alias = alias

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


@contextmanager
def make_client(monkeypatch, tmp_path, fake: FakeMailcow, provisioned: list):
    async def fake_exchange_code(_settings, _code):
        return {"email": "user@example.org"}

    async def fake_provision(_request, workflow):
        provisioned.append(workflow)

    settings = Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MOOLIAS_ALIAS_WORKFLOW_BYPASS_SECONDS=900,
        MOOLIAS_USAGE_DB_PATH=str(tmp_path / "state.sqlite3"),
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )

    monkeypatch.setattr(main_module, "MailcowClient", lambda _: fake)
    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)
    monkeypatch.setattr(wait_module, "validate_csrf", lambda _request, _token: None)
    monkeypatch.setattr(wait_module, "_provision_now", fake_provision)

    with TestClient(main_module.create_app(settings)) as client:
        login = client.get(
            "/oauth/callback?code=test&state=test",
            follow_redirects=False,
        )
        assert login.status_code == 303
        yield client


def owned_alias(*, active: bool = True, reserved: bool = False) -> AliasRecord:
    return AliasRecord(
        id=42,
        address="hotel@example.org",
        goto="user@example.org",
        domain="example.org",
        active=active,
        private_comment=RESERVED_COMMENT if reserved else "Booking alias",
        public_comment="" if reserved else "Hotel",
        sogo_visible=False,
        sender_allowed=True,
    )


def test_wait_route_uses_same_configured_duration_and_reuses_session(
    monkeypatch,
    tmp_path,
):
    alias = owned_alias()
    provisioned = []
    now = [1000]
    monkeypatch.setattr(wait_module.time, "time", lambda: now[0])

    with make_client(monkeypatch, tmp_path, FakeMailcow(alias), provisioned) as client:
        first = client.post(
            "/aliases/42/wait-for-mail",
            data={"csrf_token": "test", "return_to": "/aliases"},
            follow_redirects=False,
        )
        assert first.status_code == 303
        assert first.headers["location"] == "/aliases"
        assert len(provisioned) == 1
        first_workflow = provisioned[-1]
        assert first_workflow.started_at == 1000
        assert first_workflow.bypass_expires_at == 1900
        assert first_workflow.old_alias_id == 42

        now[0] = 1200
        second = client.post(
            "/aliases/42/wait-for-mail",
            data={"csrf_token": "test", "return_to": "/aliases"},
            follow_redirects=False,
        )
        assert second.status_code == 303
        assert len(provisioned) == 2
        second_workflow = provisioned[-1]
        assert second_workflow.id == first_workflow.id
        assert second_workflow.started_at == 1200
        assert second_workflow.bypass_expires_at == 2100

        status = client.get("/aliases/wait-status")
        assert status.status_code == 200
        assert status.json() == {
            "active": [
                {
                    "address": "hotel@example.org",
                    "workflow_id": first_workflow.id,
                    "expires_at": 2100,
                }
            ],
            "poll_seconds": 2,
        }

    assert alias == owned_alias()


def test_wait_route_accepts_reserved_offline_alias_without_assigning_it(
    monkeypatch,
    tmp_path,
):
    alias = owned_alias(reserved=True)
    provisioned = []
    monkeypatch.setattr(wait_module.time, "time", lambda: 1000)

    with make_client(monkeypatch, tmp_path, FakeMailcow(alias), provisioned) as client:
        response = client.post(
            "/aliases/42/wait-for-mail",
            data={"csrf_token": "test", "return_to": "/offline-pool"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/offline-pool"
    assert len(provisioned) == 1
    assert alias.private_comment == RESERVED_COMMENT
    assert alias.public_comment == ""


def test_wait_route_rejects_disabled_alias(monkeypatch, tmp_path):
    provisioned = []
    monkeypatch.setattr(wait_module.time, "time", lambda: 1000)

    with make_client(
        monkeypatch,
        tmp_path,
        FakeMailcow(owned_alias(active=False)),
        provisioned,
    ) as client:
        response = client.post(
            "/aliases/42/wait-for-mail",
            data={"csrf_token": "test", "return_to": "/aliases"},
            follow_redirects=False,
        )

    assert response.status_code == 409
    assert provisioned == []


def test_wait_buttons_are_server_rendered_without_javascript():
    dashboard = (main_module.PACKAGE_DIR / "templates" / "dashboard.html").read_text()
    pool = (main_module.PACKAGE_DIR / "templates" / "offline_pool.html").read_text()

    assert 'action="/aliases/{{ alias.id }}/wait-for-mail"' in dashboard
    assert 'action="/aliases/{{ alias.id }}/wait-for-mail"' in pool
    assert 'name="csrf_token"' in dashboard
    assert 'name="csrf_token"' in pool
