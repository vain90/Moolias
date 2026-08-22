from __future__ import annotations

import os
import re

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from fastapi.testclient import TestClient

import moolias.main as main_module
import moolias.sender_protection as sender_module
from moolias.config import Settings
from moolias.main import create_app
from moolias.sender_protection import SenderAgentAuthenticationError
from moolias.sender_protocol import AgentProtectionState


class FakeMailcowClient:
    async def get_mailbox(self, email: str):
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": [],
        }

    async def get_domain(self, domain: str):
        return {
            "domain_name": domain,
            "aliases_in_domain": 1,
            "max_num_aliases_for_domain": 400,
        }

    async def list_aliases(self):
        return []

    async def close(self) -> None:
        pass


class FakeSenderAgentClient:
    calls: list[tuple[str, bool]] = []

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        pass

    async def probe(self) -> None:
        pass

    async def status(self, mailbox: str) -> AgentProtectionState:
        return AgentProtectionState(mailbox=mailbox, blocked=False, retry_after=0)

    async def set_blocked(
        self,
        mailbox: str,
        blocked: bool,
    ) -> tuple[AgentProtectionState, bool]:
        self.calls.append((mailbox, blocked))
        return (
            AgentProtectionState(
                mailbox=mailbox,
                blocked=blocked,
                retry_after=10,
            ),
            True,
        )


class FakeUnauthenticatedSenderAgentClient(FakeSenderAgentClient):
    async def status(self, mailbox: str) -> AgentProtectionState:
        raise SenderAgentAuthenticationError("authentication failed")


def settings(*, enabled: bool = True, secret: str | None = None) -> Settings:
    if secret is None:
        secret = "a" * 64 if enabled else ""
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MOOLIAS_SENDER_PROTECTION=enabled,
        MOOLIAS_SENDER_AGENT_SECRET=secret,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def login(client: TestClient, monkeypatch, email: str) -> str:
    async def fake_exchange_code(_settings, _code):
        return {"email": email}

    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)

    response = client.get(
        "/oauth/callback?code=test&state=test",
        follow_redirects=False,
    )
    assert response.status_code == 303

    dashboard = client.get("/aliases")
    assert dashboard.status_code == 200
    match = re.search(r'name="csrf_token" value="([^"]+)"', dashboard.text)
    assert match is not None
    return match.group(1)


def test_sender_protection_is_completely_optional(monkeypatch):
    app = create_app(settings(enabled=False))
    with TestClient(app) as client:
        app.state.mailcow = FakeMailcowClient()
        login(client, monkeypatch, "optional@example.org")

        response = client.get("/aliases/sender-protection")

    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_enabled_sender_protection_with_missing_secret_does_not_break_app(monkeypatch):
    monkeypatch.setattr(
        sender_module,
        "SenderAgentClient",
        FakeUnauthenticatedSenderAgentClient,
    )

    app = create_app(settings(enabled=True, secret=""))
    with TestClient(app) as client:
        app.state.mailcow = FakeMailcowClient()
        login(client, monkeypatch, "missing-secret@example.org")

        response = client.get("/aliases/sender-protection")

    assert response.status_code == 200
    assert response.json() == {
        "enabled": True,
        "available": False,
        "reason": "authentication",
    }


def test_browser_cannot_choose_another_mailbox(monkeypatch):
    FakeSenderAgentClient.calls = []
    monkeypatch.setattr(sender_module, "SenderAgentClient", FakeSenderAgentClient)

    app = create_app(settings())
    with TestClient(app) as client:
        app.state.mailcow = FakeMailcowClient()
        csrf = login(client, monkeypatch, "owner@example.org")

        malicious = client.post(
            "/aliases/sender-protection",
            json={
                "blocked": True,
                "mailbox": "victim@example.org",
            },
            headers={"X-CSRF-Token": csrf},
        )
        assert malicious.status_code == 400
        assert FakeSenderAgentClient.calls == []

        valid = client.post(
            "/aliases/sender-protection",
            json={"blocked": True},
            headers={"X-CSRF-Token": csrf},
        )

    assert valid.status_code == 200
    assert valid.json()["blocked"] is True
    assert FakeSenderAgentClient.calls == [("owner@example.org", True)]


def test_sender_protection_requires_csrf(monkeypatch):
    FakeSenderAgentClient.calls = []
    monkeypatch.setattr(sender_module, "SenderAgentClient", FakeSenderAgentClient)

    app = create_app(settings())
    with TestClient(app) as client:
        app.state.mailcow = FakeMailcowClient()
        login(client, monkeypatch, "csrf@example.org")

        response = client.post(
            "/aliases/sender-protection",
            json={"blocked": True},
        )

    assert response.status_code == 403
    assert FakeSenderAgentClient.calls == []
