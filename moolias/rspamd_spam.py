from __future__ import annotations

import asyncio
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from moolias.mailcow import MailcowError
from moolias.stats import SenderEvent
from moolias.stats_history import StatsHistoryStore
from moolias.stats_mode import StatsMode
from moolias.usage import (
    UsageCollector,
    _event_key,
    _event_timestamp,
    _normalise_recipients,
    _sender_identity,
)

SPAM_ACTIONS = frozenset({"add header", "rewrite subject", "probable spam"})
_SCORE_PATTERN = re.compile(r"[-+]?\d+(?:[.,]\d+)?")


@dataclass(frozen=True, slots=True)
class SpamEvidenceEvent:
    event_key: str
    mailbox: str
    alias: str
    detail_level: str
    sender_key: str
    event_at: int
    score: float | None


@dataclass(frozen=True, slots=True)
class SenderSpamEvidence:
    spam_count: int
    max_score: float | None
    last_spam_at: int | None


class RspamdSpamStore:
    """Persist only compact Rspamd spam evidence needed for sender review."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS sender_spam_evidence (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                detail_level TEXT NOT NULL CHECK (detail_level IN ('domain', 'full')),
                sender_key TEXT NOT NULL COLLATE NOCASE,
                spam_count INTEGER NOT NULL DEFAULT 0,
                max_score REAL,
                last_spam_at INTEGER,
                PRIMARY KEY (mailbox, alias, detail_level, sender_key)
            );

            CREATE INDEX IF NOT EXISTS sender_spam_evidence_mailbox_alias_idx
                ON sender_spam_evidence (mailbox, alias, detail_level);

            CREATE TABLE IF NOT EXISTS sender_spam_processed (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                detail_level TEXT NOT NULL CHECK (detail_level IN ('domain', 'full')),
                event_key TEXT NOT NULL,
                event_at INTEGER NOT NULL,
                PRIMARY KEY (mailbox, detail_level, event_key)
            );

            CREATE INDEX IF NOT EXISTS sender_spam_processed_event_at_idx
                ON sender_spam_processed (event_at);

            CREATE TABLE IF NOT EXISTS sender_spam_bootstrap (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                detail_level TEXT NOT NULL CHECK (detail_level IN ('domain', 'full')),
                live_started_at INTEGER NOT NULL,
                history_oldest_at INTEGER,
                history_completed_at INTEGER,
                PRIMARY KEY (mailbox, detail_level)
            );
            """
        )
        return connection

    async def record_events(self, events: list[SpamEvidenceEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_events, events)

    def _record_events(self, events: list[SpamEvidenceEvent]) -> int:
        recorded = 0
        with self._connect() as connection:
            for event in events:
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO sender_spam_processed (
                        mailbox, detail_level, event_key, event_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        event.mailbox.lower(),
                        event.detail_level,
                        event.event_key,
                        int(event.event_at),
                    ),
                )
                if inserted.rowcount != 1:
                    continue

                connection.execute(
                    """
                    INSERT INTO sender_spam_evidence (
                        mailbox,
                        alias,
                        detail_level,
                        sender_key,
                        spam_count,
                        max_score,
                        last_spam_at
                    ) VALUES (?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(mailbox, alias, detail_level, sender_key) DO UPDATE SET
                        spam_count = sender_spam_evidence.spam_count + 1,
                        max_score = CASE
                            WHEN excluded.max_score IS NULL
                                THEN sender_spam_evidence.max_score
                            WHEN sender_spam_evidence.max_score IS NULL
                                THEN excluded.max_score
                            ELSE MAX(sender_spam_evidence.max_score, excluded.max_score)
                        END,
                        last_spam_at = MAX(
                            COALESCE(sender_spam_evidence.last_spam_at, excluded.last_spam_at),
                            excluded.last_spam_at
                        )
                    """,
                    (
                        event.mailbox.lower(),
                        event.alias.lower(),
                        event.detail_level,
                        event.sender_key.lower(),
                        event.score,
                        int(event.event_at),
                    ),
                )
                recorded += 1
        return recorded

    async def evidence(
        self,
        mailbox: str,
        aliases: list[str],
        *,
        level: StatsMode,
    ) -> dict[str, dict[str, SenderSpamEvidence]]:
        if not aliases or level not in {StatsMode.DOMAIN, StatsMode.FULL}:
            return {}
        return await asyncio.to_thread(self._evidence, mailbox, aliases, level)

    def _evidence(
        self,
        mailbox: str,
        aliases: list[str],
        level: StatsMode,
    ) -> dict[str, dict[str, SenderSpamEvidence]]:
        detail_level = "full" if level is StatsMode.FULL else "domain"
        placeholders = ",".join("?" for _ in aliases)
        params = [mailbox.lower(), detail_level, *(alias.lower() for alias in aliases)]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT alias, sender_key, spam_count, max_score, last_spam_at
                FROM sender_spam_evidence
                WHERE mailbox = ?
                  AND detail_level = ?
                  AND alias IN ({placeholders})
                """,
                params,
            ).fetchall()

        result: dict[str, dict[str, SenderSpamEvidence]] = {}
        for row in rows:
            alias = str(row["alias"]).lower()
            result.setdefault(alias, {})[str(row["sender_key"]).lower()] = SenderSpamEvidence(
                spam_count=int(row["spam_count"]),
                max_score=(float(row["max_score"]) if row["max_score"] is not None else None),
                last_spam_at=(
                    int(row["last_spam_at"]) if row["last_spam_at"] is not None else None
                ),
            )
        return result

    async def sync_mode(self, mailbox: str, mode: StatsMode) -> None:
        await asyncio.to_thread(self._sync_mode, mailbox, mode)

    def _sync_mode(self, mailbox: str, mode: StatsMode) -> None:
        with self._connect() as connection:
            self._prune_for_mode(connection, mailbox.lower(), mode)

    async def sync_from_sender_mode_state(self) -> None:
        await asyncio.to_thread(self._sync_from_sender_mode_state)

    def _sync_from_sender_mode_state(self) -> None:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT mailbox, mode FROM sender_mode_state"
            ).fetchall()
            for row in rows:
                self._prune_for_mode(
                    connection,
                    str(row["mailbox"]).lower(),
                    StatsMode(str(row["mode"])),
                )

    @staticmethod
    def _prune_for_mode(
        connection: sqlite3.Connection,
        mailbox: str,
        mode: StatsMode,
    ) -> None:
        if mode is StatsMode.FULL:
            return
        levels = ("full",) if mode is StatsMode.DOMAIN else ("domain", "full")
        placeholders = ",".join("?" for _ in levels)
        params = [mailbox, *levels]
        connection.execute(
            f"""
            DELETE FROM sender_spam_evidence
            WHERE mailbox = ? AND detail_level IN ({placeholders})
            """,
            params,
        )
        connection.execute(
            f"""
            DELETE FROM sender_spam_processed
            WHERE mailbox = ? AND detail_level IN ({placeholders})
            """,
            params,
        )
        connection.execute(
            f"""
            DELETE FROM sender_spam_bootstrap
            WHERE mailbox = ? AND detail_level IN ({placeholders})
            """,
            params,
        )

    async def bootstrap_matches(
        self,
        mailbox: str,
        level: StatsMode,
        *,
        live_started_at: int,
        history_oldest_at: int | None,
        history_completed_at: int | None,
    ) -> bool:
        return await asyncio.to_thread(
            self._bootstrap_matches,
            mailbox,
            level,
            live_started_at,
            history_oldest_at,
            history_completed_at,
        )

    def _bootstrap_matches(
        self,
        mailbox: str,
        level: StatsMode,
        live_started_at: int,
        history_oldest_at: int | None,
        history_completed_at: int | None,
    ) -> bool:
        detail_level = "full" if level is StatsMode.FULL else "domain"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT live_started_at, history_oldest_at, history_completed_at
                FROM sender_spam_bootstrap
                WHERE mailbox = ? AND detail_level = ?
                """,
                (mailbox.lower(), detail_level),
            ).fetchone()
        if row is None:
            return False
        return (
            int(row["live_started_at"]) == int(live_started_at)
            and (
                int(row["history_oldest_at"])
                if row["history_oldest_at"] is not None
                else None
            )
            == history_oldest_at
            and (
                int(row["history_completed_at"])
                if row["history_completed_at"] is not None
                else None
            )
            == history_completed_at
        )

    async def mark_bootstrap(
        self,
        mailbox: str,
        level: StatsMode,
        *,
        live_started_at: int,
        history_oldest_at: int | None,
        history_completed_at: int | None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_bootstrap,
            mailbox,
            level,
            live_started_at,
            history_oldest_at,
            history_completed_at,
        )

    def _mark_bootstrap(
        self,
        mailbox: str,
        level: StatsMode,
        live_started_at: int,
        history_oldest_at: int | None,
        history_completed_at: int | None,
    ) -> None:
        detail_level = "full" if level is StatsMode.FULL else "domain"
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO sender_spam_bootstrap (
                    mailbox,
                    detail_level,
                    live_started_at,
                    history_oldest_at,
                    history_completed_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(mailbox, detail_level) DO UPDATE SET
                    live_started_at = excluded.live_started_at,
                    history_oldest_at = excluded.history_oldest_at,
                    history_completed_at = excluded.history_completed_at
                """,
                (
                    mailbox.lower(),
                    detail_level,
                    int(live_started_at),
                    history_oldest_at,
                    history_completed_at,
                ),
            )


def rspamd_score(item: dict[str, Any]) -> float | None:
    value = item.get("score")
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = _SCORE_PATTERN.search(str(value))
        if match is None:
            return None
        try:
            return float(match.group(0).replace(",", "."))
        except ValueError:
            return None


def _spam_action(item: dict[str, Any]) -> bool:
    return str(item.get("action") or "").strip().lower() in SPAM_ACTIONS


def spam_events_from_captured_senders(
    history: list[dict[str, Any]],
    sender_events: list[SenderEvent],
) -> list[SpamEvidenceEvent]:
    captured = {event.event_key: event for event in sender_events}
    if not captured:
        return []

    result: list[SpamEvidenceEvent] = []
    for item in history:
        if not _spam_action(item):
            continue
        event_at = _event_timestamp(item)
        if event_at is None:
            continue
        score = rspamd_score(item)
        for alias in _normalise_recipients(item.get("rcpt_smtp")):
            source_key = _event_key("sender-detail", item, alias, event_at)
            sender = captured.get(source_key)
            if sender is None:
                continue
            result.append(
                SpamEvidenceEvent(
                    event_key=_event_key("rspamd-spam-domain", item, alias, event_at),
                    mailbox=sender.mailbox,
                    alias=sender.alias,
                    detail_level="domain",
                    sender_key=sender.sender_domain,
                    event_at=event_at,
                    score=score,
                )
            )
            if sender.sender_address is not None:
                result.append(
                    SpamEvidenceEvent(
                        event_key=_event_key("rspamd-spam-full", item, alias, event_at),
                        mailbox=sender.mailbox,
                        alias=sender.alias,
                        detail_level="full",
                        sender_key=sender.sender_address,
                        event_at=event_at,
                        score=score,
                    )
                )
    return result


def _allowed_history_start(coverage) -> int:
    if coverage.completed_at is not None and coverage.history_oldest_at is not None:
        return min(coverage.live_started_at, coverage.history_oldest_at)
    return coverage.live_started_at


def spam_events_from_history(
    history: list[dict[str, Any]],
    aliases: list[str],
    mailbox: str,
    coverage: dict[StatsMode, Any],
    levels: set[StatsMode],
) -> list[SpamEvidenceEvent]:
    alias_set = {alias.lower() for alias in aliases}
    result: list[SpamEvidenceEvent] = []
    for item in history:
        if not _spam_action(item):
            continue
        event_at = _event_timestamp(item)
        sender_identity = _sender_identity(item)
        if event_at is None or sender_identity is None:
            continue
        sender_address, sender_domain = sender_identity
        score = rspamd_score(item)
        for alias in _normalise_recipients(item.get("rcpt_smtp")).intersection(alias_set):
            if StatsMode.DOMAIN in levels:
                domain_coverage = coverage.get(StatsMode.DOMAIN)
                if (
                    domain_coverage is not None
                    and event_at >= _allowed_history_start(domain_coverage)
                ):
                    result.append(
                        SpamEvidenceEvent(
                            event_key=_event_key(
                                "rspamd-spam-domain", item, alias, event_at
                            ),
                            mailbox=mailbox,
                            alias=alias,
                            detail_level="domain",
                            sender_key=sender_domain,
                            event_at=event_at,
                            score=score,
                        )
                    )
            if StatsMode.FULL in levels:
                full_coverage = coverage.get(StatsMode.FULL)
                if (
                    full_coverage is not None
                    and event_at >= _allowed_history_start(full_coverage)
                ):
                    result.append(
                        SpamEvidenceEvent(
                            event_key=_event_key("rspamd-spam-full", item, alias, event_at),
                            mailbox=mailbox,
                            alias=alias,
                            detail_level="full",
                            sender_key=sender_address,
                            event_at=event_at,
                            score=score,
                        )
                    )
    return result


async def _bootstrap_available_history(request, state: dict, store: RspamdSpamStore) -> None:
    stats_state = state.get("stats_state")
    if stats_state is None or stats_state.effective not in {StatsMode.DOMAIN, StatsMode.FULL}:
        return

    mailbox = str(state["user"]).lower()
    history_store = StatsHistoryStore(request.app.state.stats_store.path)
    coverage = await history_store.coverage(mailbox)
    levels = {StatsMode.DOMAIN}
    if stats_state.effective is StatsMode.FULL:
        levels.add(StatsMode.FULL)

    pending_levels: set[StatsMode] = set()
    for level in levels:
        item = coverage.get(level)
        if item is None:
            continue
        history_oldest_at = item.history_oldest_at if item.completed_at is not None else None
        history_completed_at = item.completed_at
        if not await store.bootstrap_matches(
            mailbox,
            level,
            live_started_at=item.live_started_at,
            history_oldest_at=history_oldest_at,
            history_completed_at=history_completed_at,
        ):
            pending_levels.add(level)

    if not pending_levels:
        return

    aliases = [
        alias.address
        for alias in [*state.get("assigned_all", []), *state.get("reserved", [])]
    ]
    history = await request.app.state.mailcow.get_rspamd_history(
        request.app.state.settings.usage_history_count
    )
    await store.record_events(
        spam_events_from_history(history, aliases, mailbox, coverage, pending_levels)
    )

    for level in pending_levels:
        item = coverage[level]
        await store.mark_bootstrap(
            mailbox,
            level,
            live_started_at=item.live_started_at,
            history_oldest_at=(
                item.history_oldest_at if item.completed_at is not None else None
            ),
            history_completed_at=item.completed_at,
        )


def apply_spam_evidence_to_state(
    state: dict,
    evidence: dict[str, dict[str, SenderSpamEvidence]],
) -> dict:
    sender_stats = state.get("sender_stats", {})
    for alias, rows in sender_stats.items():
        alias_evidence = evidence.get(str(alias).lower(), {})
        for row in rows:
            sender_key = str(row.get("sender_key") or "").lower()
            spam = alias_evidence.get(sender_key)
            spam_count = spam.spam_count if spam is not None else 0
            row["spam_count"] = spam_count
            row["max_spam_score"] = spam.max_score if spam is not None else None
            row["last_spam_at"] = spam.last_spam_at if spam is not None else None
            row["rspamd_spam"] = spam_count > 0

            automatic_match = row.get("match_token") is not None
            automatic_expected = automatic_match and spam_count == 0
            row["automatic_expected"] = automatic_expected
            manual_expected = row.get("manual_expected")
            if manual_expected is True:
                row["expected"] = True
                row["review_source"] = "manual"
            elif manual_expected is False:
                row["expected"] = False
                row["review_source"] = "manual-unexpected"
            elif spam_count:
                row["expected"] = False
                row["review_source"] = "rspamd-spam"
            elif automatic_expected:
                row["expected"] = True
                row["review_source"] = "automatic"
            else:
                row["expected"] = False
                row["review_source"] = "unreviewed"

        rows.sort(
            key=lambda row: (
                bool(row.get("expected")),
                -int(row.get("last_received_at") or 0),
                str(row.get("label") or ""),
            )
        )

    assigned_addresses = {
        alias.address.lower()
        for alias in state.get("assigned_all", [])
        if alias.active
    }
    ignored_aliases = set(state.get("ignored_aliases", set()))
    unexpected_aliases = {
        alias
        for alias, rows in sender_stats.items()
        if alias in assigned_addresses
        and alias not in ignored_aliases
        and any(not bool(row.get("expected")) for row in rows)
    }
    state["unexpected_aliases"] = unexpected_aliases

    recognized_senders = 0
    unrecognized_senders = 0
    recognized_messages = 0
    unrecognized_messages = 0
    for rows in sender_stats.values():
        for row in rows:
            received = int(row.get("received_count") or 0)
            if bool(row.get("expected")):
                recognized_senders += 1
                recognized_messages += received
            else:
                unrecognized_senders += 1
                unrecognized_messages += received

    known_sender_total = recognized_senders + unrecognized_senders
    summary = state.get("stats_summary", {})
    summary.update(
        {
            "recognized_senders": recognized_senders,
            "unrecognized_senders": unrecognized_senders,
            "recognized_messages": recognized_messages,
            "unrecognized_messages": unrecognized_messages,
            "recognition_rate": (
                round(recognized_senders * 100 / known_sender_total)
                if known_sender_total
                else None
            ),
        }
    )
    state["stats_summary"] = summary

    action_required = state.get("action_required", {})
    action_required["unexpected"] = len(unexpected_aliases)
    action_required["base_count"] = (
        int(action_required.get("used_pool") or 0)
        + len(unexpected_aliases)
        + int(action_required.get("unused_90") or 0)
        + int(action_required.get("collector") or 0)
    )
    state["action_required"] = action_required
    return state


async def enrich_ui_state_with_rspamd_spam(request, state: dict) -> dict:
    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    stats_state = state.get("stats_state")
    if (
        not settings.usage_stats
        or stats_store is None
        or stats_state is None
        or stats_state.conflict
        or stats_state.effective not in {StatsMode.DOMAIN, StatsMode.FULL}
    ):
        return state

    mailbox = str(state["user"]).lower()
    store = RspamdSpamStore(stats_store.path)
    await store.sync_mode(mailbox, stats_state.effective)
    try:
        await _bootstrap_available_history(request, state, store)
    except MailcowError:
        state["rspamd_spam_history_error"] = True

    aliases = [
        alias.address
        for alias in [*state.get("assigned_all", []), *state.get("reserved", [])]
    ]
    evidence = await store.evidence(
        mailbox,
        aliases,
        level=stats_state.effective,
    )
    return apply_spam_evidence_to_state(state, evidence)


def install_rspamd_spam_collection() -> None:
    current = UsageCollector.collect_once
    if getattr(current, "_moolias_rspamd_spam", False):
        return

    async def collect_once_with_rspamd_spam(self: UsageCollector) -> int:
        captured: list[SenderEvent] = []
        original_record_senders = self.store.record_senders
        had_override = "record_senders" in self.store.__dict__
        previous_override = self.store.__dict__.get("record_senders")

        async def capture_sender_events(events: list[SenderEvent]) -> int:
            captured.extend(events)
            return await original_record_senders(events)

        self.store.record_senders = capture_sender_events
        try:
            recorded = await current(self)
        finally:
            if had_override:
                self.store.record_senders = previous_override
            else:
                self.store.__dict__.pop("record_senders", None)

        store = RspamdSpamStore(self.store.path)
        await store.sync_from_sender_mode_state()
        history = self._last_history
        if isinstance(history, list) and captured:
            await store.record_events(
                spam_events_from_captured_senders(history, captured)
            )
        return recorded

    collect_once_with_rspamd_spam._moolias_rspamd_spam = True
    UsageCollector.collect_once = collect_once_with_rspamd_spam
