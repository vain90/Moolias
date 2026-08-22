from __future__ import annotations

import asyncio
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, Request

from moolias.aliases import is_owned_alias, is_primary_mailbox_alias
from moolias.collector_health import (
    LOW_HEADROOM_PERCENT,
    CollectorHealthStore,
    assess_collector_health,
)
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf
from moolias.sender_protection import router as sender_protection_router
from moolias.stats_mode import StatsMode
from moolias.usage import mailbox_stats_state

router = APIRouter()
router.include_router(sender_protection_router)


class AliasReviewSettingsStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sender_alias_settings (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                ignore_unexpected INTEGER NOT NULL DEFAULT 0
                    CHECK (ignore_unexpected IN (0, 1)),
                PRIMARY KEY (mailbox, alias)
            )
            """
        )
        return connection

    async def ignored_aliases(self, mailbox: str) -> set[str]:
        return await asyncio.to_thread(self._ignored_aliases, mailbox)

    def _ignored_aliases(self, mailbox: str) -> set[str]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT alias
                FROM sender_alias_settings
                WHERE mailbox = ? AND ignore_unexpected = 1
                """,
                (mailbox.lower(),),
            ).fetchall()
        return {str(row["alias"]).lower() for row in rows}

    async def set_ignore_unexpected(
        self,
        mailbox: str,
        alias: str,
        ignored: bool,
    ) -> None:
        await asyncio.to_thread(
            self._set_ignore_unexpected,
            mailbox,
            alias,
            ignored,
        )

    def _set_ignore_unexpected(
        self,
        mailbox: str,
        alias: str,
        ignored: bool,
    ) -> None:
        mailbox = mailbox.lower()
        alias = alias.lower()
        with self._connect() as connection:
            if ignored:
                connection.execute(
                    """
                    INSERT INTO sender_alias_settings (
                        mailbox,
                        alias,
                        ignore_unexpected
                    ) VALUES (?, ?, 1)
                    ON CONFLICT(mailbox, alias) DO UPDATE SET
                        ignore_unexpected = 1
                    """,
                    (mailbox, alias),
                )
            else:
                connection.execute(
                    """
                    DELETE FROM sender_alias_settings
                    WHERE mailbox = ? AND alias = ?
                    """,
                    (mailbox, alias),
                )


def _store(request: Request) -> AliasReviewSettingsStore | None:
    stats_store = getattr(request.app.state, "stats_store", None)
    if stats_store is None:
        return None
    return AliasReviewSettingsStore(stats_store.path)


@router.get("/aliases/review-settings")
async def get_alias_review_settings(request: Request):
    user = require_user(request)
    store = _store(request)
    if store is None:
        return {"ignored_unexpected": []}
    ignored = await store.ignored_aliases(user)
    return {"ignored_unexpected": sorted(ignored)}


@router.get("/aliases/collector-health")
async def get_collector_health(request: Request):
    require_user(request)
    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    if not settings.usage_stats or stats_store is None:
        return {"enabled": False, "state": "off"}

    health = await CollectorHealthStore(stats_store.path).read()
    view = assess_collector_health(
        health,
        poll_interval_seconds=settings.usage_poll_seconds,
        stale_polls=settings.usage_stale_polls,
    )
    payload = view.as_dict()
    payload.update(
        {
            "enabled": True,
            "stale_polls": settings.usage_stale_polls,
            "low_headroom_percent": LOW_HEADROOM_PERCENT,
        }
    )
    if payload["poll_interval_seconds"] is None:
        payload["poll_interval_seconds"] = settings.usage_poll_seconds
    if payload["history_limit"] is None:
        payload["history_limit"] = settings.usage_history_count
    return payload


@router.post("/aliases/{alias_id}/unexpected-monitoring")
async def update_unexpected_monitoring(
    request: Request,
    alias_id: int,
    ignored: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    store = _store(request)
    if store is None:
        raise HTTPException(status_code=409, detail="Usage statistics are disabled")

    alias = await request.app.state.mailcow.get_alias(alias_id)
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(status_code=403, detail="Alias cannot be managed here")

    await store.set_ignore_unexpected(user, alias.address, ignored)
    return {
        "alias": alias.address,
        "ignored": ignored,
    }


@router.post("/aliases/{alias_id}/sender-domain-expectation")
async def set_sender_domain_expectation(
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

    alias = await request.app.state.mailcow.get_alias(alias_id)
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
        raise HTTPException(status_code=502, detail="Statistics state is unavailable") from exc
    if state.conflict or state.effective is not StatsMode.FULL:
        raise HTTPException(
            status_code=409,
            detail="Domain expectation is only available in full statistics mode",
        )

    stored = await stats_store.sender_usage(user, [alias.address])
    sender = next(
        (
            entry
            for entry in stored.get(alias.address.lower(), [])
            if entry.sender_key == sender_key and entry.sender_address is not None
        ),
        None,
    )
    if sender is None:
        raise HTTPException(status_code=404, detail="Sender statistic does not exist")

    await stats_store.set_sender_expectation(
        user,
        alias.address,
        sender.sender_domain,
        True,
    )
    return {
        "alias": alias.address,
        "domain": sender.sender_domain,
        "expected": True,
    }


# Keep these imports late to avoid a module cycle: ui.py uses AliasReviewSettingsStore.
from moolias.pool_ui import router as pool_ui_router  # noqa: E402
from moolias.ui import router as ui_router  # noqa: E402

router.include_router(pool_ui_router)
router.include_router(ui_router)
