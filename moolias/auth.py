from __future__ import annotations

from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request, status

from moolias.config import Settings
from moolias.security import new_token


class OAuthError(RuntimeError):
    pass


def authorization_url(request: Request, settings: Settings) -> str:
    state = new_token()
    request.session["oauth_state"] = state
    query = urlencode(
        {
            "client_id": settings.mailcow_oauth_client_id,
            "redirect_uri": settings.oauth_callback_url,
            "response_type": "code",
            "scope": "profile",
            "state": state,
        }
    )
    return f"{settings.mailcow_url}/oauth/authorize?{query}"


async def exchange_code(settings: Settings, code: str) -> dict:
    backend_url = settings.mailcow_backend_url
    async with httpx.AsyncClient(verify=settings.mailcow_verify_tls, timeout=15.0) as client:
        try:
            token_response = await client.post(
                f"{backend_url}/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": settings.oauth_callback_url,
                    "client_id": settings.mailcow_oauth_client_id,
                    "client_secret": settings.mailcow_oauth_client_secret,
                },
                headers={"Accept": "application/json"},
            )
            token_response.raise_for_status()
            token = token_response.json()
            access_token = token.get("access_token")
            if not access_token:
                raise OAuthError("mailcow did not return an access token")

            profile_response = await client.get(
                f"{backend_url}/oauth/profile",
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            profile_response.raise_for_status()
            profile = profile_response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise OAuthError(f"mailcow OAuth request failed: {exc}") from exc

    if not isinstance(profile, dict) or not profile.get("success"):
        raise OAuthError("mailcow OAuth profile was not accepted")
    return profile


def validate_oauth_state(request: Request, supplied_state: str | None) -> None:
    expected = request.session.pop("oauth_state", None)
    if not expected or not supplied_state or supplied_state != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
