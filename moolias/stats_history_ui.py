from __future__ import annotations

import time
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import RedirectResponse

from moolias.aliases import is_owned_alias, is_primary_mailbox_alias
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf
from moolias.stats_history import StatsHistoryStore
from moolias.stats_mode import (
    StatsMode,
    is_stats_mode_downgrade,
    replace_mailbox_stats_tags,
    resolve_stats_mode,
    selected_effective_mode,
    stats_mode_rank,
)
from moolias.usage import mailbox_stats_state

router = APIRouter()
STATS_MODE_SELECTIONS = {"inherit", "off", "basic", "domain", "full"}
SENDER_DECISIONS = {"expected", "unexpected", "clear"}


def _safe_return_to(value: str | None, fallback: str = "/aliases") -> str:
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return fallback
    if value.startswith("//"):
        return fallback
    return value


async def _sender_exists(
    request: Request,
    mailbox: str,
    alias: str,
    sender_key: str,
    mode: StatsMode,
) -> bool:
    stats_store = request.app.state.stats_store
    stored = await stats_store.sender_usage(mailbox, [alias])
    if any(entry.sender_key == sender_key for entry in stored.get(alias.lower(), [])):
        return True

    history_store = StatsHistoryStore(stats_store.path)
    if mode is StatsMode.DOMAIN:
        levels = (StatsMode.DOMAIN,)
    elif mode is StatsMode.FULL:
        levels = (StatsMode.FULL, StatsMode.DOMAIN)
    else:
        return False

    for level in levels:
        historical = await history_store.sender_usage(mailbox, [alias], level=level)
        if any(entry.sender_key == sender_key for entry in historical.get(alias.lower(), [])):
            return True
    return False


@router.post("/aliases/stats-mode")
async def update_stats_mode_with_history(
    request: Request,
    mode: str = Form(...),
    csrf_token: str = Form(...),
    return_to: str = Form("/aliases"),
    confirm_downgrade: bool = Form(False),
    backfill_history: bool = Form(False),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    settings = request.app.state.settings
    mailcow = request.app.state.mailcow
    stats_store = getattr(request.app.state, "stats_store", None)
    if not settings.usage_stats or stats_store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")
    if mode not in STATS_MODE_SELECTIONS:
        raise HTTPException(status_code=400, detail="Unknown statistics mode")

    changed_at = int(time.time())
    try:
        mailbox = await mailcow.get_mailbox(user)
        domain_name = str(
            mailbox.get("domain") or user.rsplit("@", 1)[-1]
        ).strip().lower()
        domain_details = await mailcow.get_domain(domain_name)
        current_state = resolve_stats_mode(
            mailbox.get("tags"),
            domain_details.get("tags"),
            settings.usage_tag,
        )
        target_mode = selected_effective_mode(mode, current_state.domain_default)
        stored_mode = await stats_store.sender_mode(user)
        confirmation_mode = (
            StatsMode(stored_mode) if stored_mode is not None else current_state.effective
        )
        if (
            is_stats_mode_downgrade(confirmation_mode, target_mode)
            and not confirm_downgrade
        ):
            raise HTTPException(
                status_code=409,
                detail="Statistics downgrade requires confirmation",
            )

        tags = replace_mailbox_stats_tags(
            mailbox.get("tags"),
            settings.usage_tag,
            mode,
        )
        await mailcow.set_mailbox_tags(user, tags)
        state = await mailbox_stats_state(settings, mailcow, user)
        mode_starts = await stats_store.sync_sender_modes(
            {user: state.effective.value},
            now=changed_at,
        )

        history_store = StatsHistoryStore(stats_store.path)
        await history_store.sync_mode(
            user,
            state.effective,
            started_at=mode_starts.get(user, changed_at),
        )
        if (
            backfill_history
            and stats_mode_rank(state.effective) > stats_mode_rank(confirmation_mode)
        ):
            await history_store.request_backfill(
                user,
                state.effective,
                requested_at=changed_at,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.post("/aliases/{alias_id}/sender-expectation")
async def update_sender_expectation_with_history(
    request: Request,
    alias_id: int,
    sender_key: str = Form(...),
    decision: str = Form(...),
    csrf_token: str = Form(...),
    return_to: str = Form("/aliases"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    if not settings.usage_stats or stats_store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")
    if decision not in SENDER_DECISIONS:
        raise HTTPException(status_code=400, detail="Unknown sender review decision")

    try:
        alias = await request.app.state.mailcow.get_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(status_code=403, detail="Alias cannot be managed here")

    sender_key = sender_key.strip().lower()
    if not sender_key or len(sender_key) > 320:
        raise HTTPException(status_code=400, detail="Invalid sender key")

    try:
        state = await mailbox_stats_state(settings, request.app.state.mailcow, user)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not state.sender_detail_enabled:
        raise HTTPException(
            status_code=409,
            detail="Sender statistics are not enabled for this mailbox",
        )
    if not await _sender_exists(request, user, alias.address, sender_key, state.effective):
        raise HTTPException(status_code=404, detail="Sender statistic does not exist")

    expected = {
        "expected": True,
        "unexpected": False,
        "clear": None,
    }[decision]
    await stats_store.set_sender_expectation(user, alias.address, sender_key, expected)
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.post("/offline-pool/{alias_id}/sender-expectation")
async def update_offline_sender_expectation_with_history(
    request: Request,
    alias_id: int,
    sender_key: str = Form(...),
    decision: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    if not settings.usage_stats or stats_store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")
    if decision not in SENDER_DECISIONS:
        raise HTTPException(status_code=400, detail="Unknown sender review decision")

    try:
        alias = await request.app.state.mailcow.get_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not is_owned_alias(alias, user) or not alias.is_reserved:
        raise HTTPException(status_code=403, detail="Offline alias cannot be managed here")

    sender_key = sender_key.strip().lower()
    if not sender_key or len(sender_key) > 320:
        raise HTTPException(status_code=400, detail="Invalid sender key")

    try:
        state = await mailbox_stats_state(settings, request.app.state.mailcow, user)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not state.sender_detail_enabled:
        raise HTTPException(
            status_code=409,
            detail="Sender statistics are not enabled for this mailbox",
        )
    if not await _sender_exists(request, user, alias.address, sender_key, state.effective):
        raise HTTPException(status_code=404, detail="Sender statistic does not exist")

    expected = {
        "expected": True,
        "unexpected": False,
        "clear": None,
    }[decision]
    await stats_store.set_sender_expectation(user, alias.address, sender_key, expected)
    return RedirectResponse("/offline-pool", status_code=303)


@router.post("/aliases/{alias_id}/sender-domain-expectation")
async def set_sender_domain_expectation_with_history(
    request: Request,
    alias_id: int,
    sender_key: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    if not settings.usage_stats or stats_store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")

    try:
        alias = await request.app.state.mailcow.get_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(status_code=403, detail="Alias cannot be managed here")

    sender_key = sender_key.strip().lower()
    if not sender_key or "@" not in sender_key or len(sender_key) > 320:
        raise HTTPException(status_code=400, detail="Invalid sender key")

    try:
        state = await mailbox_stats_state(settings, request.app.state.mailcow, user)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if state.conflict or state.effective is not StatsMode.FULL:
        raise HTTPException(
            status_code=409,
            detail="Domain expectation is only available in full statistics mode",
        )

    domain = sender_key.rsplit("@", 1)[1]
    if not await _sender_exists(request, user, alias.address, sender_key, StatsMode.FULL):
        raise HTTPException(status_code=404, detail="Sender statistic does not exist")

    await stats_store.set_sender_expectation(user, alias.address, domain, True)
    return {
        "alias": alias.address,
        "domain": domain,
        "expected": True,
    }
