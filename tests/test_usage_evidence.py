from moolias.aliases import AliasRecord
from moolias.config import Settings
from moolias.stats import StatsStore
from moolias.usage import UsageCollector
from moolias.usage_evidence import UsageEvidenceEvent, UsageEvidenceStore


def settings(db_path: str, *, history_count: int = 100) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_USAGE_STATS=True,
        MOOLIAS_USAGE_TAG="moolias-stats",
        MOOLIAS_USAGE_DB_PATH=db_path,
        MOOLIAS_USAGE_HISTORY_COUNT=history_count,
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


async def test_usage_evidence_merges_backfill_and_live_observations(tmp_path):
    store = UsageEvidenceStore(tmp_path / "usage.sqlite3")

    await store.record_events(
        [
            UsageEvidenceEvent("user@example.org", "shop@example.org", 100),
            UsageEvidenceEvent("user@example.org", "shop@example.org", 120),
        ],
        source="backfill",
    )
    await store.record_events(
        [UsageEvidenceEvent("user@example.org", "shop@example.org", 200)],
        source="live",
    )

    evidence = await store.alias_evidence("user@example.org", ["shop@example.org"])
    item = evidence["shop@example.org"]
    assert item.first_seen_at == 100
    assert item.last_seen_at == 200
    assert item.backfill_seen is True
    assert item.live_seen is True

    assert await store.pending_backfills(
        {"user@example.org"},
        history_limit=100,
    ) == {"user@example.org"}
    await store.complete_backfills(
        {"user@example.org"},
        oldest_history_at=50,
        newest_history_at=200,
        history_count=80,
        history_limit=100,
        completed_at=250,
    )
    assert await store.pending_backfills(
        {"user@example.org"},
        history_limit=100,
    ) == set()
    assert await store.pending_backfills(
        {"user@example.org"},
        history_limit=500,
    ) == {"user@example.org"}


class BackfillMailcow:
    def __init__(self, event_at: int) -> None:
        self.event_at = event_at

    async def list_domains(self):
        return [{"domain": "example.org", "tags": ["moolias-stats"]}]

    async def list_mailboxes(self):
        return [
            {"username": "user@example.org", "domain": "example.org", "tags": []}
        ]

    async def list_aliases(self):
        return [
            AliasRecord(
                id=1,
                address="shop@example.org",
                goto="user@example.org",
                domain="example.org",
                active=True,
                private_comment="",
                public_comment="Shop",
            ),
            AliasRecord(
                id=2,
                address="user@example.org",
                goto="user@example.org",
                domain="example.org",
                active=True,
                private_comment="",
                public_comment="",
            ),
        ]

    async def get_alias(self, alias_id: int):
        return next(alias for alias in await self.list_aliases() if alias.id == alias_id)

    async def mark_reserved_alias_used(self, alias_id: int) -> None:
        raise AssertionError(f"Alias {alias_id} is not reserved")

    async def get_rspamd_history(self, count: int):
        assert count == 100
        return [
            {
                "unix_time": self.event_at,
                "action": "no action",
                "sender_smtp": "sender@example.net",
                "rcpt_smtp": ["shop@example.org"],
                "message-id": "historical@example.net",
                "user": "unknown",
            }
        ]


async def test_collector_backfills_usage_before_tracking_without_changing_counts(tmp_path):
    db_path = tmp_path / "usage.sqlite3"
    stats = StatsStore(str(db_path))
    await stats.initialize()
    tracking_started_at = await stats.tracking_started_at()
    historical_at = tracking_started_at - 7 * 24 * 60 * 60

    collector = UsageCollector(
        settings(str(db_path)),
        BackfillMailcow(historical_at),
        stats,
    )

    assert await collector.collect_once() == 0
    assert await stats.alias_usage("user@example.org", ["shop@example.org"]) == {}

    evidence_store = UsageEvidenceStore(db_path)
    evidence = await evidence_store.alias_evidence(
        "user@example.org",
        ["shop@example.org"],
    )
    item = evidence["shop@example.org"]
    assert item.first_seen_at == historical_at
    assert item.last_seen_at == historical_at
    assert item.backfill_seen is True
    assert item.live_seen is False

    backfill = await evidence_store.backfill_state("user@example.org")
    assert backfill is not None
    assert backfill.oldest_history_at == historical_at
    assert backfill.newest_history_at == historical_at
    assert backfill.history_count == 1
    assert backfill.history_limit == 100
