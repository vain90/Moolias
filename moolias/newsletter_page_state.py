from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request

from moolias.aliases import (
    is_owned_alias,
    is_primary_mailbox_alias,
    mailbox_domain,
)
from moolias.mailcow import MailcowError
from moolias.security import ensure_csrf_token, require_user
from moolias.stats_mode import StatsModeSource, resolve_stats_mode


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


async def load_newsletter_page_state(request: Request) -> dict:
    user = require_user(request)
    domain = mailbox_domain(user)
    settings = request.app.state.settings
    mailcow = request.app.state.mailcow
    mailbox_details = getattr(request.state, "mailbox", None)

    try:
        if mailbox_details is None:
            all_aliases, domain_details, mailbox_details = await asyncio.gather(
                mailcow.list_aliases(),
                mailcow.get_domain(domain),
                mailcow.get_mailbox(user),
            )
        else:
            all_aliases, domain_details = await asyncio.gather(
                mailcow.list_aliases(),
                mailcow.get_domain(domain),
            )
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    primary_alias = next(
        (alias for alias in all_aliases if is_primary_mailbox_alias(alias, user)),
        None,
    )
    owned = [
        alias
        for alias in all_aliases
        if is_owned_alias(alias, user)
        and (primary_alias is None or alias.id != primary_alias.id)
    ]
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

    if stats_available:
        stats_state = resolve_stats_mode(
            mailbox_details.get("tags"),
            domain_details.get("tags"),
            settings.usage_tag,
        )
        if stats_state.conflict and stats_state.conflict_source is StatsModeSource.MAILBOX:
            stats_mode_selection = "conflict"
        elif stats_state.mailbox_override is not None:
            stats_mode_selection = stats_state.mailbox_override.value

        stored_mode = await stats_store.sender_mode(user)
        stats_confirmation_mode = stored_mode or stats_state.effective.value
        if not stats_state.conflict:
            await stats_store.sync_sender_modes({user: stats_state.effective.value})

    return {
        "user": user,
        "domain": domain,
        "assigned_all": assigned_all,
        "csrf_token": ensure_csrf_token(request),
        "mailcow_quota": {
            "used": aliases_in_domain,
            "limit": max_aliases,
            "own": len(owned),
        },
        "mailcow_aliases": all_aliases,
        "mailbox_details": mailbox_details,
        "stats_available": stats_available,
        "stats_error": stats_error,
        "stats_state": stats_state,
        "stats_mode_selection": stats_mode_selection,
        "stats_confirmation_mode": stats_confirmation_mode,
        "usage_stats_visible": bool(stats_state and stats_state.enabled),
    }
