from __future__ import annotations

import asyncio
from pathlib import Path

from moolias.alias_workflows import AliasWorkflowStore
from moolias.housekeeping import run_housekeeping
from moolias.newsletter_store import NewsletterStore
from moolias.review_settings import AliasReviewSettingsStore
from moolias.rspamd_spam import RspamdSpamStore
from moolias.stats import StatsStore
from moolias.stats_history import StatsHistoryStore
from moolias.usage_evidence import UsageEvidenceStore


async def _initialize_current_stats_schema(path: Path) -> None:
    await StatsStore(path).initialize()
    await AliasWorkflowStore(path).initialize()
    await AliasReviewSettingsStore(path).ignored_aliases("user@example.org")
    await UsageEvidenceStore(path).pending_backfills(
        {"user@example.org"},
        history_limit=1000,
    )
    await StatsHistoryStore(path).coverage("user@example.org")
    await RspamdSpamStore(path).sync_from_sender_mode_state()


def test_housekeeping_accepts_current_application_store_schemas(tmp_path: Path) -> None:
    stats = tmp_path / "stats.sqlite3"
    newsletters = tmp_path / "newsletters.sqlite3"

    asyncio.run(_initialize_current_stats_schema(stats))
    asyncio.run(NewsletterStore(newsletters).initialize())

    report = run_housekeeping(
        stats_db=stats,
        newsletter_db=newsletters,
        valid_addresses={"user@example.org"},
    )

    assert report.candidates == ()
    assert report.protected == ()
