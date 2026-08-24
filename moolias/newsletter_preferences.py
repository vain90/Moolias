from __future__ import annotations

import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from moolias import newsletters as newsletter_core
from moolias.mailcow import MailcowError
from moolias.newsletter_mode import (
    NewsletterModeSource,
    NewsletterModeState,
    replace_mailbox_newsletter_tags,
    resolve_newsletter_mode,
)
from moolias.security import require_user, validate_csrf
from moolias.ui import _load_ui_state, _template_context

router = APIRouter()
NEWSLETTER_MODE_SELECTIONS = {"inherit", "off", "on"}


def _safe_return_to(value: str | None, fallback: str = "/overview") -> str:
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return fallback
    if value.startswith("//"):
        return fallback
    return value


def _untrack(request: Request, mailbox: str) -> None:
    collector = getattr(request.app.state, "newsletter_collector", None)
    if collector is not None:
        collector._tracked_mailboxes.discard(mailbox.casefold())


async def _track(request: Request, mailbox: str) -> None:
    store, collector = await newsletter_core._runtime(request)
    if await store.history_since(mailbox) is None:
        # A tag can be enabled directly by an administrator outside Moolias. In that
        # case there was no interactive history choice, so fail privacy-safe and start
        # with messages arriving from now on instead of silently importing history.
        await store.set_history_since(mailbox, int(time.time()))
    collector.track(mailbox)


async def mailbox_newsletter_state(
    request: Request,
    mailbox_address: str,
) -> NewsletterModeState:
    settings = request.app.state.settings
    if not settings.newsletter_management:
        return resolve_newsletter_mode([], [], settings.newsletter_tag)

    mailcow = request.app.state.mailcow
    mailbox = await mailcow.get_mailbox(mailbox_address)
    domain_name = str(
        mailbox.get("domain") or mailbox_address.rsplit("@", 1)[-1]
    ).strip().lower()
    domain = await mailcow.get_domain(domain_name)
    return resolve_newsletter_mode(
        mailbox.get("tags"),
        domain.get("tags"),
        settings.newsletter_tag,
    )


def _selection(state: NewsletterModeState) -> str:
    if state.conflict and state.conflict_source is NewsletterModeSource.MAILBOX:
        return "conflict"
    if state.mailbox_override is not None:
        return state.mailbox_override.value
    return "inherit"


async def _require_enabled(request: Request, mailbox: str) -> NewsletterModeState:
    if not request.app.state.settings.newsletter_management:
        raise HTTPException(
            status_code=409,
            detail="Newsletter management is disabled server-side",
        )
    try:
        state = await mailbox_newsletter_state(request, mailbox)
    except MailcowError as exc:
        raise HTTPException(
            status_code=502,
            detail="Newsletter policy is unavailable",
        ) from exc
    if state.conflict or not state.enabled:
        raise HTTPException(
            status_code=409,
            detail="Newsletter management is disabled for this mailbox",
        )
    return state


@router.get("/account/newsletter-management")
async def get_newsletter_management_setting(request: Request):
    user = require_user(request)
    server_enabled = request.app.state.settings.newsletter_management
    try:
        state = await mailbox_newsletter_state(request, user)
    except MailcowError as exc:
        raise HTTPException(
            status_code=502,
            detail="Newsletter policy is unavailable",
        ) from exc

    effective_enabled = server_enabled and not state.conflict and state.enabled
    if effective_enabled:
        await _track(request, user)
    else:
        _untrack(request, user)

    return {
        "server_enabled": server_enabled,
        "effective_enabled": effective_enabled,
        "selection": _selection(state),
        "effective": state.effective.value,
        "source": state.source.value,
        "mailbox_override": (
            state.mailbox_override.value if state.mailbox_override is not None else None
        ),
        "domain_default": (
            state.domain_default.value if state.domain_default is not None else None
        ),
        "conflict": state.conflict,
        "conflict_source": (
            state.conflict_source.value if state.conflict_source is not None else None
        ),
    }


@router.post("/account/newsletter-management")
async def update_newsletter_management_setting(
    request: Request,
    mode: str = Form(...),
    backfill_history: bool | None = Form(None),
    csrf_token: str = Form(...),
    return_to: str = Form("/overview"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    settings = request.app.state.settings
    if not settings.newsletter_management:
        raise HTTPException(
            status_code=409,
            detail="Newsletter management is disabled server-side",
        )
    if mode not in NEWSLETTER_MODE_SELECTIONS:
        raise HTTPException(status_code=400, detail="Unknown newsletter mode")

    mailcow = request.app.state.mailcow
    try:
        mailbox = await mailcow.get_mailbox(user)
        domain_name = str(
            mailbox.get("domain") or user.rsplit("@", 1)[-1]
        ).strip().lower()
        domain = await mailcow.get_domain(domain_name)
        current_state = resolve_newsletter_mode(
            mailbox.get("tags"),
            domain.get("tags"),
            settings.newsletter_tag,
        )
        tags = replace_mailbox_newsletter_tags(
            mailbox.get("tags"),
            settings.newsletter_tag,
            mode,
        )
        target_state = resolve_newsletter_mode(
            tags,
            domain.get("tags"),
            settings.newsletter_tag,
        )
        activating = (
            (current_state.conflict or not current_state.enabled)
            and not target_state.conflict
            and target_state.enabled
        )
        if activating and backfill_history is None:
            raise HTTPException(
                status_code=400,
                detail="Choose whether available newsletter history should be imported",
            )

        await mailcow.set_mailbox_tags(user, tags)
        state = await mailbox_newsletter_state(request, user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MailcowError as exc:
        raise HTTPException(
            status_code=502,
            detail="Newsletter policy could not be updated",
        ) from exc

    if not state.conflict and state.enabled:
        store, collector = await newsletter_core._runtime(request)
        if activating:
            await store.set_history_since(
                user,
                0 if backfill_history else int(time.time()),
            )
        elif await store.history_since(user) is None:
            await store.set_history_since(user, int(time.time()))
        collector.track(user)
    else:
        _untrack(request, user)
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.get("/newsletters", response_class=HTMLResponse)
async def newsletters_page(request: Request):
    user = require_user(request)
    server_enabled = request.app.state.settings.newsletter_management
    try:
        state = await mailbox_newsletter_state(request, user)
    except MailcowError as exc:
        raise HTTPException(
            status_code=502,
            detail="Newsletter policy is unavailable",
        ) from exc

    if server_enabled and not state.conflict and state.enabled:
        await _track(request, user)
        return await newsletter_core.newsletters_page(request)

    _untrack(request, user)
    ui_state = await _load_ui_state(request)
    return newsletter_core.TEMPLATES.TemplateResponse(
        request,
        "newsletters.html",
        _template_context(
            request,
            active_nav="newsletters",
            newsletter_enabled=False,
            newsletter_server_enabled=server_enabled,
            newsletter_mode_state=state,
            newsletter_mode_selection=_selection(state),
            newsletters=[],
            newsletter_collector_error=None,
            newsletter_collector_last_success=None,
            **ui_state,
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
