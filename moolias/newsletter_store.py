from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

MAX_UNSUBSCRIBE_LINKS = 3


@dataclass(frozen=True, slots=True)
class NewsletterLink:
    id: int
    newsletter_id: int
    url: str
    one_click: bool
    mailto: str | None
    source_message_id: str | None
    discovered_at: int
    last_seen_at: int


@dataclass(frozen=True, slots=True)
class Newsletter:
    id: int
    mailbox: str
    recipient_alias: str
    identity_key: str
    sender_name: str
    sender_address: str
    list_id: str | None
    first_seen_at: int
    last_seen_at: int
    message_count: int
    latest_message_id: str | None
    unsubscribed_at: int | None
    links: tuple[NewsletterLink, ...] = ()

    @property
    def latest_link(self) -> NewsletterLink | None:
        return self.links[0] if self.links else None

    @property
    def direct_unsubscribe_available(self) -> bool:
        return self.latest_link is not None

    @property
    def one_click_available(self) -> bool:
        return any(link.one_click for link in self.links)


@dataclass(frozen=True, slots=True)
class NewsletterObservation:
    mailbox: str
    recipient_alias: str
    identity_key: str
    sender_name: str
    sender_address: str
    list_id: str | None
    message_id: str
    event_at: int
    unsubscribe_url: str | None = None
    unsubscribe_mailto: str | None = None
    one_click: bool = False
    headers_resolved: bool = False


class NewsletterStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    async def initialize(self) -> None:
        await asyncio.to_thread(self._initialize)

    def _initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS newsletters (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mailbox TEXT NOT NULL COLLATE NOCASE,
                    recipient_alias TEXT NOT NULL COLLATE NOCASE,
                    identity_key TEXT NOT NULL COLLATE NOCASE,
                    sender_name TEXT NOT NULL DEFAULT '',
                    sender_address TEXT NOT NULL COLLATE NOCASE,
                    list_id TEXT COLLATE NOCASE,
                    first_seen_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    latest_message_id TEXT,
                    unsubscribed_at INTEGER,
                    UNIQUE (mailbox, recipient_alias, identity_key)
                );

                CREATE INDEX IF NOT EXISTS newsletters_mailbox_last_seen_idx
                    ON newsletters (mailbox, last_seen_at DESC);

                CREATE TABLE IF NOT EXISTS newsletter_messages (
                    event_key TEXT PRIMARY KEY,
                    newsletter_id INTEGER NOT NULL REFERENCES newsletters(id) ON DELETE CASCADE,
                    message_id TEXT NOT NULL,
                    event_at INTEGER NOT NULL,
                    headers_checked INTEGER NOT NULL DEFAULT 0
                        CHECK (headers_checked IN (0, 1))
                );

                CREATE INDEX IF NOT EXISTS newsletter_messages_newsletter_idx
                    ON newsletter_messages (newsletter_id, event_at DESC);

                CREATE TABLE IF NOT EXISTS newsletter_unsubscribe_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    newsletter_id INTEGER NOT NULL REFERENCES newsletters(id) ON DELETE CASCADE,
                    url TEXT NOT NULL,
                    one_click INTEGER NOT NULL DEFAULT 0 CHECK (one_click IN (0, 1)),
                    mailto TEXT,
                    source_message_id TEXT,
                    discovered_at INTEGER NOT NULL,
                    last_seen_at INTEGER NOT NULL,
                    UNIQUE (newsletter_id, url)
                );

                CREATE INDEX IF NOT EXISTS newsletter_links_newsletter_seen_idx
                    ON newsletter_unsubscribe_links (newsletter_id, last_seen_at DESC, id DESC);

                CREATE TABLE IF NOT EXISTS newsletter_mailbox_scan_policy (
                    mailbox TEXT PRIMARY KEY COLLATE NOCASE,
                    history_since INTEGER NOT NULL CHECK (history_since >= 0),
                    updated_at INTEGER NOT NULL
                );
                """
            )
            message_columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(newsletter_messages)")
            }
            if "headers_checked" not in message_columns:
                connection.execute(
                    """
                    ALTER TABLE newsletter_messages
                    ADD COLUMN headers_checked INTEGER NOT NULL DEFAULT 0
                        CHECK (headers_checked IN (0, 1))
                    """
                )

    @staticmethod
    def _event_key(observation: NewsletterObservation) -> str:
        return "\x1f".join(
            (
                observation.mailbox.casefold(),
                observation.recipient_alias.casefold(),
                observation.message_id.strip(),
            )
        )

    @staticmethod
    def _history_allows(
        connection: sqlite3.Connection,
        mailbox: str,
        event_at: int,
    ) -> bool:
        row = connection.execute(
            """
            SELECT history_since
            FROM newsletter_mailbox_scan_policy
            WHERE mailbox = ?
            """,
            (mailbox.strip().casefold(),),
        ).fetchone()
        return row is None or int(event_at) >= int(row["history_since"])

    async def history_since(self, mailbox: str) -> int | None:
        return await asyncio.to_thread(self._history_since, mailbox)

    def _history_since(self, mailbox: str) -> int | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT history_since
                FROM newsletter_mailbox_scan_policy
                WHERE mailbox = ?
                """,
                (mailbox.strip().casefold(),),
            ).fetchone()
        return int(row["history_since"]) if row is not None else None

    async def set_history_since(self, mailbox: str, history_since: int) -> None:
        await asyncio.to_thread(self._set_history_since, mailbox, history_since)

    def _set_history_since(self, mailbox: str, history_since: int) -> None:
        value = max(0, int(history_since))
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO newsletter_mailbox_scan_policy (
                    mailbox,
                    history_since,
                    updated_at
                ) VALUES (?, ?, ?)
                ON CONFLICT(mailbox) DO UPDATE SET
                    history_since = excluded.history_since,
                    updated_at = excluded.updated_at
                """,
                (mailbox.strip().casefold(), value, int(time.time())),
            )

    async def record(self, observation: NewsletterObservation) -> int:
        return await asyncio.to_thread(self._record, observation)

    def _record(self, observation: NewsletterObservation) -> int:
        mailbox = observation.mailbox.strip().casefold()
        recipient_alias = observation.recipient_alias.strip().casefold()
        identity_key = observation.identity_key.strip().casefold()
        sender_address = observation.sender_address.strip().casefold()
        message_id = observation.message_id.strip()
        event_at = int(observation.event_at)
        if not mailbox or not recipient_alias or not identity_key or not sender_address:
            raise ValueError("Newsletter observation is missing required identity data")
        if not message_id:
            raise ValueError("Newsletter observation is missing a message ID")

        with self._connect() as connection:
            if not self._history_allows(connection, mailbox, event_at):
                return 0

            row = connection.execute(
                """
                SELECT id, unsubscribed_at
                FROM newsletters
                WHERE mailbox = ? AND recipient_alias = ? AND identity_key = ?
                """,
                (mailbox, recipient_alias, identity_key),
            ).fetchone()
            if row is None:
                cursor = connection.execute(
                    """
                    INSERT INTO newsletters (
                        mailbox,
                        recipient_alias,
                        identity_key,
                        sender_name,
                        sender_address,
                        list_id,
                        first_seen_at,
                        last_seen_at,
                        message_count,
                        latest_message_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        mailbox,
                        recipient_alias,
                        identity_key,
                        observation.sender_name.strip(),
                        sender_address,
                        observation.list_id.strip() if observation.list_id else None,
                        event_at,
                        event_at,
                        message_id,
                    ),
                )
                newsletter_id = int(cursor.lastrowid)
                unsubscribed_at = None
            else:
                newsletter_id = int(row["id"])
                unsubscribed_at = (
                    int(row["unsubscribed_at"])
                    if row["unsubscribed_at"] is not None
                    else None
                )

            event_key = self._event_key(observation)
            inserted = connection.execute(
                """
                INSERT OR IGNORE INTO newsletter_messages (
                    event_key,
                    newsletter_id,
                    message_id,
                    event_at
                ) VALUES (?, ?, ?, ?)
                """,
                (event_key, newsletter_id, message_id, event_at),
            ).rowcount

            clear_unsubscribed = unsubscribed_at is not None and event_at > unsubscribed_at
            connection.execute(
                """
                UPDATE newsletters
                SET sender_name = CASE WHEN ? THEN ? ELSE sender_name END,
                    sender_address = CASE WHEN ? THEN ? ELSE sender_address END,
                    list_id = COALESCE(?, list_id),
                    first_seen_at = MIN(first_seen_at, ?),
                    last_seen_at = MAX(last_seen_at, ?),
                    message_count = message_count + ?,
                    latest_message_id = CASE
                        WHEN ? >= last_seen_at THEN ?
                        ELSE latest_message_id
                    END,
                    unsubscribed_at = CASE WHEN ? THEN NULL ELSE unsubscribed_at END
                WHERE id = ?
                """,
                (
                    1 if observation.headers_resolved else 0,
                    observation.sender_name.strip(),
                    1 if observation.headers_resolved else 0,
                    sender_address,
                    observation.list_id.strip() if observation.list_id else None,
                    event_at,
                    event_at,
                    1 if inserted else 0,
                    event_at,
                    message_id,
                    1 if clear_unsubscribed else 0,
                    newsletter_id,
                ),
            )

            if observation.unsubscribe_url:
                url = observation.unsubscribe_url.strip()
                connection.execute(
                    """
                    INSERT INTO newsletter_unsubscribe_links (
                        newsletter_id,
                        url,
                        one_click,
                        mailto,
                        source_message_id,
                        discovered_at,
                        last_seen_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(newsletter_id, url) DO UPDATE SET
                        one_click = MAX(one_click, excluded.one_click),
                        mailto = COALESCE(excluded.mailto, mailto),
                        source_message_id = CASE
                            WHEN excluded.last_seen_at >= last_seen_at
                                THEN excluded.source_message_id
                            ELSE source_message_id
                        END,
                        last_seen_at = MAX(last_seen_at, excluded.last_seen_at)
                    """,
                    (
                        newsletter_id,
                        url,
                        1 if observation.one_click else 0,
                        observation.unsubscribe_mailto,
                        message_id,
                        event_at,
                        event_at,
                    ),
                )
                self._trim_links(connection, newsletter_id)

            return newsletter_id

    async def headers_checked(self, observation: NewsletterObservation) -> bool:
        return await asyncio.to_thread(self._headers_checked, observation)

    def _headers_checked(self, observation: NewsletterObservation) -> bool:
        with self._connect() as connection:
            if not self._history_allows(
                connection,
                observation.mailbox,
                int(observation.event_at),
            ):
                return True
            row = connection.execute(
                """
                SELECT headers_checked
                FROM newsletter_messages
                WHERE event_key = ?
                """,
                (self._event_key(observation),),
            ).fetchone()
        return bool(row and row["headers_checked"])

    async def mark_headers_checked(self, observation: NewsletterObservation) -> None:
        await asyncio.to_thread(self._mark_headers_checked, observation)

    def _mark_headers_checked(self, observation: NewsletterObservation) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE newsletter_messages
                SET headers_checked = 1
                WHERE event_key = ?
                """,
                (self._event_key(observation),),
            )

    @staticmethod
    def _trim_links(connection: sqlite3.Connection, newsletter_id: int) -> None:
        connection.execute(
            """
            DELETE FROM newsletter_unsubscribe_links
            WHERE newsletter_id = ?
              AND id NOT IN (
                  SELECT id
                  FROM newsletter_unsubscribe_links
                  WHERE newsletter_id = ?
                  ORDER BY last_seen_at DESC, id DESC
                  LIMIT ?
              )
            """,
            (newsletter_id, newsletter_id, MAX_UNSUBSCRIBE_LINKS),
        )

    async def list_for_mailbox(self, mailbox: str) -> list[Newsletter]:
        return await asyncio.to_thread(self._list_for_mailbox, mailbox)

    def _list_for_mailbox(self, mailbox: str) -> list[Newsletter]:
        mailbox = mailbox.strip().casefold()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM newsletters
                WHERE mailbox = ?
                ORDER BY last_seen_at DESC, sender_address ASC
                """,
                (mailbox,),
            ).fetchall()
            if not rows:
                return []
            ids = [int(row["id"]) for row in rows]
            placeholders = ",".join("?" for _ in ids)
            link_rows = connection.execute(
                f"""
                SELECT *
                FROM newsletter_unsubscribe_links
                WHERE newsletter_id IN ({placeholders})
                ORDER BY newsletter_id, last_seen_at DESC, id DESC
                """,
                ids,
            ).fetchall()

        links_by_newsletter: dict[int, list[NewsletterLink]] = {}
        for row in link_rows:
            link = self._link_from_row(row)
            links_by_newsletter.setdefault(link.newsletter_id, []).append(link)
        return [
            self._newsletter_from_row(
                row,
                tuple(links_by_newsletter.get(int(row["id"]), ())),
            )
            for row in rows
        ]

    async def get(self, newsletter_id: int, mailbox: str) -> Newsletter | None:
        return await asyncio.to_thread(self._get, newsletter_id, mailbox)

    def _get(self, newsletter_id: int, mailbox: str) -> Newsletter | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM newsletters WHERE id = ? AND mailbox = ?",
                (newsletter_id, mailbox.strip().casefold()),
            ).fetchone()
            if row is None:
                return None
            links = tuple(
                self._link_from_row(link_row)
                for link_row in connection.execute(
                    """
                    SELECT *
                    FROM newsletter_unsubscribe_links
                    WHERE newsletter_id = ?
                    ORDER BY last_seen_at DESC, id DESC
                    """,
                    (newsletter_id,),
                ).fetchall()
            )
        return self._newsletter_from_row(row, links)

    async def mark_unsubscribed(
        self,
        newsletter_id: int,
        mailbox: str,
        when: int | None = None,
    ) -> None:
        await asyncio.to_thread(
            self._mark_unsubscribed,
            newsletter_id,
            mailbox,
            int(time.time()) if when is None else int(when),
        )

    def _mark_unsubscribed(self, newsletter_id: int, mailbox: str, when: int) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE newsletters
                SET unsubscribed_at = ?
                WHERE id = ? AND mailbox = ?
                """,
                (when, newsletter_id, mailbox.strip().casefold()),
            )

    @staticmethod
    def _link_from_row(row: sqlite3.Row) -> NewsletterLink:
        return NewsletterLink(
            id=int(row["id"]),
            newsletter_id=int(row["newsletter_id"]),
            url=str(row["url"]),
            one_click=bool(row["one_click"]),
            mailto=str(row["mailto"]) if row["mailto"] is not None else None,
            source_message_id=(
                str(row["source_message_id"])
                if row["source_message_id"] is not None
                else None
            ),
            discovered_at=int(row["discovered_at"]),
            last_seen_at=int(row["last_seen_at"]),
        )

    @staticmethod
    def _newsletter_from_row(
        row: sqlite3.Row,
        links: tuple[NewsletterLink, ...],
    ) -> Newsletter:
        return Newsletter(
            id=int(row["id"]),
            mailbox=str(row["mailbox"]),
            recipient_alias=str(row["recipient_alias"]),
            identity_key=str(row["identity_key"]),
            sender_name=str(row["sender_name"]),
            sender_address=str(row["sender_address"]),
            list_id=str(row["list_id"]) if row["list_id"] is not None else None,
            first_seen_at=int(row["first_seen_at"]),
            last_seen_at=int(row["last_seen_at"]),
            message_count=int(row["message_count"]),
            latest_message_id=(
                str(row["latest_message_id"])
                if row["latest_message_id"] is not None
                else None
            ),
            unsubscribed_at=(
                int(row["unsubscribed_at"])
                if row["unsubscribed_at"] is not None
                else None
            ),
            links=links,
        )
