from __future__ import annotations

import sqlite3
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from moolias import newsletters as newsletter_core
from moolias.mailbox_settings import MailboxSettingsStore
from moolias.security import require_user, validate_csrf
from moolias.ui import _load_ui_state, _template_context

router = APIRouter()


def _safe_return_to(value: str | None, fallback: str = "/overview") -> str:
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return fallback
    if value.startswith("//"):
        return fallback
    return value


def _store(request: Request) -> MailboxSettingsStore:
    return MailboxSettingsStore(request.app.state.settings.usage_db_path)


async def _preference(request: Request, mailbox: str) -> bool | None:
    try:
        return await _store(request).newsletter_enabled(mailbox)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Mailbox settings database is unavailable",
        ) from exc


async def _require_enabled(request: Request, mailbox: str) -> None:
    if not request.app.state.settings.newsletter_management:
        raise HTTPException(
            status_code=409,
            detail="Newsletter management is disabled server-side",
        )
    if await _preference(request, mailbox) is not True:
        raise HTTPException(
            status_code=409,
            detail="Newsletter management is disabled for this mailbox",
        )


@router.get("/account/newsletter-management")
async def get_newsletter_management_setting(request: Request):
    user = require_user(request)
    server_enabled = request.app.state.settings.newsletter_management
    preference = await _preference(request, user)
    return {
        "server_enabled": server_enabled,
        "preference": preference,
        "effective_enabled": server_enabled and preference is True,
    }


@router.post("/account/newsletter-management")
async def update_newsletter_management_setting(
    request: Request,
    enabled: bool = Form(False),
    csrf_token: str = Form(...),
    return_to: str = Form("/overview"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if not request.app.state.settings.newsletter_management:
        raise HTTPException(
            status_code=409,
            detail="Newsletter management is disabled server-side",
        )
    try:
        await _store(request).set_newsletter_enabled(user, enabled)
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Mailbox settings database is unavailable",
        ) from exc
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.get("/newsletters", response_class=HTMLResponse)
async def newsletters_page(request: Request):
    user = require_user(request)
    server_enabled = request.app.state.settings.newsletter_management
    preference = await _preference(request, user)
    if server_enabled and preference is True:
        return await newsletter_core.newsletters_page(request)

    state = await _load_ui_state(request)
    return newsletter_core.TEMPLATES.TemplateResponse(
        request,
        "newsletters.html",
        _template_context(
            request,
            active_nav="newsletters",
            newsletter_enabled=False,
            newsletter_server_enabled=server_enabled,
            newsletter_user_preference=preference,
            newsletters=[],
            newsletter_collector_error=None,
            newsletter_collector_last_success=None,
            **state,
        ),
    )


@router.post("/newsletters/refresh")
async def refresh_newsletters(request: Request, csrf_token: str = Form(...)):
    user = require_user(request)
    await _require_enabled(request, user)
    return await newsletter_core.refresh_newsletters(request, csrf_token)


@router.post("/newsletters/{newsletter_id}/unsubscribe")
async def unsubscribe_newsletter(
    request: Request,
    newsletter_id: int,
    csrf_token: str = Form(...),
):
    user = require_user(request)
    await _require_enabled(request, user)
    return await newsletter_core.unsubscribe_newsletter(
        request,
        newsletter_id,
        csrf_token,
    )
