from __future__ import annotations

import asyncio
import sqlite3
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

WORKFLOW_CREATION = "creation"
WORKFLOW_REPLACEMENT = "replacement"
DEACTIVATION_LATER = "later"
DEACTIVATION_NOW = "now"
DEACTIVATION_7_DAYS = "7d"
DEACTIVATION_30_DAYS = "30d"
DEACTIVATION_MODES = {
    DEACTIVATION_LATER,
    DEACTIVATION_NOW,
    DEACTIVATION_7_DAYS,
    DEACTIVATION_30_DAYS,
}


@dataclass(frozen=True, slots=True)
class AliasWorkflow:
    id: int
    kind: str
    mailbox: str
    old_alias_id: int | None
    old_address: str | None
    new_address: str
    alias_name: str
    alias_description: str
    started_at: int
    watcher_active: bool
    old_mail_received_at: int | None
    new_mail_received_at: int | None
    deactivation_mode: str
    scheduled_deactivation_at: int | None
    bypass_expires_at: int
    bypass_provisioned_at: int | None
    bypass_clear_requested_at: int | None
    bypass_cleared_at: int | None
    completed_at: int | None

    @property
    def is_replacement(self) -> bool:
        return self.kind == WORKFLOW_REPLACEMENT

    @property
    def is_pending_replacement(self) -> bool:
        return self.is_replacement and self.completed_at is None

    @property
    def bypass_recipients(self) -> tuple[str, ...]:
        if self.old_address:
            return (self.old_address, self.new_address)
        return (self.new_address,)

    @property
    def waiting_state(self) -> str:
        if self.new_mail_received_at is not None:
            return "received"
        if self.old_mail_received_at is not None:
            return "old_received"
        if self.watcher_active:
            return "waiting"
        return "stopped"


class AliasWorkflowStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize_sync)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_sync(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS alias_workflows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kind TEXT NOT NULL CHECK (kind IN ('creation', 'replacement')),
                    mailbox TEXT NOT NULL COLLATE NOCASE,
                    old_alias_id INTEGER,
                    old_address TEXT COLLATE NOCASE,
                    new_address TEXT NOT NULL COLLATE NOCASE,
                    alias_name TEXT NOT NULL DEFAULT '',
                    alias_description TEXT NOT NULL DEFAULT '',
                    started_at INTEGER NOT NULL,
                    watcher_active INTEGER NOT NULL DEFAULT 1,
                    old_mail_received_at INTEGER,
                    new_mail_received_at INTEGER,
                    deactivation_mode TEXT NOT NULL DEFAULT 'later',
                    scheduled_deactivation_at INTEGER,
                    bypass_expires_at INTEGER NOT NULL,
                    bypass_provisioned_at INTEGER,
                    bypass_clear_requested_at INTEGER,
                    bypass_cleared_at INTEGER,
                    completed_at INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_alias_workflows_mailbox
                    ON alias_workflows(mailbox, completed_at, started_at DESC);
                CREATE INDEX IF NOT EXISTS idx_alias_workflows_watchers
                    ON alias_workflows(watcher_active, completed_at, started_at);
                CREATE INDEX IF NOT EXISTS idx_alias_workflows_deactivation
                    ON alias_workflows(scheduled_deactivation_at, completed_at);
                CREATE INDEX IF NOT EXISTS idx_alias_workflows_bypass
                    ON alias_workflows(
                        bypass_clear_requested_at,
                        bypass_cleared_at,
                        bypass_expires_at
                    );
                """
            )

    @staticmethod
    def _row(row: sqlite3.Row | None) -> AliasWorkflow | None:
        if row is None:
            return None
        return AliasWorkflow(
            id=int(row["id"]),
            kind=str(row["kind"]),
            mailbox=str(row["mailbox"]).lower(),
            old_alias_id=(None if row["old_alias_id"] is None else int(row["old_alias_id"])),
            old_address=(None if row["old_address"] is None else str(row["old_address"]).lower()),
            new_address=str(row["new_address"]).lower(),
            alias_name=str(row["alias_name"] or ""),
            alias_description=str(row["alias_description"] or ""),
            started_at=int(row["started_at"]),
            watcher_active=bool(row["watcher_active"]),
            old_mail_received_at=(
                None if row["old_mail_received_at"] is None else int(row["old_mail_received_at"])
            ),
            new_mail_received_at=(
                None if row["new_mail_received_at"] is None else int(row["new_mail_received_at"])
            ),
            deactivation_mode=str(row["deactivation_mode"]),
            scheduled_deactivation_at=(
                None
                if row["scheduled_deactivation_at"] is None
                else int(row["scheduled_deactivation_at"])
            ),
            bypass_expires_at=int(row["bypass_expires_at"]),
            bypass_provisioned_at=(
                None
                if row["bypass_provisioned_at"] is None
                else int(row["bypass_provisioned_at"])
            ),
            bypass_clear_requested_at=(
                None
                if row["bypass_clear_requested_at"] is None
                else int(row["bypass_clear_requested_at"])
            ),
            bypass_cleared_at=(
                None if row["bypass_cleared_at"] is None else int(row["bypass_cleared_at"])
            ),
            completed_at=(None if row["completed_at"] is None else int(row["completed_at"])),
        )

    async def create_creation(
        self,
        *,
        mailbox: str,
        new_address: str,
        alias_name: str,
        alias_description: str,
        bypass_expires_at: int,
        started_at: int | None = None,
    ) -> AliasWorkflow:
        return await asyncio.to_thread(
            self._create_sync,
            WORKFLOW_CREATION,
            mailbox,
            None,
            None,
            new_address,
            alias_name,
            alias_description,
            int(time.time()) if started_at is None else int(started_at),
            int(bypass_expires_at),
        )

    async def create_replacement(
        self,
        *,
        mailbox: str,
        old_alias_id: int,
        old_address: str,
        new_address: str,
        alias_name: str,
        alias_description: str,
        bypass_expires_at: int,
        started_at: int | None = None,
    ) -> AliasWorkflow:
        return await asyncio.to_thread(
            self._create_sync,
            WORKFLOW_REPLACEMENT,
            mailbox,
            int(old_alias_id),
            old_address,
            new_address,
            alias_name,
            alias_description,
            int(time.time()) if started_at is None else int(started_at),
            int(bypass_expires_at),
        )

    def _create_sync(
        self,
        kind: str,
        mailbox: str,
        old_alias_id: int | None,
        old_address: str | None,
        new_address: str,
        alias_name: str,
        alias_description: str,
        started_at: int,
        bypass_expires_at: int,
    ) -> AliasWorkflow:
        if bypass_expires_at <= started_at:
            raise ValueError("bypass expiry must be after workflow start")
        mailbox = mailbox.strip().lower()
        new_address = new_address.strip().lower()
        old_address = old_address.strip().lower() if old_address else None
        with self._connect() as connection:
            if kind == WORKFLOW_REPLACEMENT:
                existing = connection.execute(
                    """
                    SELECT id FROM alias_workflows
                    WHERE mailbox = ? COLLATE NOCASE
                      AND completed_at IS NULL
                      AND kind = 'replacement'
                      AND (
                          old_address = ? COLLATE NOCASE
                          OR old_address = ? COLLATE NOCASE
                          OR new_address = ? COLLATE NOCASE
                          OR new_address = ? COLLATE NOCASE
                      )
                    LIMIT 1
                    """,
                    (mailbox, old_address, new_address, old_address, new_address),
                ).fetchone()
                if existing is not None:
                    raise ValueError("an active replacement already exists for this alias")
            cursor = connection.execute(
                """
                INSERT INTO alias_workflows (
                    kind, mailbox, old_alias_id, old_address, new_address,
                    alias_name, alias_description, started_at, bypass_expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    kind,
                    mailbox,
                    old_alias_id,
                    old_address,
                    new_address,
                    alias_name.strip(),
                    alias_description.strip(),
                    started_at,
                    bypass_expires_at,
                ),
            )
            row = connection.execute(
                "SELECT * FROM alias_workflows WHERE id = ?",
                (cursor.lastrowid,),
            ).fetchone()
        record = self._row(row)
        assert record is not None
        return record

    async def get(self, mailbox: str, workflow_id: int) -> AliasWorkflow | None:
        return await asyncio.to_thread(self._get_sync, mailbox, workflow_id)

    def _get_sync(self, mailbox: str, workflow_id: int) -> AliasWorkflow | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM alias_workflows WHERE id = ? AND mailbox = ? COLLATE NOCASE",
                (int(workflow_id), mailbox.strip().lower()),
            ).fetchone()
        return self._row(row)

    async def pending_replacements(self, mailbox: str) -> list[AliasWorkflow]:
        return await asyncio.to_thread(self._pending_replacements_sync, mailbox)

    def _pending_replacements_sync(self, mailbox: str) -> list[AliasWorkflow]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alias_workflows
                WHERE mailbox = ? COLLATE NOCASE
                  AND kind = 'replacement'
                  AND completed_at IS NULL
                ORDER BY started_at DESC, id DESC
                """,
                (mailbox.strip().lower(),),
            ).fetchall()
        return [record for row in rows if (record := self._row(row)) is not None]

    async def active_watchers(self) -> list[AliasWorkflow]:
        return await asyncio.to_thread(self._active_watchers_sync)

    def _active_watchers_sync(self) -> list[AliasWorkflow]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alias_workflows
                WHERE watcher_active = 1
                  AND completed_at IS NULL
                  AND new_mail_received_at IS NULL
                ORDER BY started_at ASC, id ASC
                """
            ).fetchall()
        return [record for row in rows if (record := self._row(row)) is not None]

    async def stop_waiting(self, mailbox: str, workflow_id: int) -> AliasWorkflow | None:
        return await asyncio.to_thread(self._stop_waiting_sync, mailbox, workflow_id)

    def _stop_waiting_sync(self, mailbox: str, workflow_id: int) -> AliasWorkflow | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE alias_workflows SET watcher_active = 0
                WHERE id = ? AND mailbox = ? COLLATE NOCASE
                """,
                (int(workflow_id), mailbox.strip().lower()),
            )
            row = connection.execute(
                "SELECT * FROM alias_workflows WHERE id = ? AND mailbox = ? COLLATE NOCASE",
                (int(workflow_id), mailbox.strip().lower()),
            ).fetchone()
        return self._row(row)

    async def record_deliveries(
        self,
        deliveries: Iterable[tuple[str, int]],
    ) -> list[AliasWorkflow]:
        normalized = [(address.strip().lower(), int(event_at)) for address, event_at in deliveries]
        if not normalized:
            return []
        return await asyncio.to_thread(self._record_deliveries_sync, normalized)

    def _record_deliveries_sync(
        self,
        deliveries: list[tuple[str, int]],
    ) -> list[AliasWorkflow]:
        changed_ids: set[int] = set()
        with self._connect() as connection:
            for recipient, event_at in deliveries:
                rows = connection.execute(
                    """
                    SELECT * FROM alias_workflows
                    WHERE watcher_active = 1
                      AND completed_at IS NULL
                      AND started_at <= ?
                      AND (new_address = ? COLLATE NOCASE OR old_address = ? COLLATE NOCASE)
                    """,
                    (event_at, recipient, recipient),
                ).fetchall()
                for row in rows:
                    workflow_id = int(row["id"])
                    if str(row["new_address"]).lower() == recipient:
                        connection.execute(
                            """
                            UPDATE alias_workflows
                            SET new_mail_received_at = COALESCE(new_mail_received_at, ?),
                                watcher_active = 0,
                                bypass_clear_requested_at = COALESCE(bypass_clear_requested_at, ?)
                            WHERE id = ?
                            """,
                            (event_at, event_at, workflow_id),
                        )
                    elif (
                        row["old_address"] is not None
                        and str(row["old_address"]).lower() == recipient
                    ):
                        connection.execute(
                            """
                            UPDATE alias_workflows
                            SET old_mail_received_at = COALESCE(old_mail_received_at, ?)
                            WHERE id = ?
                            """,
                            (event_at, workflow_id),
                        )
                    changed_ids.add(workflow_id)

            if not changed_ids:
                return []
            placeholders = ",".join("?" for _ in changed_ids)
            rows = connection.execute(
                f"SELECT * FROM alias_workflows WHERE id IN ({placeholders}) ORDER BY id",
                tuple(sorted(changed_ids)),
            ).fetchall()
        return [record for row in rows if (record := self._row(row)) is not None]

    async def mark_bypass_provisioned(
        self,
        workflow_id: int,
        *,
        now: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_timestamp_sync,
            workflow_id,
            "bypass_provisioned_at",
            int(time.time()) if now is None else int(now),
        )

    async def mark_bypass_cleared(
        self,
        workflow_id: int,
        *,
        now: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_timestamp_sync,
            workflow_id,
            "bypass_cleared_at",
            int(time.time()) if now is None else int(now),
        )

    def _mark_timestamp_sync(self, workflow_id: int, column: str, value: int) -> None:
        if column not in {"bypass_provisioned_at", "bypass_cleared_at"}:
            raise ValueError("unsupported workflow timestamp")
        with self._connect() as connection:
            connection.execute(
                f"UPDATE alias_workflows SET {column} = ? WHERE id = ?",
                (value, int(workflow_id)),
            )

    async def bypass_provisioning_due(self, now: int | None = None) -> list[AliasWorkflow]:
        return await asyncio.to_thread(
            self._bypass_provisioning_due_sync,
            int(time.time()) if now is None else int(now),
        )

    def _bypass_provisioning_due_sync(self, now: int) -> list[AliasWorkflow]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alias_workflows
                WHERE bypass_provisioned_at IS NULL
                  AND bypass_cleared_at IS NULL
                  AND bypass_expires_at > ?
                ORDER BY started_at ASC
                """,
                (now,),
            ).fetchall()
        return [record for row in rows if (record := self._row(row)) is not None]

    async def bypass_clear_due(self) -> list[AliasWorkflow]:
        return await asyncio.to_thread(self._bypass_clear_due_sync)

    def _bypass_clear_due_sync(self) -> list[AliasWorkflow]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alias_workflows
                WHERE bypass_clear_requested_at IS NOT NULL
                  AND bypass_cleared_at IS NULL
                ORDER BY bypass_clear_requested_at ASC
                """
            ).fetchall()
        return [record for row in rows if (record := self._row(row)) is not None]

    async def set_deactivation(
        self,
        mailbox: str,
        workflow_id: int,
        mode: str,
        *,
        now: int | None = None,
    ) -> AliasWorkflow:
        if mode not in DEACTIVATION_MODES:
            raise ValueError("unknown deactivation mode")
        current = int(time.time()) if now is None else int(now)
        schedule = {
            DEACTIVATION_LATER: None,
            DEACTIVATION_NOW: None,
            DEACTIVATION_7_DAYS: current + 7 * 86400,
            DEACTIVATION_30_DAYS: current + 30 * 86400,
        }[mode]
        record = await asyncio.to_thread(
            self._set_deactivation_sync,
            mailbox,
            workflow_id,
            mode,
            schedule,
        )
        if record is None:
            raise KeyError(workflow_id)
        return record

    def _set_deactivation_sync(
        self,
        mailbox: str,
        workflow_id: int,
        mode: str,
        scheduled_at: int | None,
    ) -> AliasWorkflow | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE alias_workflows
                SET deactivation_mode = ?, scheduled_deactivation_at = ?
                WHERE id = ?
                  AND mailbox = ? COLLATE NOCASE
                  AND kind = 'replacement'
                  AND completed_at IS NULL
                """,
                (mode, scheduled_at, int(workflow_id), mailbox.strip().lower()),
            )
            row = connection.execute(
                "SELECT * FROM alias_workflows WHERE id = ? AND mailbox = ? COLLATE NOCASE",
                (int(workflow_id), mailbox.strip().lower()),
            ).fetchone()
        return self._row(row)

    async def due_deactivations(self, now: int | None = None) -> list[AliasWorkflow]:
        return await asyncio.to_thread(
            self._due_deactivations_sync,
            int(time.time()) if now is None else int(now),
        )

    def _due_deactivations_sync(self, now: int) -> list[AliasWorkflow]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM alias_workflows
                WHERE kind = 'replacement'
                  AND completed_at IS NULL
                  AND scheduled_deactivation_at IS NOT NULL
                  AND scheduled_deactivation_at <= ?
                ORDER BY scheduled_deactivation_at ASC
                """,
                (now,),
            ).fetchall()
        return [record for row in rows if (record := self._row(row)) is not None]

    async def complete_replacement(
        self,
        mailbox: str,
        workflow_id: int,
        *,
        now: int | None = None,
    ) -> AliasWorkflow | None:
        return await asyncio.to_thread(
            self._complete_replacement_sync,
            mailbox,
            workflow_id,
            int(time.time()) if now is None else int(now),
        )

    def _complete_replacement_sync(
        self,
        mailbox: str,
        workflow_id: int,
        completed_at: int,
    ) -> AliasWorkflow | None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE alias_workflows
                SET completed_at = ?, watcher_active = 0, scheduled_deactivation_at = NULL
                WHERE id = ?
                  AND mailbox = ? COLLATE NOCASE
                  AND kind = 'replacement'
                  AND completed_at IS NULL
                """,
                (completed_at, int(workflow_id), mailbox.strip().lower()),
            )
            row = connection.execute(
                "SELECT * FROM alias_workflows WHERE id = ? AND mailbox = ? COLLATE NOCASE",
                (int(workflow_id), mailbox.strip().lower()),
            ).fetchone()
        return self._row(row)

    async def cleanup(self, *, before: int) -> int:
        return await asyncio.to_thread(self._cleanup_sync, int(before))

    def _cleanup_sync(self, before: int) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                DELETE FROM alias_workflows
                WHERE kind = 'creation'
                  AND watcher_active = 0
                  AND started_at < ?
                """,
                (before,),
            )
            return int(cursor.rowcount)
