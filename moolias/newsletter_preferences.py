from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from moolias import newsletters as newsletter_core
from moolias.mailcow import MailcowError
from moolias.newsletter_forwarding import (
    cache_linked_mailcow_mailboxes,
    direct_mailcow_forwards_to_mailbox,
    linked_mailcow_mailbox_cache_ready,
    replace_forwarded_newsletter_tag,
)
from moolias.newsletter_mode import (
    NewsletterModeSource,
    NewsletterModeState,
    replace_mailbox_newsletter_tags,
    resolve_newsletter_mode,
)
from moolias.newsletter_mode import (
    mailbox_newsletter_state as resolve_mailbox_newsletter_state,
)
from moolias.security import require_user, validate_csrf
from moolias.ui import PAGE_SIZES, _load_ui_state, _template_context

router = APIRouter()
NEWSLETTER_MODE_SELECTIONS = {"inherit", "off", "on"}
_LINK_SESSION_KEY = "newsletter_link_cache"


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


def _link_session_value(request: Request, mailbox: str) -> str:
    base_tag = request.app.state.settings.newsletter_tag.strip().casefold()
    return f"{mailbox.strip().casefold()}|{base_tag}"


async def _refresh_linked_mailboxes(request: Request, mailbox: str) -> None:
    """Resolve source/target mailbox tags once per authenticated browser session."""

    expected = _link_session_value(request, mailbox)
    if (
        request.session.get(_LINK_SESSION_KEY) == expected
        and linked_mailcow_mailbox_cache_ready(mailbox)
    ):
        return

    list_mailboxes = getattr(request.app.state.mailcow, "list_mailboxes", None)
    if not callable(list_mailboxes):
        return
    try:
        mailboxes = await list_mailboxes()
    except MailcowError:
        # Linked mailboxes are optional. A temporary failure must not make the normal
        # Newsletter page unavailable; direct aliases continue to work as before.
        return
    cache_linked_mailcow_mailboxes(
        mailboxes,
        mailbox,
        request.app.state.settings.newsletter_tag,
    )
    request.session[_LINK_SESSION_KEY] = expected


async def mailbox_newsletter_state(
    request: Request,
    mailbox_address: str,
) -> NewsletterModeState:
    return await resolve_mailbox_newsletter_state(
        request.app.state.settings,
        request.app.state.mailcow,
        mailbox_address,
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
    await _track(request, mailbox)
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


@router.post("/account/newsletter-forwarded")
async def update_forwarded_newsletter_setting(
    request: Request,
    enabled: bool = Form(...),
    csrf_token: str = Form(...),
    return_to: str = Form("/newsletters"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    await _require_enabled(request, user)
    await _refresh_linked_mailboxes(request, user)

    mailcow = request.app.state.mailcow
    settings = request.app.state.settings
    try:
        mailbox, aliases = await asyncio.gather(
            mailcow.get_mailbox(user),
            mailcow.list_aliases(),
        )
        forwarded = direct_mailcow_forwards_to_mailbox(aliases, user)
        if enabled and not forwarded:
            raise HTTPException(
                status_code=409,
                detail="No Mailcow forwarding or linked source mailbox exists for this mailbox",
            )
        tags = replace_forwarded_newsletter_tag(
            mailbox.get("tags"),
            settings.newsletter_tag,
            enabled,
        )
        await mailcow.set_mailbox_tags(user, tags)
    except MailcowError as exc:
        raise HTTPException(
            status_code=502,
            detail="Forwarded newsletter setting could not be updated",
        ) from exc

    return RedirectResponse(_safe_return_to(return_to, "/newsletters"), status_code=303)


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
        await _refresh_linked_mailboxes(request, user)
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
            newsletter_alias_labels={},
            newsletter_sender_names={},
            newsletter_forwarded_aliases=[],
            newsletter_forwarded_enabled=False,
            newsletter_search_query="",
            newsletter_status_filter="all",
            newsletter_status_counts={"all": 0, "active": 0, "unsubscribed": 0},
            newsletter_filtered_total=0,
            newsletter_page=1,
            newsletter_per_page=25,
            newsletter_page_sizes=PAGE_SIZES,
            newsletter_total_pages=1,
            newsletter_pagination_items=[1],
            newsletter_range_start=0,
            newsletter_range_end=0,
            newsletter_collector_error=None,
            newsletter_collector_last_success=None,
            **ui_state,
        ),
    )


@router.post("/newsletters/refresh")
async def refresh_newsletters(request: Request, csrf_token: str = Form(...)):
    user = require_user(request)
    await _require_enabled(request, user)
    await _refresh_linked_mailboxes(request, user)
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


@router.post("/newsletters/{newsletter_id}/mark-unsubscribed")
async def mark_newsletter_unsubscribed(
    request: Request,
    newsletter_id: int,
    csrf_token: str = Form(...),
):
    user = require_user(request)
    await _require_enabled(request, user)
    return await newsletter_core.mark_newsletter_unsubscribed(
        request,
        newsletter_id,
        csrf_token,
    )
