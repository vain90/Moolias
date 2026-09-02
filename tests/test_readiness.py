from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

import moolias.readiness as readiness
from moolias.config import Settings
from moolias.main import create_app


def _settings() -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://moolias.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_MAILCOW_AGENT_SECRET="agent-secret-" + "x" * 32,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.calls = 0

    async def list_domains(self):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return []


class FakeAgentClient:
    error: Exception | None = None
    status_mailbox = readiness.READINESS_PROBE_MAILBOX
    probes = 0
    status_calls = 0

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def probe(self) -> None:
        type(self).probes += 1
        if type(self).error is not None:
            raise type(self).error

    async def status(self, _mailbox: str):
        type(self).status_calls += 1
        if type(self).error is not None:
            raise type(self).error
        return SimpleNamespace(mailbox=type(self).status_mailbox)


def _readiness_app(settings: Settings, mailcow: FakeMailcow) -> FastAPI:
    app = FastAPI()
    app.state.settings = settings
    app.state.mailcow = mailcow
    app.include_router(readiness.router)
    return app


def _reset_agent() -> None:
    FakeAgentClient.error = None
    FakeAgentClient.status_mailbox = readiness.READINESS_PROBE_MAILBOX
    FakeAgentClient.probes = 0
    FakeAgentClient.status_calls = 0


def test_healthz_remains_a_liveness_check():
    with TestClient(create_app(_settings())) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.text == "ok\n"


def test_main_app_registers_readyz():
    app = create_app(_settings())
    assert any(getattr(route, "path", None) == "/readyz" for route in app.routes)


async def test_readyz_requires_mailcow_and_authenticated_agent(monkeypatch):
    _reset_agent()
    monkeypatch.setattr(readiness, "MailcowAgentClient", FakeAgentClient)
    mailcow = FakeMailcow()
    transport = httpx.ASGITransport(app=_readiness_app(_settings(), mailcow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 200
    assert response.text == "ready\n"
    assert mailcow.calls == 1
    assert FakeAgentClient.probes == 1
    assert FakeAgentClient.status_calls == 1


async def test_readyz_is_not_ready_when_mailcow_is_unavailable(monkeypatch):
    _reset_agent()
    monkeypatch.setattr(readiness, "MailcowAgentClient", FakeAgentClient)
    mailcow = FakeMailcow(error=RuntimeError("mailcow unavailable"))
    transport = httpx.ASGITransport(app=_readiness_app(_settings(), mailcow))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.text == "not ready\n"


async def test_readyz_is_not_ready_when_agent_authentication_fails(monkeypatch):
    _reset_agent()
    FakeAgentClient.error = RuntimeError("authentication failed")
    monkeypatch.setattr(readiness, "MailcowAgentClient", FakeAgentClient)
    transport = httpx.ASGITransport(app=_readiness_app(_settings(), FakeMailcow()))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.text == "not ready\n"


async def test_readyz_rejects_wrong_agent_identity(monkeypatch):
    _reset_agent()
    FakeAgentClient.status_mailbox = "wrong@moolias.invalid"
    monkeypatch.setattr(readiness, "MailcowAgentClient", FakeAgentClient)
    transport = httpx.ASGITransport(app=_readiness_app(_settings(), FakeMailcow()))

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/readyz")

    assert response.status_code == 503
    assert response.text == "not ready\n"
