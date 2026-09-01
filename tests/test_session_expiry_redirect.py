import os

import pytest
from fastapi import Request, Response
from fastapi.testclient import TestClient

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

from moolias.config import Settings
from moolias.main import create_app


PROTECTED_HTML_ROUTES = (
    "/overview",
    "/aliases",
    "/offline-pool",
    "/newsletters",
    "/statistics",
)


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


@pytest.mark.parametrize("path", PROTECTED_HTML_ROUTES)
def test_expired_html_session_redirects_to_login_page(path: str):
    app = create_app(settings())

    with TestClient(app) as client:
        response = client.get(
            path,
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert '"detail"' not in response.text


def test_expired_api_session_keeps_json_401():
    app = create_app(settings())

    with TestClient(app) as client:
        response = client.get(
            "/aliases/review-settings",
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}


def test_stale_html_form_redirects_after_session_expiry():
    app = create_app(settings())

    with TestClient(app) as client:
        response = client.post(
            "/aliases",
            data={
                "mode": "readable",
                "description": "Expired form",
                "csrf_token": "stale-csrf-token",
            },
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert '"detail"' not in response.text


def test_authenticated_invalid_csrf_stays_forbidden():
    app = create_app(settings())

    @app.get("/__test__/session")
    async def establish_test_session(request: Request):
        request.session["user_email"] = "user@example.org"
        request.session["csrf_token"] = "valid-csrf-token"
        return Response(status_code=204)

    with TestClient(app) as client:
        login_response = client.get("/__test__/session")
        assert login_response.status_code == 204

        response = client.post(
            "/aliases",
            data={
                "mode": "readable",
                "description": "Invalid CSRF",
                "csrf_token": "wrong-csrf-token",
            },
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )

    assert response.status_code == 403
    assert response.json() == {"detail": "Invalid CSRF token"}
