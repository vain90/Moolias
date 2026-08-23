from __future__ import annotations

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from moolias.ui import (
    PAGE_SIZES,
    STATUS_FILTERS,
    TEMPLATES,
    _load_ui_state,
    _pagination_items,
    _template_context,
)

router = APIRouter()
SORT_MODES = {"attention", "last_used", "usage", "most_used", "status", "purpose"}
SORT_DIRECTIONS = {"asc", "desc"}


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
            if needle in f"{alias.address} {alias.public_comment}".lower()
        ]

    def usage_total(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("received_count") or 0) + int(usage.get("sent_count") or 0)

    def last_used(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("last_used_at") or 0)

    def purpose(alias) -> tuple[str, str]:
        return ((alias.description or "").casefold(), alias.address.lower())

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