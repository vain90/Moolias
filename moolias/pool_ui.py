from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from moolias.alias_table_ui import router as alias_table_router
from moolias.aliases import (
    RESERVED_COMMENT,
    RESERVED_MARKER,
    USED_RESERVED_MARKER,
    is_owned_alias,
    mailbox_domain,
    readable_local_part,
    update_private_comment,
    validate_local_part,
)
from moolias.i18n import LANGUAGE_COOKIE, detect_language
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf
from moolias.statistics_destinations import top_outgoing_destinations
from moolias.stats_mode import StatsMode
from moolias.usage import mailbox_stats_state

router = APIRouter()
router.include_router(alias_table_router)
SENDER_DECISIONS = {"expected", "unexpected", "clear"}


def _language(request: Request) -> str:
    return detect_language(
        request.cookies.get(LANGUAGE_COOKIE),
        request.headers.get("accept-language"),
    )


async def _owned_alias(request: Request, alias_id: int):
    user = require_user(request)
    try:
        alias = await request.app.state.mailcow.get_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not is_owned_alias(alias, user):
        raise HTTPException(status_code=403, detail="Alias is not owned by the current mailbox")
    return user, alias


async def _create_unique_reserved(request: Request, user: str, attempts: int = 12) -> None:
    domain = mailbox_domain(user)
    last_error: Exception | None = None
    for _ in range(attempts):
        address = f"{validate_local_part(readable_local_part(_language(request)))}@{domain}"
        try:
            await request.app.state.mailcow.create_alias(
                address,
                user,
                "",
                private_comment=RESERVED_COMMENT,
                sogo_visible=False,
            )
            return
        except MailcowError as exc:
            last_error = exc
    raise MailcowError(
        f"Could not create a unique offline alias after {attempts} attempts: {last_error}"
    )


@router.get("/aliases/private-descriptions")
async def alias_private_descriptions(request: Request):
    user = require_user(request)
    try:
        aliases = await request.app.state.mailcow.list_aliases()
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "descriptions": {
            str(alias.id): alias.private_description
            for alias in aliases
            if is_owned_alias(alias, user)
        }
    }


@router.get("/statistics", response_class=HTMLResponse)
async def statistics_page(
    request: Request,
    detail: str = Query(default="address"),
):
    # Imported lazily to keep the existing router inclusion order free of cycles.
    from moolias.ui import TEMPLATES, _load_ui_state, _template_context

    state = await _load_ui_state(request)
    destinations: list[dict[str, int | str]] = []
    destination_stats_error = False
    destination_mode_available = False
    detail_toggle_available = False
    stats_state = state.get("stats_state")
    detail = detail if detail in {"domain", "address"} else "address"

    if state.get("usage_stats_visible") and stats_state is not None:
        mode = stats_state.effective
        detail_toggle_available = mode is StatsMode.FULL
        if not detail_toggle_available:
            detail = "domain"

        if detail_toggle_available and detail == "address":
            source_counts: Counter[str] = Counter()
            for rows in state.get("sender_stats", {}).values():
                for row in rows:
                    label = str(row.get("label") or row.get("domain") or "").strip().lower()
                    if label:
                        source_counts[label] += int(row.get("received_count") or 0)
            state["top_sources"] = source_counts.most_common(8)

        destination_mode_available = mode in {StatsMode.DOMAIN, StatsMode.FULL}
        if destination_mode_available:
            destination_view_mode = (
                StatsMode.FULL
                if mode is StatsMode.FULL and detail == "address"
                else StatsMode.DOMAIN
            )
            try:
                destinations = await top_outgoing_destinations(
                    request.app.state.settings,
                    request.app.state.mailcow,
                    state["user"],
                    state["assigned_all"],
                    destination_view_mode,
                )
            except MailcowError:
                destination_stats_error = True

    state.update(
        {
            "top_destinations": destinations,
            "destination_mode_available": destination_mode_available,
            "destination_stats_error": destination_stats_error,
            "statistics_detail": detail,
            "statistics_detail_toggle_available": detail_toggle_available,
        }
    )
    return TEMPLATES.TemplateResponse(
        request,
        "statistics.html",
        _template_context(request, active_nav="statistics", **state),
    )


@router.post("/offline-pool/create")
async def create_offline_pool_aliases(
    request: Request,
    count: int = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if count not in {1, 5, 10}:
        raise HTTPException(status_code=400, detail="Pool size must be 1, 5 or 10")
    try:
        for _ in range(count):
            await _create_unique_reserved(request, user)
    except (MailcowError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/offline-pool", status_code=303)


@router.post("/offline-pool/{alias_id}/assign")
async def assign_offline_pool_alias(
    request: Request,
    alias_id: int,
    description: str = Form(...),
    private_description: str = Form(""),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    _, alias = await _owned_alias(request, alias_id)
    if not alias.is_reserved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only offline aliases can be assigned",
        )
    name = description.strip()
    private_description = private_description.strip()
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(private_description) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")

    private_comment = update_private_comment(
        alias.private_comment,
        description=private_description,
        remove_markers={RESERVED_MARKER, USED_RESERVED_MARKER},
    )
    try:
        await request.app.state.mailcow.assign_reserved_alias(
            alias_id,
            name,
            sogo_visible,
            private_comment=private_comment,
        )
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/offline-pool", status_code=303)


@router.post("/offline-pool/{alias_id}/sender-expectation")
async def update_offline_sender_expectation(
    request: Request,
    alias_id: int,
    sender_key: str = Form(...),
    decision: str = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user, alias = await _owned_alias(request, alias_id)
    if not alias.is_reserved:
        raise HTTPException(status_code=409, detail="Sender review is only available here")
    if decision not in SENDER_DECISIONS:
        raise HTTPException(status_code=400, detail="Unknown sender review decision")

    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    if not settings.usage_stats or stats_store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")

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

    stored = await stats_store.sender_usage(user, [alias.address])
    sender_entries = stored.get(alias.address.lower(), [])
    if not any(entry.sender_key == sender_key for entry in sender_entries):
        raise HTTPException(status_code=404, detail="Sender statistic does not exist")

    expected = {
        "expected": True,
        "unexpected": False,
        "clear": None,
    }[decision]
    await stats_store.set_sender_expectation(
        user,
        alias.address,
        sender_key,
        expected,
    )
    return RedirectResponse("/offline-pool", status_code=303)


@router.post("/offline-pool/{alias_id}/delete")
async def delete_offline_pool_alias(
    request: Request,
    alias_id: int,
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user, alias = await _owned_alias(request, alias_id)
    if not alias.is_reserved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only offline aliases can be deleted",
        )
    if alias.is_reserved_used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Used offline aliases must be assigned before they can be deleted",
        )

    stats_store = getattr(request.app.state, "stats_store", None)
    if stats_store is not None:
        stored_usage = await stats_store.alias_usage(user, [alias.address])
        usage = stored_usage.get(alias.address.lower())
        if usage is not None and (usage.received_count > 0 or usage.sent_count > 0):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Used offline aliases must be assigned before they can be deleted",
            )

    try:
        await request.app.state.mailcow.delete_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/offline-pool", status_code=303)
