import httpx
from starlette.requests import Request

from moolias.auth import authorization_url
from moolias.config import Settings
from moolias.mailcow import MailcowClient


def _settings(internal_url: str = "") -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://moolias.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_INTERNAL_URL=internal_url,
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def test_backend_url_falls_back_to_public_mailcow_url():
    settings = _settings()
    assert settings.mailcow_backend_url == "https://mail.example.org"


def test_backend_url_prefers_internal_mailcow_url():
    settings = _settings("http://nginx-mailcow:8080/")
    assert settings.mailcow_url == "https://mail.example.org"
    assert settings.mailcow_internal_url == "http://nginx-mailcow:8080"
    assert settings.mailcow_backend_url == "http://nginx-mailcow:8080"


async def test_mailcow_client_uses_internal_backend_url():
    seen_url = None

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal seen_url
        seen_url = str(request.url)
        return httpx.Response(200, json=[])

    client = MailcowClient(
        _settings("http://nginx-mailcow:8080"),
        transport=httpx.MockTransport(handler),
    )
    await client.list_domains()
    await client.close()

    assert seen_url == "http://nginx-mailcow:8080/api/v1/get/domain/all"


def test_browser_oauth_authorization_stays_on_public_mailcow_url():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "session": {},
    }
    request = Request(scope)
    url = authorization_url(request, _settings("http://nginx-mailcow:8080"))

    assert url.startswith("https://mail.example.org/oauth/authorize?")
    assert "nginx-mailcow" not in url
