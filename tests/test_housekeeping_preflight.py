from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from moolias.housekeeping import HousekeepingSchemaError, run_housekeeping


def test_apply_preflights_newsletter_schema_before_stats_mutation(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    newsletters = tmp_path / "newsletters.sqlite3"

    con = sqlite3.connect(stats)
    try:
        con.execute(
            """
            CREATE TABLE alias_usage_evidence (
                mailbox TEXT NOT NULL,
                alias TEXT NOT NULL,
                first_seen_at INTEGER NOT NULL,
                last_seen_at INTEGER NOT NULL,
                backfill_seen INTEGER NOT NULL DEFAULT 0,
                live_seen INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (mailbox, alias)
            )
            """
        )
        con.execute(
            """
            INSERT INTO alias_usage_evidence
            VALUES ('user@example.org', 'stale@example.org', 1, 2, 1, 1)
            """
        )
        con.commit()
    finally:
        con.close()

    con = sqlite3.connect(newsletters)
    try:
        con.execute("PRAGMA foreign_keys = ON")
        con.executescript(
            """
            CREATE TABLE newsletters (
                id INTEGER PRIMARY KEY,
                mailbox TEXT NOT NULL,
                recipient_alias TEXT NOT NULL,
                identity_key TEXT NOT NULL
            );
            CREATE TABLE newsletter_future_child (
                id INTEGER PRIMARY KEY,
                newsletter_id INTEGER NOT NULL
                    REFERENCES newsletters(id) ON DELETE CASCADE
            );
            """
        )
        con.commit()
    finally:
        con.close()

    with pytest.raises(HousekeepingSchemaError, match="unreviewed child table"):
        run_housekeeping(
            stats_db=stats,
            newsletter_db=newsletters,
            valid_addresses={"user@example.org"},
            apply=True,
        )

    con = sqlite3.connect(stats)
    try:
        remaining = con.execute(
            "SELECT COUNT(*) FROM alias_usage_evidence WHERE alias = ?",
            ("stale@example.org",),
        ).fetchone()[0]
    finally:
        con.close()

    assert remaining == 1
