import os
from contextlib import contextmanager

from fastapi.testclient import TestClient

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
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None

    async def close(self) -> None:
        pass

    async def get_mailbox(self, email: str):
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": [],
        }

    async def create_alias(
        self,
        address: str,
        target: str,
        public_comment: str = "",
        *,
        private_comment: str = "",
        sogo_visible: bool = False,
    ) -> None:
        self.created = {
            "address": address,
            "target": target,
            "public_comment": public_comment,
            "private_comment": private_comment,
            "sogo_visible": sogo_visible,
        }


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


def creation_form() -> dict[str, str]:
    return {
        "mode": "custom",
        "description": "Issue 110",
        "private_description": "Verification alias",
        "local_part": "issue-110",
        "sogo_visible": "1",
        "csrf_token": "test",
    }


def test_json_creation_result_exposes_stable_workflow_payload(monkeypatch):
    fake = FakeMailcow()

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases",
            data=creation_form(),
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )

    assert response.status_code == 200
    payload = response.json()
    workflow = payload.pop("workflow")
    assert payload == {
        "kind": "alias_creation",
        "state": "created",
        "address": "issue-110@example.org",
        "name": "Issue 110",
        "description": "Verification alias",
        "sogo_visible": True,
    }
    assert workflow["id"] > 0
    assert workflow["kind"] == "creation"
    assert workflow["state"] == "waiting"
    assert workflow["old_address"] is None
    assert workflow["new_address"] == "issue-110@example.org"
    assert workflow["name"] == "Issue 110"
    assert workflow["description"] == "Verification alias"
    assert workflow["started_at"] > 0
    assert workflow["old_mail_received_at"] is None
    assert workflow["new_mail_received_at"] is None
    assert workflow["scheduled_deactivation_at"] is None
    assert workflow["completed"] is False
    assert fake.created == {
        "address": "issue-110@example.org",
        "target": "hidden@example.org",
        "public_comment": "Issue 110",
        "private_comment": "Verification alias",
        "sogo_visible": True,
    }


def test_html_creation_redirects_to_server_rendered_workflow(monkeypatch):
    fake = FakeMailcow()

    with make_client(monkeypatch, fake) as client:
        response = client.post(
            "/aliases",
            data=creation_form(),
            follow_redirects=False,
        )

    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith("/aliases?workflow=")
    assert int(location.rsplit("=", 1)[1]) > 0
    assert fake.created is not None
