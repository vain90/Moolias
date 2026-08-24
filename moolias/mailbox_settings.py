from __future__ import annotations

import asyncio
import sqlite3
import time
from pathlib import Path


class MailboxSettingsStore:
    """Persist mailbox-specific application preferences outside Mailcow."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mailbox_feature_settings (
                mailbox TEXT PRIMARY KEY COLLATE NOCASE,
                newsletter_enabled INTEGER
                    CHECK (newsletter_enabled IS NULL OR newsletter_enabled IN (0, 1)),
                updated_at INTEGER NOT NULL
            )
            """
        )
        return connection

    async def newsletter_enabled(self, mailbox: str) -> bool | None:
        return await asyncio.to_thread(self._newsletter_enabled, mailbox)

    def _newsletter_enabled(self, mailbox: str) -> bool | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT newsletter_enabled
                FROM mailbox_feature_settings
                WHERE mailbox = ?
                """,
                (mailbox.strip().lower(),),
            ).fetchone()
        if row is None or row["newsletter_enabled"] is None:
            return None
        return bool(row["newsletter_enabled"])

    async def set_newsletter_enabled(self, mailbox: str, enabled: bool) -> None:
        await asyncio.to_thread(self._set_newsletter_enabled, mailbox, enabled)

    def _set_newsletter_enabled(self, mailbox: str, enabled: bool) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO mailbox_feature_settings (
                    mailbox,
                    newsletter_enabled,
                    updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(mailbox) DO UPDATE SET
                    newsletter_enabled = excluded.newsletter_enabled,
                    updated_at = excluded.updated_at
                """,
                (
                    mailbox.strip().lower(),
                    1 if enabled else 0,
                    int(time.time()),
                ),
            )
