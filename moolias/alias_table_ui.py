from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from moolias.aliases import (
    RESERVED_MARKER,
    USED_RESERVED_MARKER,
    is_owned_alias,
    is_primary_mailbox_alias,
    mailbox_domain,
    named_local_part,
    readable_local_part,
    update_private_comment,
    validate_local_part,
)
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf
from moolias.ui import (
    PAGE_SIZES,
    STATUS_FILTERS,
    TEMPLATES,
    _language,
    _load_ui_state,
    _pagination_items,
    _safe_return_to,
    _template_context,
)

router = APIRouter()
SORT_MODES = {"attention", "last_used", "usage", "most_used", "status", "purpose"}
SORT_DIRECTIONS = {"asc", "desc"}


async def _submitted_private_description(
    request: Request,
    parsed_value: str | None,
    *,
    fallback: str,
) -> str:
    form = await request.form()
    if "private_description" not in form:
        return fallback
    return (parsed_value or "").strip()


async def _create_unique_alias(
    request: Request,
    user: str,
    factory,
    *,
    public_comment: str,
    private_comment: str,
    sogo_visible: bool,
    attempts: int = 12,
) -> str:
    domain = mailbox_domain(user)
    last_error: Exception | None = None
    for _ in range(attempts):
        address = f"{validate_local_part(factory())}@{domain}"
        try:
            await request.app.state.mailcow.create_alias(
                address,
                user,
                public_comment,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
            return address
        except MailcowError as exc:
            last_error = exc
    raise MailcowError(
        f"Could not create a unique alias after {attempts} attempts: {last_error}"
    )


@router.get("/aliases", response_class=HTMLResponse)
async def aliases_page(
    request: Request,
    q: str = Query(default="", max_length=160),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25),
    status_filter: str = Query(default="all", alias="status"),
    sort: str = Query(default="attention"),
    direction: str = Query(default="desc"),
):
    state = await _load_ui_state(request)
    if per_page not in PAGE_SIZES:
        per_page = 25
    if status_filter not in STATUS_FILTERS:
        status_filter = "all"
    if sort not in SORT_MODES:
        sort = "attention"
    if sort == "most_used":
        sort = "usage"
    if direction not in SORT_DIRECTIONS:
        direction = "desc"

    assigned_all = list(state["assigned_all"])
    unexpected_aliases = state["unexpected_aliases"]
    no_usage_evidence = state["no_usage_evidence"]
    usage_stats = state["usage_stats"]

    if status_filter == "active":
        filtered = [alias for alias in assigned_all if alias.active]
    elif status_filter == "disabled":
        filtered = [alias for alias in assigned_all if not alias.active]
    elif status_filter == "unexpected":
        filtered = [
            alias
            for alias in assigned_all
            if alias.address.lower() in unexpected_aliases
        ]
    elif status_filter == "unused":
        filtered = [
            alias
            for alias in assigned_all
            if alias.address.lower() in no_usage_evidence
        ]
    else:
        filtered = assigned_all

    search_query = q.strip()
    if search_query:
        needle = search_query.lower()
        filtered = [
            alias
            for alias in filtered
            if needle
            in f"{alias.address} {alias.name} {alias.private_description}".lower()
        ]

    def usage_total(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("received_count") or 0) + int(usage.get("sent_count") or 0)

    def last_used(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("last_used_at") or 0)

    def purpose(alias) -> tuple[str, str]:
        return ((alias.name or "").casefold(), alias.address.lower())

    def status_rank(alias) -> tuple[int, str, str]:
        address = alias.address.lower()
        if address in unexpected_aliases:
            rank = 2
        elif alias.active:
            rank = 1
        else:
            rank = 0
        purpose_key, address_key = purpose(alias)
        return (rank, purpose_key, address_key)

    def usage_sort_key(alias) -> tuple[int, int, str, str]:
        purpose_key, address_key = purpose(alias)
        return (usage_total(alias), last_used(alias), purpose_key, address_key)

    def last_used_sort_key(alias) -> tuple[int, int, str, str]:
        purpose_key, address_key = purpose(alias)
        return (last_used(alias), usage_total(alias), purpose_key, address_key)

    def attention_sort_key(alias) -> tuple[int, int, int, str, str]:
        purpose_key, address_key = purpose(alias)
        return (
            1 if alias.address.lower() in unexpected_aliases else 0,
            last_used(alias),
            usage_total(alias),
            purpose_key,
            address_key,
        )

    sort_keys = {
        "attention": attention_sort_key,
        "purpose": purpose,
        "status": status_rank,
        "usage": usage_sort_key,
        "last_used": last_used_sort_key,
    }
    filtered.sort(key=sort_keys[sort], reverse=direction == "desc")

    filtered_total = len(filtered)
    total_pages = max(1, (filtered_total + per_page - 1) // per_page)
    page = min(page, total_pages)
    offset = (page - 1) * per_page
    assigned = filtered[offset : offset + per_page]

    status_counts = {
        "all": len(assigned_all),
        "active": sum(alias.active for alias in assigned_all),
        "disabled": sum(not alias.active for alias in assigned_all),
        "unexpected": len(unexpected_aliases),
        "unused": len(no_usage_evidence),
    }

    state.update(
        {
            "assigned": assigned,
            "filtered_total": filtered_total,
            "search_query": search_query,
            "status_filter": status_filter,
            "status_counts": status_counts,
            "sort_mode": sort,
            "sort_direction": direction,
            "page": page,
            "per_page": per_page,
            "page_sizes": PAGE_SIZES,
            "total_pages": total_pages,
            "pagination_items": _pagination_items(page, total_pages),
            "range_start": offset + 1 if filtered_total else 0,
            "range_end": min(offset + per_page, filtered_total),
        }
    )
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        _template_context(request, active_nav="aliases", **state),
    )


@router.post("/aliases")
async def create_alias(
    request: Request,
    mode: str = Form(...),
    description: str = Form(...),
    private_description: str = Form(""),
    local_part: str = Form(""),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    name = description.strip()
    private_description = private_description.strip()
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(private_description) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")
    private_comment = update_private_comment("", description=private_description)

    try:
        if mode == "readable":
            address = await _create_unique_alias(
                request,
                user,
                lambda: readable_local_part(_language(request)),
                public_comment=name,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
        elif mode == "named":
            address = await _create_unique_alias(
                request,
                user,
                lambda: named_local_part(name),
                public_comment=name,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
        elif mode == "custom":
            address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
            await request.app.state.mailcow.create_alias(
                address,
                user,
                name,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
        else:
            raise HTTPException(status_code=400, detail="Unknown alias mode")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if "application/json" in request.headers.get("accept", "").lower():
        return {
            "kind": "alias_creation",
            "state": "created",
            "address": address,
            "name": name,
            "description": private_description,
            "sogo_visible": sogo_visible,
        }
    return RedirectResponse("/aliases", status_code=303)


@router.post("/aliases/{alias_id}/metadata")
async def update_metadata(
    request: Request,
    alias_id: int,
    description: str = Form(""),
    private_description: str | None = Form(None),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
    return_to: str = Form("/aliases"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    alias = await request.app.state.mailcow.get_alias(alias_id)
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(status_code=403, detail="Alias cannot be edited here")

    name = description.strip()
    description_text = await _submitted_private_description(
        request,
        private_description,
        fallback=alias.private_description,
    )
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(description_text) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")

    private_comment = update_private_comment(
        alias.private_comment,
        description=description_text,
    )
    try:
        await request.app.state.mailcow.update_alias_preferences(
            alias_id,
            name,
            sogo_visible,
            private_comment=private_comment,
        )
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.post("/aliases/{alias_id}/description")
async def assign_reserved_alias_compatibility(
    request: Request,
    alias_id: int,
    description: str = Form(...),
    private_description: str | None = Form(None),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    alias = await request.app.state.mailcow.get_alias(alias_id)
    if not is_owned_alias(alias, user) or not alias.is_reserved:
        raise HTTPException(status_code=409, detail="Alias is not reserved")

    name = description.strip()
    description_text = await _submitted_private_description(
        request,
        private_description,
        fallback=alias.private_description,
    )
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(description_text) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")
    private_comment = update_private_comment(
        alias.private_comment,
        description=description_text,
        remove_markers={RESERVED_MARKER, USED_RESERVED_MARKER},
    )
    await request.app.state.mailcow.assign_reserved_alias(
        alias_id,
        name,
        sogo_visible,
        private_comment=private_comment,
    )
    return RedirectResponse("/aliases", status_code=303)


@router.post("/aliases/{alias_id}/replace")
async def replace_alias(
    request: Request,
    alias_id: int,
    mode: str = Form("named"),
    local_part: str = Form(""),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    alias = await request.app.state.mailcow.get_alias(alias_id)
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This alias cannot be replaced",
        )
    if mode not in {"named", "readable", "custom"}:
        raise HTTPException(status_code=400, detail="Unknown replacement mode")

    replacement_name = alias.name or "alias"
    try:
        if mode == "named":
            new_address = await _create_unique_alias(
                request,
                user,
                lambda: named_local_part(replacement_name),
                public_comment=alias.public_comment,
                private_comment=alias.private_comment,
                sogo_visible=alias.sogo_visible,
            )
        elif mode == "readable":
            new_address = await _create_unique_alias(
                request,
                user,
                lambda: readable_local_part(_language(request)),
                public_comment=alias.public_comment,
                private_comment=alias.private_comment,
                sogo_visible=alias.sogo_visible,
            )
        else:
            new_address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
            await request.app.state.mailcow.create_alias(
                new_address,
                user,
                alias.public_comment,
                private_comment=alias.private_comment,
                sogo_visible=alias.sogo_visible,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    try:
        await request.app.state.mailcow.set_active(alias_id, False)
    except MailcowError as exc:
        raise HTTPException(
            status_code=502,
            detail={
                "code": "partial_replacement",
                "message": (
                    "The replacement alias was created, but the old alias "
                    "could not be disabled"
                ),
                "address": new_address,
            },
        ) from exc

    return {"address": new_address, "old_address": alias.address}
