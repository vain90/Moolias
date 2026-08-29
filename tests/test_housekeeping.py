from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from moolias.housekeeping import (
    HousekeepingSchemaError,
    load_mailcow_inventory,
    run_housekeeping,
)


def create_stats_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE alias_usage (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                received_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (mailbox, alias)
            );
            CREATE TABLE sender_usage (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                sender_key TEXT NOT NULL,
                PRIMARY KEY (mailbox, alias, sender_key)
            );
            CREATE TABLE sender_expectations (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                sender_key TEXT NOT NULL,
                expected INTEGER NOT NULL,
                PRIMARY KEY (mailbox, alias, sender_key)
            );
            CREATE TABLE sender_alias_settings (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                ignore_unexpected INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (mailbox, alias)
            );
            CREATE TABLE alias_usage_evidence (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                backfill_seen INTEGER NOT NULL DEFAULT 0,
                live_seen INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (mailbox, alias)
            );
            CREATE TABLE stats_history_alias_usage (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                received_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (mailbox, alias)
            );
            CREATE TABLE stats_history_sender_domain (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                sender_domain TEXT NOT NULL,
                PRIMARY KEY (mailbox, alias, sender_domain)
            );
            CREATE TABLE stats_history_sender_full (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                sender_address TEXT NOT NULL,
                sender_domain TEXT NOT NULL,
                PRIMARY KEY (mailbox, alias, sender_address)
            );
            CREATE TABLE sender_spam_evidence (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                detail_level TEXT NOT NULL,
                sender_key TEXT NOT NULL,
                PRIMARY KEY (mailbox, alias, detail_level, sender_key)
            );
            CREATE TABLE alias_workflows (
                id INTEGER PRIMARY KEY,
                old_address TEXT,
                new_address TEXT NOT NULL,
                completed_at INTEGER,
                bypass_expires_at INTEGER NOT NULL,
                bypass_cleared_at INTEGER
            );
            """
        )
        con.commit()
    finally:
        con.close()


def create_newsletter_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(
            """
            CREATE TABLE newsletters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mailbox TEXT NOT NULL,
                recipient_alias TEXT NOT NULL,
                identity_key TEXT NOT NULL,
                UNIQUE (mailbox, recipient_alias, identity_key)
            );
            CREATE TABLE newsletter_messages (
                event_key TEXT PRIMARY KEY,
                newsletter_id INTEGER NOT NULL
                    REFERENCES newsletters(id) ON DELETE CASCADE,
                message_id TEXT NOT NULL
            );
            CREATE TABLE newsletter_unsubscribe_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                newsletter_id INTEGER NOT NULL
                    REFERENCES newsletters(id) ON DELETE CASCADE,
                url TEXT NOT NULL
            );
            CREATE TABLE newsletter_mailbox_scan_policy (
                mailbox TEXT PRIMARY KEY,
                history_since INTEGER NOT NULL
            );
            """
        )
        con.commit()
    finally:
        con.close()


def insert_stats_rows(path: Path, mailbox: str, alias: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("INSERT INTO alias_usage VALUES (?, ?, 1)", (mailbox, alias))
        con.execute("INSERT INTO sender_usage VALUES (?, ?, ?)", (mailbox, alias, "example.org"))
        con.execute(
            "INSERT INTO sender_expectations VALUES (?, ?, ?, 1)",
            (mailbox, alias, "example.org"),
        )
        con.execute("INSERT INTO sender_alias_settings VALUES (?, ?, 1)", (mailbox, alias))
        con.execute(
            "INSERT INTO alias_usage_evidence VALUES (?, ?, 1, 2, 1, 1)",
            (mailbox, alias),
        )
        con.execute("INSERT INTO stats_history_alias_usage VALUES (?, ?, 2)", (mailbox, alias))
        con.execute(
            "INSERT INTO stats_history_sender_domain VALUES (?, ?, ?)",
            (mailbox, alias, "example.org"),
        )
        con.execute(
            "INSERT INTO stats_history_sender_full VALUES (?, ?, ?, ?)",
            (mailbox, alias, "sender@example.org", "example.org"),
        )
        con.execute(
            "INSERT INTO sender_spam_evidence VALUES (?, ?, ?, ?)",
            (mailbox, alias, "domain", "example.org"),
        )
        con.commit()
    finally:
        con.close()


def insert_newsletter(path: Path, mailbox: str, alias: str, suffix: str) -> None:
    con = sqlite3.connect(path)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        cursor = con.execute(
            "INSERT INTO newsletters (mailbox, recipient_alias, identity_key) VALUES (?, ?, ?)",
            (mailbox, alias, f"sender:{suffix}@example.org"),
        )
        newsletter_id = int(cursor.lastrowid)
        con.execute(
            "INSERT INTO newsletter_messages VALUES (?, ?, ?)",
            (f"event-{suffix}", newsletter_id, f"msg-{suffix}"),
        )
        con.execute(
            "INSERT INTO newsletter_unsubscribe_links (newsletter_id, url) VALUES (?, ?)",
            (newsletter_id, f"https://example.org/u/{suffix}"),
        )
        con.commit()
    finally:
        con.close()


def scalar(path: Path, query: str, params: tuple = ()) -> int:
    con = sqlite3.connect(path)
    try:
        return int(con.execute(query, params).fetchone()[0])
    finally:
        con.close()


def test_dry_run_finds_all_known_rows_without_mutating(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    insert_stats_rows(stats, "user@example.org", "stale@example.org")
    insert_stats_rows(stats, "user@example.org", "live@example.org")
    insert_newsletter(news, "user@example.org", "stale@example.org", "stale")
    insert_newsletter(news, "user@example.org", "live@example.org", "live")

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=news,
        valid_addresses={"live@example.org", "user@example.org"},
    )

    assert not report.applied
    assert [entry.address for entry in report.candidates] == ["stale@example.org"]
    counts = dict(report.candidates[0].counts)
    assert counts["stats.alias_usage"] == 1
    assert counts["stats.alias_usage_evidence"] == 1
    assert counts["stats.sender_usage"] == 1
    assert counts["stats.sender_expectations"] == 1
    assert counts["stats.sender_alias_settings"] == 1
    assert counts["stats.stats_history_alias_usage"] == 1
    assert counts["stats.stats_history_sender_domain"] == 1
    assert counts["stats.stats_history_sender_full"] == 1
    assert counts["stats.sender_spam_evidence"] == 1
    assert counts["newsletter.newsletters"] == 1
    assert counts["newsletter.newsletter_messages"] == 1
    assert counts["newsletter.newsletter_unsubscribe_links"] == 1
    assert scalar(stats, "SELECT COUNT(*) FROM alias_usage") == 2
    assert scalar(news, "SELECT COUNT(*) FROM newsletters") == 2


def test_apply_deletes_orphan_rows_and_newsletter_children(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    insert_stats_rows(stats, "user@example.org", "stale@example.org")
    insert_stats_rows(stats, "user@example.org", "live@example.org")
    insert_newsletter(news, "user@example.org", "stale@example.org", "stale")
    insert_newsletter(news, "user@example.org", "live@example.org", "live")

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=news,
        valid_addresses={"live@example.org", "user@example.org"},
        apply=True,
    )

    assert report.applied
    assert [entry.address for entry in report.candidates] == ["stale@example.org"]
    for table in (
        "alias_usage",
        "sender_usage",
        "sender_expectations",
        "sender_alias_settings",
        "alias_usage_evidence",
        "stats_history_alias_usage",
        "stats_history_sender_domain",
        "stats_history_sender_full",
        "sender_spam_evidence",
    ):
        assert (
            scalar(
                stats,
                f"SELECT COUNT(*) FROM {table} WHERE alias = ?",
                ("stale@example.org",),
            )
            == 0
        )
        assert (
            scalar(
                stats,
                f"SELECT COUNT(*) FROM {table} WHERE alias = ?",
                ("live@example.org",),
            )
            == 1
        )
    assert (
        scalar(
            news,
            "SELECT COUNT(*) FROM newsletters WHERE recipient_alias = ?",
            ("stale@example.org",),
        )
        == 0
    )
    assert scalar(news, "SELECT COUNT(*) FROM newsletter_messages") == 1
    assert scalar(news, "SELECT COUNT(*) FROM newsletter_unsubscribe_links") == 1

    second = run_housekeeping(
        stats_db=stats,
        newsletter_db=news,
        valid_addresses={"live@example.org", "user@example.org"},
        apply=True,
    )
    assert second.candidates == ()


def test_active_workflow_protects_stats_and_newsletter_rows(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    insert_stats_rows(stats, "user@example.org", "pending@example.org")
    insert_newsletter(news, "user@example.org", "pending@example.org", "pending")
    con = sqlite3.connect(stats)
    try:
        con.execute(
            """
            INSERT INTO alias_workflows (
                id, old_address, new_address, completed_at,
                bypass_expires_at, bypass_cleared_at
            ) VALUES (1, NULL, ?, NULL, ?, NULL)
            """,
            ("pending@example.org", 2_000),
        )
        con.commit()
    finally:
        con.close()

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=news,
        valid_addresses={"user@example.org"},
        apply=True,
        now=1_000,
    )

    assert report.candidates == ()
    assert [entry.address for entry in report.protected] == ["pending@example.org"]
    assert (
        scalar(
            stats,
            "SELECT COUNT(*) FROM alias_usage WHERE alias = ?",
            ("pending@example.org",),
        )
        == 1
    )
    assert (
        scalar(
            news,
            "SELECT COUNT(*) FROM newsletters WHERE recipient_alias = ?",
            ("pending@example.org",),
        )
        == 1
    )


def test_live_uncleared_bypass_protects_completed_workflow(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    insert_stats_rows(stats, "user@example.org", "pending-clear@example.org")
    con = sqlite3.connect(stats)
    try:
        con.execute(
            """
            INSERT INTO alias_workflows (
                id, old_address, new_address, completed_at,
                bypass_expires_at, bypass_cleared_at
            ) VALUES (1, NULL, ?, 900, 2000, NULL)
            """,
            ("pending-clear@example.org",),
        )
        con.commit()
    finally:
        con.close()

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=news,
        valid_addresses={"user@example.org"},
        apply=True,
        now=1_000,
    )
    assert report.candidates == ()
    assert [entry.address for entry in report.protected] == ["pending-clear@example.org"]


def test_completed_replacement_history_is_retained_but_does_not_protect_stale_data(
    tmp_path: Path,
) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    insert_stats_rows(stats, "user@example.org", "old@example.org")
    con = sqlite3.connect(stats)
    try:
        con.execute(
            """
            INSERT INTO alias_workflows (
                id, old_address, new_address, completed_at,
                bypass_expires_at, bypass_cleared_at
            ) VALUES (1, ?, ?, 900, 800, 850)
            """,
            ("old@example.org", "new@example.org"),
        )
        con.commit()
    finally:
        con.close()

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=news,
        valid_addresses={"user@example.org", "new@example.org"},
        apply=True,
        now=1_000,
    )
    assert [entry.address for entry in report.candidates] == ["old@example.org"]
    assert (
        scalar(
            stats,
            "SELECT COUNT(*) FROM alias_usage WHERE alias = ?",
            ("old@example.org",),
        )
        == 0
    )
    assert (
        scalar(
            stats,
            "SELECT COUNT(*) FROM alias_workflows WHERE old_address = ?",
            ("old@example.org",),
        )
        == 1
    )


def test_missing_newsletter_db_is_normal(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    create_stats_db(stats)
    insert_stats_rows(stats, "user@example.org", "stale@example.org")

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=tmp_path / "does-not-exist.sqlite3",
        valid_addresses={"user@example.org"},
    )
    assert [entry.address for entry in report.candidates] == ["stale@example.org"]
    assert not (tmp_path / "does-not-exist.sqlite3").exists()


def test_unknown_alias_reference_fails_closed_before_apply(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    insert_stats_rows(stats, "user@example.org", "stale@example.org")
    con = sqlite3.connect(stats)
    try:
        con.execute("CREATE TABLE future_feature (alias TEXT NOT NULL)")
        con.execute("INSERT INTO future_feature VALUES ('stale@example.org')")
        con.commit()
    finally:
        con.close()

    with pytest.raises(HousekeepingSchemaError, match=r"future_feature\.alias"):
        run_housekeeping(
            stats_db=stats,
            newsletter_db=news,
            valid_addresses={"user@example.org"},
            apply=True,
        )
    assert (
        scalar(
            stats,
            "SELECT COUNT(*) FROM alias_usage WHERE alias = ?",
            ("stale@example.org",),
        )
        == 1
    )


@dataclass
class FakeAlias:
    address: str


class FakeClient:
    async def list_aliases(self):
        return [FakeAlias("alias@example.org")]

    async def list_mailboxes(self):
        return [{"username": "Primary@Example.org"}]


def test_inventory_includes_primary_mailbox_addresses() -> None:
    inventory = asyncio.run(load_mailcow_inventory(FakeClient()))
    assert inventory.addresses == frozenset({"alias@example.org", "primary@example.org"})
    assert inventory.alias_count == 1
    assert inventory.mailbox_count == 1


def test_unknown_newsletter_child_fails_closed(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    create_newsletter_db(news)
    con = sqlite3.connect(news)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.execute(
            """
            CREATE TABLE newsletter_future_child (
                id INTEGER PRIMARY KEY,
                newsletter_id INTEGER NOT NULL
                    REFERENCES newsletters(id) ON DELETE CASCADE
            )
            """
        )
        con.commit()
    finally:
        con.close()

    with pytest.raises(HousekeepingSchemaError, match="unreviewed child table"):
        run_housekeeping(
            stats_db=stats,
            newsletter_db=news,
            valid_addresses={"user@example.org"},
            apply=True,
        )


def test_newsletter_child_without_cascade_fails_closed(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    news = tmp_path / "news.sqlite3"
    create_stats_db(stats)
    con = sqlite3.connect(news)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(
            """
            CREATE TABLE newsletters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mailbox TEXT NOT NULL,
                recipient_alias TEXT NOT NULL,
                identity_key TEXT NOT NULL
            );
            CREATE TABLE newsletter_messages (
                event_key TEXT PRIMARY KEY,
                newsletter_id INTEGER NOT NULL REFERENCES newsletters(id),
                message_id TEXT NOT NULL
            );
            """
        )
        con.commit()
    finally:
        con.close()

    with pytest.raises(HousekeepingSchemaError, match="ON DELETE CASCADE"):
        run_housekeeping(
            stats_db=stats,
            newsletter_db=news,
            valid_addresses={"user@example.org"},
        )
