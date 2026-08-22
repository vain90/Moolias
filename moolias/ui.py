from __future__ import annotations

import asyncio
import sqlite3
import time
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from moolias import __version__
from moolias.aliases import (
    is_mailbox_catch_all,
    is_owned_alias,
    is_primary_mailbox_alias,
    mailbox_domain,
)
from moolias.collector_health import CollectorHealthStore, assess_collector_health
from moolias.i18n import LANGUAGE_COOKIE, detect_language, translations
from moolias.mailcow import MailcowAccessDenied, MailcowError
from moolias.security import ensure_csrf_token, require_user, validate_csrf
from moolias.senders import sender_match_token
from moolias.service_icons import icon_catalog, resolve_service_icon
from moolias.stats_mode import StatsModeSource
from moolias.usage import mailbox_stats_state

router = APIRouter()
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))

PAGE_SIZES = (10, 25, 50, 100)
STATUS_FILTERS = ("all", "active", "disabled", "unexpected")
SORT_MODES = ("last_used", "most_used")
SORT_DIRECTIONS = ("asc", "desc")
ACTIONABLE_HEALTH_STATES = {"low", "gap", "stale", "failed"}


def _safe_return_to(value: str | None, fallback: str = "/aliases") -> str:
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return fallback
    if value.startswith("//"):
        return fallback
    return value


def _language(request: Request) -> str:
    return detect_language(
        request.cookies.get(LANGUAGE_COOKIE),
        request.headers.get("accept-language"),
    )


def _template_context(request: Request, **values):
    language = _language(request)
    return_to = request.url.path
    if request.url.query:
        return_to = f"{return_to}?{request.url.query}"
    return {
        "language": language,
        "t": translations(language),
        "return_to": return_to,
        "version": __version__,
        **values,
    }


def _pagination_items(current_page: int, total_pages: int) -> list[int | None]:
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    visible = {1, total_pages}
    visible.update(
        page
        for page in range(current_page - 2, current_page + 3)
        if 1 <= page <= total_pages
    )
    items: list[int | None] = []
    previous = 0
    for page in sorted(visible):
        if previous and page - previous > 1:
            items.append(None)
        items.append(page)
        previous = page
    return items


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


class IconPreferenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS alias_icon_settings (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                icon_key TEXT NOT NULL,
                PRIMARY KEY (mailbox, alias)
            )
            """
        )
        return connection

    async def get_many(self, mailbox: str, aliases: list[str]) -> dict[str, str]:
        if not aliases:
            return {}
        return await asyncio.to_thread(self._get_many, mailbox, aliases)

    def _get_many(self, mailbox: str, aliases: list[str]) -> dict[str, str]:
        placeholders = ",".join("?" for _ in aliases)
        query = f"""
            SELECT alias, icon_key
            FROM alias_icon_settings
            WHERE mailbox = ? AND alias IN ({placeholders})
        """
        with self._connect() as connection:
            rows = connection.execute(
                query,
                (mailbox.lower(), *(alias.lower() for alias in aliases)),
            ).fetchall()
        return {str(row["alias"]).lower(): str(row["icon_key"]) for row in rows}

    async def set(self, mailbox: str, alias: str, icon_key: str | None) -> None:
        await asyncio.to_thread(self._set, mailbox, alias, icon_key)

    def _set(self, mailbox: str, alias: str, icon_key: str | None) -> None:
        mailbox = mailbox.lower()
        alias = alias.lower()
        with self._connect() as connection:
            if not icon_key or icon_key == "auto":
                connection.execute(
                    "DELETE FROM alias_icon_settings WHERE mailbox = ? AND alias = ?",
                    (mailbox, alias),
                )
                return
            connection.execute(
                """
                INSERT INTO alias_icon_settings (mailbox, alias, icon_key)
                VALUES (?, ?, ?)
                ON CONFLICT(mailbox, alias) DO UPDATE SET icon_key = excluded.icon_key
                """,
                (mailbox, alias, icon_key),
            )


async def _load_ui_state(request: Request) -> dict:
    user = require_user(request)
    domain = mailbox_domain(user)
    settings = request.app.state.settings
    mailcow = request.app.state.mailcow

    try:
        all_aliases = await mailcow.list_aliases()
        domain_details = await mailcow.get_domain(domain)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    primary_alias = next(
        (alias for alias in all_aliases if is_primary_mailbox_alias(alias, user)),
        None,
    )
    catch_all = next(
        (alias for alias in all_aliases if is_mailbox_catch_all(alias, user)),
        None,
    )
    owned = [
        alias
        for alias in all_aliases
        if is_owned_alias(alias, user)
        and (primary_alias is None or alias.id != primary_alias.id)
    ]
    reserved = sorted(
        (alias for alias in owned if alias.is_reserved),
        key=lambda item: item.address,
    )
    assigned_all = sorted(
        (alias for alias in owned if not alias.is_reserved),
        key=lambda item: (item.description.lower(), item.address),
    )

    max_aliases = _as_int(
        domain_details.get("max_num_aliases_for_domain")
        or domain_details.get("aliases")
    )
    aliases_in_domain = _as_int(domain_details.get("aliases_in_domain"), -1)
    if aliases_in_domain < 0:
        aliases_left = _as_int(domain_details.get("aliases_left"), -1)
        if max_aliases > 0 and aliases_left >= 0:
            aliases_in_domain = max(0, max_aliases - aliases_left)
        else:
            aliases_in_domain = sum(
                1 for alias in all_aliases if alias.domain.strip().lower() == domain
            )

    stats_store = getattr(request.app.state, "stats_store", None)
    stats_available = settings.usage_stats and stats_store is not None
    stats_state = None
    stats_error = False
    stats_mode_selection = "inherit"
    stats_confirmation_mode: str | None = None
    usage_stats_visible = False
    usage_stats: dict[str, dict[str, int | None]] = {}
    sender_stats: dict[str, list[dict[str, str | int | bool | None]]] = {}
    unexpected_aliases: set[str] = set()
    ignored_aliases: set[str] = set()

    if stats_available:
        try:
            stats_state = await mailbox_stats_state(settings, mailcow, user)
            usage_stats_visible = stats_state.enabled
            if stats_state.conflict and stats_state.conflict_source is StatsModeSource.MAILBOX:
                stats_mode_selection = "conflict"
            elif stats_state.mailbox_override is not None:
                stats_mode_selection = stats_state.mailbox_override.value

            stored_mode = await stats_store.sender_mode(user)
            stats_confirmation_mode = stored_mode or stats_state.effective.value
            if not stats_state.conflict:
                await stats_store.sync_sender_modes({user: stats_state.effective.value})
        except (MailcowAccessDenied, MailcowError):
            stats_error = True
            stats_state = None
            usage_stats_visible = False

    addresses = [alias.address for alias in [*assigned_all, *reserved]]
    if usage_stats_visible and stats_state is not None and addresses:
        stored_usage = await stats_store.alias_usage(user, addresses)
        for alias in [*assigned_all, *reserved]:
            usage = stored_usage.get(alias.address.lower())
            received_count = usage.received_count if usage is not None else 0
            sent_count = usage.sent_count if usage is not None else 0
            timestamps = (
                []
                if usage is None
                else [
                    value
                    for value in (usage.last_received_at, usage.last_sent_at)
                    if value is not None
                ]
            )
            usage_stats[alias.address.lower()] = {
                "received_count": received_count,
                "sent_count": sent_count,
                "last_used_at": max(timestamps) if timestamps else None,
            }

    if (
        usage_stats_visible
        and stats_state is not None
        and stats_state.sender_detail_enabled
        and addresses
    ):
        stored_senders = await stats_store.sender_usage(user, addresses)
        aliases_by_address = {
            alias.address.lower(): alias for alias in [*assigned_all, *reserved]
        }
        for alias_address, entries in stored_senders.items():
            alias_record = aliases_by_address.get(alias_address)
            if alias_record is None:
                continue
            rows: list[dict[str, str | int | bool | None]] = []
            for entry in entries:
                match_token = sender_match_token(
                    alias_record.address,
                    alias_record.description,
                    entry.sender_domain,
                )
                automatic_expected = match_token is not None
                if entry.manual_expected is None:
                    expected = automatic_expected
                    review_source = "automatic" if automatic_expected else "unreviewed"
                elif entry.manual_expected:
                    expected = True
                    review_source = "manual"
                else:
                    expected = False
                    review_source = "manual-unexpected"

                rows.append(
                    {
                        "sender_key": entry.sender_key,
                        "label": entry.sender_address or entry.sender_domain,
                        "domain": entry.sender_domain,
                        "received_count": entry.received_count,
                        "last_received_at": entry.last_received_at,
                        "expected": expected,
                        "automatic_expected": automatic_expected,
                        "review_source": review_source,
                        "manual_expected": entry.manual_expected,
                        "match_token": match_token,
                    }
                )
            rows.sort(
                key=lambda row: (
                    bool(row["expected"]),
                    -int(row["last_received_at"] or 0),
                    str(row["label"]),
                )
            )
            sender_stats[alias_address] = rows

        from moolias.review_settings import AliasReviewSettingsStore

        ignored_aliases = await AliasReviewSettingsStore(stats_store.path).ignored_aliases(user)
        assigned_addresses = {
            alias.address.lower() for alias in assigned_all if alias.active
        }
        unexpected_aliases = {
            alias_address
            for alias_address, rows in sender_stats.items()
            if alias_address in assigned_addresses
            and alias_address not in ignored_aliases
            and any(not bool(row["expected"]) for row in rows)
        }

    try:
        icon_overrides = await IconPreferenceStore(settings.usage_db_path).get_many(
            user,
            [alias.address for alias in assigned_all],
        )
    except sqlite3.Error:
        icon_overrides = {}
    service_icons = {
        alias.address.lower(): resolve_service_icon(
            alias.address,
            alias.description,
            icon_overrides.get(alias.address.lower()),
        )
        for alias in assigned_all
    }

    total_received = sum(
        int(item.get("received_count") or 0) for item in usage_stats.values()
    )
    total_sent = sum(int(item.get("sent_count") or 0) for item in usage_stats.values())
    recognized_senders = 0
    unrecognized_senders = 0
    recognized_messages = 0
    unrecognized_messages = 0
    source_counts: Counter[str] = Counter()
    for rows in sender_stats.values():
        for row in rows:
            received = int(row["received_count"] or 0)
            domain_name = str(row["domain"] or "").lower()
            if domain_name:
                source_counts[domain_name] += received
            if bool(row.get("automatic_expected")):
                recognized_senders += 1
                recognized_messages += received
            else:
                unrecognized_senders += 1
                unrecognized_messages += received

    def usage_total(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("received_count") or 0) + int(usage.get("sent_count") or 0)

    def last_used(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("last_used_at") or 0)

    recent_aliases = sorted(
        assigned_all,
        key=lambda alias: (last_used(alias), usage_total(alias), alias.address.lower()),
        reverse=True,
    )[:5]
    top_aliases = sorted(
        assigned_all,
        key=lambda alias: (usage_total(alias), last_used(alias), alias.address.lower()),
        reverse=True,
    )[:8]

    used_reserved = [
        alias
        for alias in reserved
        if alias.is_reserved_used
        or usage_total(alias) > 0
    ]
    cutoff = int(time.time()) - 90 * 24 * 60 * 60
    unused_90 = [
        alias
        for alias in assigned_all
        if last_used(alias) > 0 and last_used(alias) < cutoff
    ]
    never_used = [alias for alias in assigned_all if usage_total(alias) == 0]

    collector_health = None
    if stats_available:
        try:
            health = await CollectorHealthStore(stats_store.path).read()
            collector_health = assess_collector_health(
                health,
                poll_interval_seconds=settings.usage_poll_seconds,
                stale_polls=settings.usage_stale_polls,
            ).as_dict()
        except (OSError, sqlite3.Error):
            collector_health = None

    health_actionable = bool(
        collector_health and collector_health.get("state") in ACTIONABLE_HEALTH_STATES
    )
    action_base_count = (
        len(used_reserved)
        + len(unexpected_aliases)
        + len(unused_90)
        + (1 if health_actionable else 0)
    )

    known_sender_total = recognized_senders + unrecognized_senders
    recognition_rate = (
        round(recognized_senders * 100 / known_sender_total)
        if known_sender_total
        else None
    )

    return {
        "user": user,
        "domain": domain,
        "catch_all": catch_all,
        "assigned_all": assigned_all,
        "assigned_total": len(assigned_all),
        "active_total": sum(alias.active for alias in assigned_all),
        "reserved": reserved,
        "used_reserved": used_reserved,
        "primary_alias": primary_alias,
        "csrf_token": ensure_csrf_token(request),
        "mailcow_quota": {
            "used": aliases_in_domain,
            "limit": max_aliases,
            "own": len(owned),
        },
        "stats_available": stats_available,
        "stats_error": stats_error,
        "stats_state": stats_state,
        "stats_mode_selection": stats_mode_selection,
        "stats_confirmation_mode": stats_confirmation_mode,
        "usage_stats_visible": usage_stats_visible,
        "usage_stats": usage_stats,
        "sender_stats": sender_stats,
        "unexpected_aliases": unexpected_aliases,
        "ignored_aliases": ignored_aliases,
        "service_icons": service_icons,
        "icon_catalog": icon_catalog(),
        "icon_overrides": icon_overrides,
        "recent_aliases": recent_aliases,
        "top_aliases": top_aliases,
        "top_sources": source_counts.most_common(8),
        "stats_summary": {
            "received": total_received,
            "sent": total_sent,
            "recognized_senders": recognized_senders,
            "unrecognized_senders": unrecognized_senders,
            "recognized_messages": recognized_messages,
            "unrecognized_messages": unrecognized_messages,
            "recognition_rate": recognition_rate,
            "never_used": len(never_used),
            "last_activity": max(
                (int(item.get("last_used_at") or 0) for item in usage_stats.values()),
                default=0,
            ),
        },
        "action_required": {
            "used_pool": len(used_reserved),
            "unexpected": len(unexpected_aliases),
            "unused_90": len(unused_90),
            "collector": 1 if health_actionable else 0,
            "base_count": action_base_count,
            "collector_state": collector_health.get("state") if collector_health else None,
        },
    }


@router.get("/overview", response_class=HTMLResponse)
async def overview(request: Request):
    state = await _load_ui_state(request)
    return TEMPLATES.TemplateResponse(
        request,
        "overview.html",
        _template_context(request, active_nav="overview", **state),
    )


@router.get("/aliases", response_class=HTMLResponse)
async def aliases_page(
    request: Request,
    q: str = Query(default="", max_length=160),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25),
    status_filter: str = Query(default="all", alias="status"),
    sort: str = Query(default="last_used"),
    direction: str = Query(default="desc"),
):
    state = await _load_ui_state(request)
    if per_page not in PAGE_SIZES:
        per_page = 25
    if status_filter not in STATUS_FILTERS:
        status_filter = "all"
    if sort not in SORT_MODES:
        sort = "last_used"
    if direction not in SORT_DIRECTIONS:
        direction = "desc"

    assigned_all = list(state["assigned_all"])
    unexpected_aliases = state["unexpected_aliases"]
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

    if sort == "most_used":
        sort_key = lambda alias: (usage_total(alias), last_used(alias), alias.address.lower())
    else:
        sort_key = lambda alias: (last_used(alias), usage_total(alias), alias.address.lower())
    filtered.sort(key=sort_key, reverse=direction == "desc")

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


@router.get("/offline-pool", response_class=HTMLResponse)
async def offline_pool(request: Request):
    state = await _load_ui_state(request)
    return TEMPLATES.TemplateResponse(
        request,
        "offline_pool.html",
        _template_context(request, active_nav="pool", **state),
    )


@router.get("/statistics", response_class=HTMLResponse)
async def statistics_page(request: Request):
    state = await _load_ui_state(request)
    return TEMPLATES.TemplateResponse(
        request,
        "statistics.html",
        _template_context(request, active_nav="statistics", **state),
    )


@router.post("/aliases/{alias_id}/icon")
async def update_alias_icon(
    request: Request,
    alias_id: int,
    icon_key: str = Form(...),
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
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alias icon cannot be changed here",
        )

    valid_keys = {"auto", "generic", *(icon.key for icon in icon_catalog())}
    icon_key = icon_key.strip().lower()
    if icon_key not in valid_keys:
        raise HTTPException(status_code=400, detail="Unknown service icon")

    store = IconPreferenceStore(request.app.state.settings.usage_db_path)
    try:
        await store.set(user, alias.address, None if icon_key == "auto" else icon_key)
    except sqlite3.Error as exc:
        raise HTTPException(status_code=503, detail="Icon settings are unavailable") from exc

    effective = resolve_service_icon(
        alias.address,
        alias.description,
        None if icon_key == "auto" else icon_key,
    )
    return {
        "alias": alias.address,
        "override": icon_key,
        "icon": {
            "key": effective.key,
            "label": effective.label,
            "glyph": effective.glyph,
            "tone": effective.tone,
        },
    }
