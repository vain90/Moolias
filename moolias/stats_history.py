from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from moolias.stats import AliasUsage, SenderUsage
from moolias.stats_mode import StatsMode, stats_mode_rank

LEVELS = (StatsMode.BASIC, StatsMode.DOMAIN, StatsMode.FULL)


@dataclass(frozen=True, slots=True)
class HistoricalUsageEvent:
    event_key: str
    mailbox: str
    alias: str
    kind: str
    event_at: int


@dataclass(frozen=True, slots=True)
class HistoricalSenderEvent:
    event_key: str
    mailbox: str
    alias: str
    sender_domain: str
    sender_address: str | None
    level: StatsMode
    event_at: int


@dataclass(frozen=True, slots=True)
class HistoryBackfillRequest:
    mailbox: str
    target_mode: StatsMode
    requested_at: int


@dataclass(frozen=True, slots=True)
class HistoryCoverage:
    level: StatsMode
    live_started_at: int
    history_oldest_at: int | None
    completed_at: int | None
    history_count: int | None
    history_limit: int | None

    @property
    def start_at(self) -> int:
        if self.history_oldest_at is None:
            return self.live_started_at
        return min(self.live_started_at, self.history_oldest_at)


class StatsHistoryStore:
    """Stores opt-in historical statistics separately from live counters.

    Historical aggregates stop at the live start of their respective detail level.
    This keeps Basic, Domain and Full coverage independent and prevents mode upgrades
    from making older low-detail data look as if it had always been collected at the
    higher detail level.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS stats_history_level_state (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                level TEXT NOT NULL,
                live_started_at INTEGER NOT NULL,
                PRIMARY KEY (mailbox, level)
            );

            CREATE TABLE IF NOT EXISTS stats_history_requests (
                mailbox TEXT PRIMARY KEY COLLATE NOCASE,
                target_mode TEXT NOT NULL,
                requested_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS stats_history_coverage (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                level TEXT NOT NULL,
                history_oldest_at INTEGER,
                completed_at INTEGER NOT NULL,
                history_count INTEGER NOT NULL,
                history_limit INTEGER NOT NULL,
                PRIMARY KEY (mailbox, level)
            );

            CREATE TABLE IF NOT EXISTS stats_history_processed (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                level TEXT NOT NULL,
                event_key TEXT NOT NULL,
                event_at INTEGER NOT NULL,
                PRIMARY KEY (mailbox, level, event_key)
            );

            CREATE INDEX IF NOT EXISTS stats_history_processed_event_at_idx
                ON stats_history_processed (event_at);

            CREATE TABLE IF NOT EXISTS stats_history_alias_usage (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                received_count INTEGER NOT NULL DEFAULT 0,
                sent_count INTEGER NOT NULL DEFAULT 0,
                last_received_at INTEGER,
                last_sent_at INTEGER,
                PRIMARY KEY (mailbox, alias)
            );

            CREATE TABLE IF NOT EXISTS stats_history_sender_domain (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                sender_domain TEXT NOT NULL COLLATE NOCASE,
                received_count INTEGER NOT NULL DEFAULT 0,
                last_received_at INTEGER,
                PRIMARY KEY (mailbox, alias, sender_domain)
            );

            CREATE TABLE IF NOT EXISTS stats_history_sender_full (
                mailbox TEXT NOT NULL COLLATE NOCASE,
                alias TEXT NOT NULL COLLATE NOCASE,
                sender_address TEXT NOT NULL COLLATE NOCASE,
                sender_domain TEXT NOT NULL COLLATE NOCASE,
                received_count INTEGER NOT NULL DEFAULT 0,
                last_received_at INTEGER,
                PRIMARY KEY (mailbox, alias, sender_address)
            );
            """
        )
        return connection

    async def sync_mode(
        self,
        mailbox: str,
        mode: StatsMode,
        *,
        started_at: int,
    ) -> None:
        await asyncio.to_thread(self._sync_mode, mailbox, mode, int(started_at))

    def _sync_mode(self, mailbox: str, mode: StatsMode, started_at: int) -> None:
        mailbox = mailbox.lower()
        enabled = {level for level in LEVELS if stats_mode_rank(level) <= stats_mode_rank(mode)}
        with self._connect() as connection:
            for level in enabled:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO stats_history_level_state (
                        mailbox, level, live_started_at
                    ) VALUES (?, ?, ?)
                    """,
                    (mailbox, level.value, started_at),
                )

            for level in LEVELS:
                if level in enabled:
                    continue
                self._clear_level(connection, mailbox, level)

            if mode is StatsMode.OFF:
                connection.execute(
                    "DELETE FROM stats_history_requests WHERE mailbox = ?",
                    (mailbox,),
                )

    @staticmethod
    def _clear_level(
        connection: sqlite3.Connection,
        mailbox: str,
        level: StatsMode,
    ) -> None:
        connection.execute(
            "DELETE FROM stats_history_level_state WHERE mailbox = ? AND level = ?",
            (mailbox, level.value),
        )
        connection.execute(
            "DELETE FROM stats_history_coverage WHERE mailbox = ? AND level = ?",
            (mailbox, level.value),
        )
        connection.execute(
            "DELETE FROM stats_history_processed WHERE mailbox = ? AND level = ?",
            (mailbox, level.value),
        )
        if level is StatsMode.BASIC:
            connection.execute(
                "DELETE FROM stats_history_alias_usage WHERE mailbox = ?",
                (mailbox,),
            )
        elif level is StatsMode.DOMAIN:
            connection.execute(
                "DELETE FROM stats_history_sender_domain WHERE mailbox = ?",
                (mailbox,),
            )
        elif level is StatsMode.FULL:
            connection.execute(
                "DELETE FROM stats_history_sender_full WHERE mailbox = ?",
                (mailbox,),
            )

    async def request_backfill(
        self,
        mailbox: str,
        target_mode: StatsMode,
        *,
        requested_at: int | None = None,
    ) -> None:
        if target_mode is StatsMode.OFF:
            return
        timestamp = int(time.time()) if requested_at is None else int(requested_at)
        await asyncio.to_thread(
            self._request_backfill,
            mailbox,
            target_mode,
            timestamp,
        )

    def _request_backfill(
        self,
        mailbox: str,
        target_mode: StatsMode,
        requested_at: int,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO stats_history_requests (mailbox, target_mode, requested_at)
                VALUES (?, ?, ?)
                ON CONFLICT(mailbox) DO UPDATE SET
                    target_mode = CASE
                        WHEN excluded.target_mode = 'full' THEN 'full'
                        WHEN stats_history_requests.target_mode = 'full' THEN 'full'
                        WHEN excluded.target_mode = 'domain' THEN 'domain'
                        WHEN stats_history_requests.target_mode = 'domain' THEN 'domain'
                        ELSE 'basic'
                    END,
                    requested_at = excluded.requested_at
                """,
                (mailbox.lower(), target_mode.value, requested_at),
            )

    async def pending_requests(
        self,
        mailboxes: set[str],
    ) -> dict[str, HistoryBackfillRequest]:
        if not mailboxes:
            return {}
        return await asyncio.to_thread(self._pending_requests, mailboxes)

    def _pending_requests(
        self,
        mailboxes: set[str],
    ) -> dict[str, HistoryBackfillRequest]:
        normalized = {mailbox.lower() for mailbox in mailboxes}
        placeholders = ",".join("?" for _ in normalized)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT mailbox, target_mode, requested_at
                FROM stats_history_requests
                WHERE mailbox IN ({placeholders})
                """,
                tuple(normalized),
            ).fetchall()
        return {
            str(row["mailbox"]).lower(): HistoryBackfillRequest(
                mailbox=str(row["mailbox"]).lower(),
                target_mode=StatsMode(str(row["target_mode"])),
                requested_at=int(row["requested_at"]),
            )
            for row in rows
        }

    async def pending_request(self, mailbox: str) -> HistoryBackfillRequest | None:
        values = await self.pending_requests({mailbox})
        return values.get(mailbox.lower())

    async def level_starts(self, mailbox: str) -> dict[StatsMode, int]:
        return await asyncio.to_thread(self._level_starts, mailbox)

    def _level_starts(self, mailbox: str) -> dict[StatsMode, int]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT level, live_started_at
                FROM stats_history_level_state
                WHERE mailbox = ?
                """,
                (mailbox.lower(),),
            ).fetchall()
        return {
            StatsMode(str(row["level"])): int(row["live_started_at"])
            for row in rows
        }

    async def record_usage_events(self, events: list[HistoricalUsageEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_usage_events, events)

    def _record_usage_events(self, events: list[HistoricalUsageEvent]) -> int:
        recorded = 0
        with self._connect() as connection:
            for event in events:
                if event.kind not in {"received", "sent"}:
                    raise ValueError("Historical usage event must be received or sent")
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO stats_history_processed (
                        mailbox, level, event_key, event_at
                    ) VALUES (?, 'basic', ?, ?)
                    """,
                    (event.mailbox.lower(), event.event_key, int(event.event_at)),
                )
                if inserted.rowcount != 1:
                    continue

                if event.kind == "received":
                    connection.execute(
                        """
                        INSERT INTO stats_history_alias_usage (
                            mailbox, alias, received_count, last_received_at
                        ) VALUES (?, ?, 1, ?)
                        ON CONFLICT(mailbox, alias) DO UPDATE SET
                            received_count = stats_history_alias_usage.received_count + 1,
                            last_received_at = MAX(
                                COALESCE(
                                    stats_history_alias_usage.last_received_at,
                                    excluded.last_received_at
                                ),
                                excluded.last_received_at
                            )
                        """,
                        (event.mailbox.lower(), event.alias.lower(), int(event.event_at)),
                    )
                else:
                    connection.execute(
                        """
                        INSERT INTO stats_history_alias_usage (
                            mailbox, alias, sent_count, last_sent_at
                        ) VALUES (?, ?, 1, ?)
                        ON CONFLICT(mailbox, alias) DO UPDATE SET
                            sent_count = stats_history_alias_usage.sent_count + 1,
                            last_sent_at = MAX(
                                COALESCE(
                                    stats_history_alias_usage.last_sent_at,
                                    excluded.last_sent_at
                                ),
                                excluded.last_sent_at
                            )
                        """,
                        (event.mailbox.lower(), event.alias.lower(), int(event.event_at)),
                    )
                recorded += 1
        return recorded

    async def record_sender_events(self, events: list[HistoricalSenderEvent]) -> int:
        if not events:
            return 0
        return await asyncio.to_thread(self._record_sender_events, events)

    def _record_sender_events(self, events: list[HistoricalSenderEvent]) -> int:
        recorded = 0
        with self._connect() as connection:
            for event in events:
                if event.level not in {StatsMode.DOMAIN, StatsMode.FULL}:
                    raise ValueError("Historical sender event must use Domain or Full level")
                inserted = connection.execute(
                    """
                    INSERT OR IGNORE INTO stats_history_processed (
                        mailbox, level, event_key, event_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        event.mailbox.lower(),
                        event.level.value,
                        event.event_key,
                        int(event.event_at),
                    ),
                )
                if inserted.rowcount != 1:
                    continue

                if event.level is StatsMode.DOMAIN:
                    connection.execute(
                        """
                        INSERT INTO stats_history_sender_domain (
                            mailbox,
                            alias,
                            sender_domain,
                            received_count,
                            last_received_at
                        ) VALUES (?, ?, ?, 1, ?)
                        ON CONFLICT(mailbox, alias, sender_domain) DO UPDATE SET
                            received_count = stats_history_sender_domain.received_count + 1,
                            last_received_at = MAX(
                                COALESCE(
                                    stats_history_sender_domain.last_received_at,
                                    excluded.last_received_at
                                ),
                                excluded.last_received_at
                            )
                        """,
                        (
                            event.mailbox.lower(),
                            event.alias.lower(),
                            event.sender_domain.lower(),
                            int(event.event_at),
                        ),
                    )
                elif event.sender_address:
                    connection.execute(
                        """
                        INSERT INTO stats_history_sender_full (
                            mailbox,
                            alias,
                            sender_address,
                            sender_domain,
                            received_count,
                            last_received_at
                        ) VALUES (?, ?, ?, ?, 1, ?)
                        ON CONFLICT(mailbox, alias, sender_address) DO UPDATE SET
                            received_count = stats_history_sender_full.received_count + 1,
                            last_received_at = MAX(
                                COALESCE(
                                    stats_history_sender_full.last_received_at,
                                    excluded.last_received_at
                                ),
                                excluded.last_received_at
                            )
                        """,
                        (
                            event.mailbox.lower(),
                            event.alias.lower(),
                            event.sender_address.lower(),
                            event.sender_domain.lower(),
                            int(event.event_at),
                        ),
                    )
                recorded += 1
        return recorded

    async def complete_backfill(
        self,
        request: HistoryBackfillRequest,
        *,
        oldest_history_at: int | None,
        history_count: int,
        history_limit: int,
        completed_at: int | None = None,
    ) -> None:
        timestamp = int(time.time()) if completed_at is None else int(completed_at)
        await asyncio.to_thread(
            self._complete_backfill,
            request,
            oldest_history_at,
            int(history_count),
            int(history_limit),
            timestamp,
        )

    def _complete_backfill(
        self,
        request: HistoryBackfillRequest,
        oldest_history_at: int | None,
        history_count: int,
        history_limit: int,
        completed_at: int,
    ) -> None:
        mailbox = request.mailbox.lower()
        target_rank = stats_mode_rank(request.target_mode)
        with self._connect() as connection:
            level_rows = connection.execute(
                """
                SELECT level, live_started_at
                FROM stats_history_level_state
                WHERE mailbox = ?
                """,
                (mailbox,),
            ).fetchall()
            starts = {
                StatsMode(str(row["level"])): int(row["live_started_at"])
                for row in level_rows
            }
            for level in LEVELS:
                if stats_mode_rank(level) > target_rank or level not in starts:
                    continue
                usable_oldest = (
                    int(oldest_history_at)
                    if oldest_history_at is not None
                    and int(oldest_history_at) < starts[level]
                    else None
                )
                existing = connection.execute(
                    """
                    SELECT history_oldest_at
                    FROM stats_history_coverage
                    WHERE mailbox = ? AND level = ?
                    """,
                    (mailbox, level.value),
                ).fetchone()
                if existing is not None and existing["history_oldest_at"] is not None:
                    previous = int(existing["history_oldest_at"])
                    usable_oldest = (
                        previous
                        if usable_oldest is None
                        else min(previous, usable_oldest)
                    )
                connection.execute(
                    """
                    INSERT INTO stats_history_coverage (
                        mailbox,
                        level,
                        history_oldest_at,
                        completed_at,
                        history_count,
                        history_limit
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(mailbox, level) DO UPDATE SET
                        history_oldest_at = excluded.history_oldest_at,
                        completed_at = excluded.completed_at,
                        history_count = excluded.history_count,
                        history_limit = excluded.history_limit
                    """,
                    (
                        mailbox,
                        level.value,
                        usable_oldest,
                        completed_at,
                        history_count,
                        history_limit,
                    ),
                )
            connection.execute(
                "DELETE FROM stats_history_requests WHERE mailbox = ?",
                (mailbox,),
            )

    async def coverage(self, mailbox: str) -> dict[StatsMode, HistoryCoverage]:
        return await asyncio.to_thread(self._coverage, mailbox)

    def _coverage(self, mailbox: str) -> dict[StatsMode, HistoryCoverage]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    l.level,
                    l.live_started_at,
                    c.history_oldest_at,
                    c.completed_at,
                    c.history_count,
                    c.history_limit
                FROM stats_history_level_state AS l
                LEFT JOIN stats_history_coverage AS c
                    ON c.mailbox = l.mailbox AND c.level = l.level
                WHERE l.mailbox = ?
                """,
                (mailbox.lower(),),
            ).fetchall()
        return {
            StatsMode(str(row["level"])): HistoryCoverage(
                level=StatsMode(str(row["level"])),
                live_started_at=int(row["live_started_at"]),
                history_oldest_at=(
                    int(row["history_oldest_at"])
                    if row["history_oldest_at"] is not None
                    else None
                ),
                completed_at=(
                    int(row["completed_at"]) if row["completed_at"] is not None else None
                ),
                history_count=(
                    int(row["history_count"]) if row["history_count"] is not None else None
                ),
                history_limit=(
                    int(row["history_limit"]) if row["history_limit"] is not None else None
                ),
            )
            for row in rows
        }

    async def alias_usage(self, mailbox: str, aliases: list[str]) -> dict[str, AliasUsage]:
        if not aliases:
            return {}
        return await asyncio.to_thread(self._alias_usage, mailbox, aliases)

    def _alias_usage(self, mailbox: str, aliases: list[str]) -> dict[str, AliasUsage]:
        placeholders = ",".join("?" for _ in aliases)
        params = [mailbox.lower(), *(alias.lower() for alias in aliases)]
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT alias, received_count, sent_count, last_received_at, last_sent_at
                FROM stats_history_alias_usage
                WHERE mailbox = ? AND alias IN ({placeholders})
                """,
                params,
            ).fetchall()
        return {
            str(row["alias"]).lower(): AliasUsage(
                received_count=int(row["received_count"]),
                sent_count=int(row["sent_count"]),
                last_received_at=(
                    int(row["last_received_at"])
                    if row["last_received_at"] is not None
                    else None
                ),
                last_sent_at=(
                    int(row["last_sent_at"])
                    if row["last_sent_at"] is not None
                    else None
                ),
            )
            for row in rows
        }

    async def sender_usage(
        self,
        mailbox: str,
        aliases: list[str],
        *,
        level: StatsMode,
    ) -> dict[str, list[SenderUsage]]:
        if not aliases or level not in {StatsMode.DOMAIN, StatsMode.FULL}:
            return {}
        return await asyncio.to_thread(self._sender_usage, mailbox, aliases, level)

    def _sender_usage(
        self,
        mailbox: str,
        aliases: list[str],
        level: StatsMode,
    ) -> dict[str, list[SenderUsage]]:
        placeholders = ",".join("?" for _ in aliases)
        params = [mailbox.lower(), *(alias.lower() for alias in aliases)]
        if level is StatsMode.DOMAIN:
            query = f"""
                SELECT
                    h.alias,
                    h.sender_domain AS sender_key,
                    h.sender_domain,
                    NULL AS sender_address,
                    h.received_count,
                    h.last_received_at,
                    e.expected AS exact_expected,
                    e.expected AS domain_expected
                FROM stats_history_sender_domain AS h
                LEFT JOIN sender_expectations AS e
                    ON e.mailbox = h.mailbox
                    AND e.alias = h.alias
                    AND e.sender_key = h.sender_domain
                WHERE h.mailbox = ? AND h.alias IN ({placeholders})
                ORDER BY h.alias, h.last_received_at DESC, h.sender_domain
            """
        else:
            query = f"""
                SELECT
                    h.alias,
                    h.sender_address AS sender_key,
                    h.sender_domain,
                    h.sender_address,
                    h.received_count,
                    h.last_received_at,
                    exact_e.expected AS exact_expected,
                    domain_e.expected AS domain_expected
                FROM stats_history_sender_full AS h
                LEFT JOIN sender_expectations AS exact_e
                    ON exact_e.mailbox = h.mailbox
                    AND exact_e.alias = h.alias
                    AND exact_e.sender_key = h.sender_address
                LEFT JOIN sender_expectations AS domain_e
                    ON domain_e.mailbox = h.mailbox
                    AND domain_e.alias = h.alias
                    AND domain_e.sender_key = h.sender_domain
                WHERE h.mailbox = ? AND h.alias IN ({placeholders})
                ORDER BY h.alias, h.last_received_at DESC, h.sender_address
            """

        with self._connect() as connection:
            rows = connection.execute(query, params).fetchall()

        result: dict[str, list[SenderUsage]] = {}
        for row in rows:
            exact_expected = row["exact_expected"]
            domain_expected = row["domain_expected"]
            manual_expected = exact_expected if exact_expected is not None else domain_expected
            alias = str(row["alias"]).lower()
            result.setdefault(alias, []).append(
                SenderUsage(
                    sender_key=str(row["sender_key"]).lower(),
                    sender_domain=str(row["sender_domain"]).lower(),
                    sender_address=(
                        str(row["sender_address"]).lower()
                        if row["sender_address"] is not None
                        else None
                    ),
                    received_count=int(row["received_count"]),
                    last_received_at=(
                        int(row["last_received_at"])
                        if row["last_received_at"] is not None
                        else None
                    ),
                    manual_expected=(
                        bool(manual_expected) if manual_expected is not None else None
                    ),
                )
            )
        return result
