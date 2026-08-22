from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class UsageEvidenceEvent:
    mailbox: str
    alias: str
    event_at: int


@dataclass(frozen=True, slots=True)
class AliasUsageEvidence:
    first_seen_at: int
    last_seen_at: int
    backfill_seen: bool
    live_seen: bool


@dataclass(frozen=True, slots=True)
class UsageBackfillState:
    completed_at: int
    oldest_history_at: int | None
    newest_history_at: int | None
    history_count: int
    history_limit: int


class UsageEvidenceStore:
    """Persist privacy-preserving proof that an alias has been used."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS alias_usage_evidence (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                backfill_seen INTEGER NOT NULL DEFAULT 0
                    CHECK (backfill_seen IN (0, 1)),
                live_seen INTEGER NOT NULL DEFAULT 0
                    CHECK (live_seen IN (0, 1)),
                PRIMARY KEY (mailbox, alias)
            );

            CREATE INDEX IF NOT EXISTS alias_usage_evidence_mailbox_idx
                ON alias_usage_evidence (mailbox);

            CREATE TABLE IF NOT EXISTS usage_backfill_state (
                mailbox TEXT PRIMARY KEY COLLATE NOCASE,
                completed_at INTEGER NOT NULL,
                oldest_history_at INTEGER,
                newest_history_at INTEGER,
                history_count INTEGER NOT NULL,
                history_limit INTEGER NOT NULL
            );
            """
        )
        return connection

    async def record_events(
        self,
        events: list[UsageEvidenceEvent],
        *,
        source: str,
    ) -> None:
        if not events:
            return
        if source not in {"backfill", "live"}:
            raise ValueError("Usage evidence source must be 'backfill' or 'live'")
        await asyncio.to_thread(self._record_events, events, source)

    def _record_events(self, events: list[UsageEvidenceEvent], source: str) -> None:
        aggregated: dict[tuple[str, str], tuple[int, int]] = {}
        for event in events:
            key = (event.mailbox.strip().lower(), event.alias.strip().lower())
            if not key[0] or not key[1]:
                continue
            current = aggregated.get(key)
            if current is None:
                aggregated[key] = (int(event.event_at), int(event.event_at))
            else:
                aggregated[key] = (
                    min(current[0], int(event.event_at)),
                    max(current[1], int(event.event_at)),
                )

        if not aggregated:
            return

        backfill_seen = 1 if source == "backfill" else 0
        live_seen = 1 if source == "live" else 0
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO alias_usage_evidence (
                    mailbox,
                    alias,
                    first_seen_at,
                    last_seen_at,
                    backfill_seen,
                    live_seen
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mailbox, alias) DO UPDATE SET
                    first_seen_at = MIN(
                        alias_usage_evidence.first_seen_at,
                        excluded.first_seen_at
                    ),
                    last_seen_at = MAX(
                        alias_usage_evidence.last_seen_at,
                        excluded.last_seen_at
                    ),
                    backfill_seen = MAX(
                        alias_usage_evidence.backfill_seen,
                        excluded.backfill_seen
                    ),
                    live_seen = MAX(
                        alias_usage_evidence.live_seen,
                        excluded.live_seen
                    )
                """,
                [
                    (
                        mailbox,
                        alias,
                        first_seen_at,
                        last_seen_at,
                        backfill_seen,
                        live_seen,
                    )
                    for (mailbox, alias), (first_seen_at, last_seen_at) in aggregated.items()
                ],
            )

    async def alias_evidence(
        self,
        mailbox: str,
        aliases: list[str],
    ) -> dict[str, AliasUsageEvidence]:
        if not aliases:
            return {}
        return await asyncio.to_thread(self._alias_evidence, mailbox, aliases)

    def _alias_evidence(
        self,
        mailbox: str,
        aliases: list[str],
    ) -> dict[str, AliasUsageEvidence]:
        placeholders = ",".join("?" for _ in aliases)
        params = [mailbox.lower(), *(alias.lower() for alias in aliases)]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT
                    alias,
                    first_seen_at,
                    last_seen_at,
                    backfill_seen,
                    live_seen
                FROM alias_usage_evidence
                WHERE mailbox = ? AND alias IN ({placeholders})
                """,
                params,
            ).fetchall()
            usage_rows = connection.execute(
                f"""
                SELECT
                    alias,
                    received_count,
                    sent_count,
                    last_received_at,
                    last_sent_at
                FROM alias_usage
                WHERE mailbox = ?
                    AND alias IN ({placeholders})
                    AND (received_count > 0 OR sent_count > 0)
                """,
                params,
            ).fetchall()

        evidence = {
            str(row["alias"]).lower(): AliasUsageEvidence(
                first_seen_at=int(row["first_seen_at"]),
                last_seen_at=int(row["last_seen_at"]),
                backfill_seen=bool(row["backfill_seen"]),
                live_seen=bool(row["live_seen"]),
            )
            for row in rows
        }
        for row in usage_rows:
            alias = str(row["alias"]).lower()
            timestamps = [
                int(value)
                for value in (row["last_received_at"], row["last_sent_at"])
                if value is not None
            ]
            if not timestamps:
                continue
            seen_at = max(timestamps)
            current = evidence.get(alias)
            if current is None:
                evidence[alias] = AliasUsageEvidence(
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    backfill_seen=False,
                    live_seen=True,
                )
            elif seen_at > current.last_seen_at:
                evidence[alias] = AliasUsageEvidence(
                    first_seen_at=current.first_seen_at,
                    last_seen_at=seen_at,
                    backfill_seen=current.backfill_seen,
                    live_seen=True,
                )
        return evidence

    async def pending_backfills(
        self,
        mailboxes: set[str],
        *,
        history_limit: int,
    ) -> set[str]:
        if not mailboxes:
            return set()
        return await asyncio.to_thread(
            self._pending_backfills,
            mailboxes,
            int(history_limit),
        )

    def _pending_backfills(self, mailboxes: set[str], history_limit: int) -> set[str]:
        normalized = {mailbox.lower() for mailbox in mailboxes}
        placeholders = ",".join("?" for _ in normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT mailbox, history_limit
                FROM usage_backfill_state
                WHERE mailbox IN ({placeholders})
                """,
                tuple(normalized),
            ).fetchall()
        completed = {
            str(row["mailbox"]).lower(): int(row["history_limit"])
            for row in rows
        }
        return {
            mailbox
            for mailbox in normalized
            if mailbox not in completed or completed[mailbox] < history_limit
        }

    async def complete_backfills(
        self,
        mailboxes: set[str],
        *,
        oldest_history_at: int | None,
        newest_history_at: int | None,
        history_count: int,
        history_limit: int,
        completed_at: int | None = None,
    ) -> None:
        if not mailboxes:
            return
        timestamp = int(time.time()) if completed_at is None else int(completed_at)
        await asyncio.to_thread(
            self._complete_backfills,
            mailboxes,
            oldest_history_at,
            newest_history_at,
            int(history_count),
            int(history_limit),
            timestamp,
        )

    def _complete_backfills(
        self,
        mailboxes: set[str],
        oldest_history_at: int | None,
        newest_history_at: int | None,
        history_count: int,
        history_limit: int,
        completed_at: int,
    ) -> None:
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO usage_backfill_state (
                    mailbox,
                    completed_at,
                    oldest_history_at,
                    newest_history_at,
                    history_count,
                    history_limit
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(mailbox) DO UPDATE SET
                    completed_at = excluded.completed_at,
                    oldest_history_at = excluded.oldest_history_at,
                    newest_history_at = excluded.newest_history_at,
                    history_count = excluded.history_count,
                    history_limit = excluded.history_limit
                """,
                [
                    (
                        mailbox.lower(),
                        completed_at,
                        oldest_history_at,
                        newest_history_at,
                        history_count,
                        history_limit,
                    )
                    for mailbox in mailboxes
                ],
            )

    async def backfill_state(self, mailbox: str) -> UsageBackfillState | None:
        return await asyncio.to_thread(self._backfill_state, mailbox)

    def _backfill_state(self, mailbox: str) -> UsageBackfillState | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT
                    completed_at,
                    oldest_history_at,
                    newest_history_at,
                    history_count,
                    history_limit
                FROM usage_backfill_state
                WHERE mailbox = ?
                """,
                (mailbox.lower(),),
            ).fetchone()
        if row is None:
            return None
        return UsageBackfillState(
            completed_at=int(row["completed_at"]),
            oldest_history_at=(
                int(row["oldest_history_at"])
                if row["oldest_history_at"] is not None
                else None
            ),
            newest_history_at=(
                int(row["newest_history_at"])
                if row["newest_history_at"] is not None
                else None
            ),
            history_count=int(row["history_count"]),
            history_limit=int(row["history_limit"]),
        )

    async def clear_mailboxes(self, mailboxes: set[str]) -> None:
        if not mailboxes:
            return
        await asyncio.to_thread(self._clear_mailboxes, mailboxes)

    def _clear_mailboxes(self, mailboxes: set[str]) -> None:
        normalized = {mailbox.lower() for mailbox in mailboxes}
        placeholders = ",".join("?" for _ in normalized)
        params = tuple(normalized)
        with self._connect() as connection:
            connection.execute(
                f"DELETE FROM alias_usage_evidence WHERE mailbox IN ({placeholders})",
                params,
            )
            connection.execute(
                f"DELETE FROM usage_backfill_state WHERE mailbox IN ({placeholders})",
                params,
            )
