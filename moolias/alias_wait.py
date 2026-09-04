from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass

from moolias.alias_workflows import AliasWorkflow, AliasWorkflowStore, WORKFLOW_CREATION


@dataclass(frozen=True, slots=True)
class AliasWaitStatus:
    address: str
    workflow_id: int
    expires_at: int


def is_manual_alias_wait(workflow: AliasWorkflow) -> bool:
    return (
        workflow.kind == WORKFLOW_CREATION
        and workflow.old_alias_id is not None
        and workflow.old_address is None
    )


class AliasWaitService:
    """Reuse creation workflows for temporary first-mail waits on existing aliases."""

    def __init__(self, store: AliasWorkflowStore) -> None:
        self.store = store

    async def start(
        self,
        *,
        mailbox: str,
        alias_id: int,
        address: str,
        alias_name: str,
        alias_description: str,
        started_at: int,
        bypass_expires_at: int,
    ) -> AliasWorkflow:
        workflow_id = await asyncio.to_thread(
            self._start_sync,
            mailbox,
            int(alias_id),
            address,
            alias_name,
            alias_description,
            int(started_at),
            int(bypass_expires_at),
        )
        workflow = await self.store.get(mailbox, workflow_id)
        if workflow is None:
            raise RuntimeError("alias wait workflow could not be loaded")
        return workflow

    def _start_sync(
        self,
        mailbox: str,
        alias_id: int,
        address: str,
        alias_name: str,
        alias_description: str,
        started_at: int,
        bypass_expires_at: int,
    ) -> int:
        if bypass_expires_at <= started_at:
            raise ValueError("bypass expiry must be after workflow start")

        mailbox = mailbox.strip().lower()
        address = address.strip().lower()
        if not mailbox or not address:
            raise ValueError("mailbox and alias address are required")

        with sqlite3.connect(self.store.path, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute("BEGIN IMMEDIATE")

            replacement = connection.execute(
                """
                SELECT id
                FROM alias_workflows
                WHERE mailbox = ? COLLATE NOCASE
                  AND kind = 'replacement'
                  AND completed_at IS NULL
                  AND (
                      old_address = ? COLLATE NOCASE
                      OR new_address = ? COLLATE NOCASE
                  )
                LIMIT 1
                """,
                (mailbox, address, address),
            ).fetchone()
            if replacement is not None:
                raise ValueError("alias is part of an active replacement")

            existing = connection.execute(
                """
                SELECT id
                FROM alias_workflows
                WHERE mailbox = ? COLLATE NOCASE
                  AND kind = 'creation'
                  AND new_address = ? COLLATE NOCASE
                ORDER BY id DESC
                LIMIT 1
                """,
                (mailbox, address),
            ).fetchone()

            if existing is not None:
                workflow_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE alias_workflows
                    SET old_alias_id = ?,
                        old_address = NULL,
                        alias_name = ?,
                        alias_description = ?,
                        started_at = ?,
                        watcher_active = 1,
                        old_mail_received_at = NULL,
                        new_mail_received_at = NULL,
                        deactivation_mode = 'later',
                        scheduled_deactivation_at = NULL,
                        bypass_expires_at = ?,
                        bypass_provisioned_at = NULL,
                        bypass_clear_requested_at = NULL,
                        bypass_cleared_at = NULL,
                        cancelled_at = NULL,
                        completed_at = NULL
                    WHERE id = ?
                    """,
                    (
                        alias_id,
                        alias_name.strip(),
                        alias_description.strip(),
                        started_at,
                        bypass_expires_at,
                        workflow_id,
                    ),
                )
                return workflow_id

            cursor = connection.execute(
                """
                INSERT INTO alias_workflows (
                    kind,
                    mailbox,
                    old_alias_id,
                    old_address,
                    new_address,
                    alias_name,
                    alias_description,
                    started_at,
                    watcher_active,
                    bypass_expires_at
                ) VALUES ('creation', ?, ?, NULL, ?, ?, ?, ?, 1, ?)
                """,
                (
                    mailbox,
                    alias_id,
                    address,
                    alias_name.strip(),
                    alias_description.strip(),
                    started_at,
                    bypass_expires_at,
                ),
            )
            return int(cursor.lastrowid)

    async def active_for_mailbox(
        self,
        mailbox: str,
        *,
        now: int,
    ) -> list[AliasWaitStatus]:
        return await asyncio.to_thread(
            self._active_for_mailbox_sync,
            mailbox,
            int(now),
        )

    def _active_for_mailbox_sync(
        self,
        mailbox: str,
        now: int,
    ) -> list[AliasWaitStatus]:
        with sqlite3.connect(self.store.path, timeout=10) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA busy_timeout = 5000")
            rows = connection.execute(
                """
                SELECT id, new_address, bypass_expires_at
                FROM alias_workflows
                WHERE mailbox = ? COLLATE NOCASE
                  AND kind = 'creation'
                  AND completed_at IS NULL
                  AND watcher_active = 1
                  AND new_mail_received_at IS NULL
                  AND bypass_expires_at > ?
                ORDER BY started_at DESC, id DESC
                """,
                (mailbox.strip().lower(), now),
            ).fetchall()

        statuses: list[AliasWaitStatus] = []
        seen: set[str] = set()
        for row in rows:
            address = str(row["new_address"]).strip().lower()
            if not address or address in seen:
                continue
            seen.add(address)
            statuses.append(
                AliasWaitStatus(
                    address=address,
                    workflow_id=int(row["id"]),
                    expires_at=int(row["bypass_expires_at"]),
                )
            )
        return statuses

    async def expire_due(self, *, now: int) -> int:
        return await asyncio.to_thread(self._expire_due_sync, int(now))

    def _expire_due_sync(self, now: int) -> int:
        with sqlite3.connect(self.store.path, timeout=10) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            cursor = connection.execute(
                """
                UPDATE alias_workflows
                SET watcher_active = 0,
                    bypass_clear_requested_at = COALESCE(bypass_clear_requested_at, ?)
                WHERE kind = 'creation'
                  AND old_alias_id IS NOT NULL
                  AND old_address IS NULL
                  AND completed_at IS NULL
                  AND watcher_active = 1
                  AND new_mail_received_at IS NULL
                  AND bypass_expires_at <= ?
                """,
                (now, now),
            )
            return int(cursor.rowcount)
