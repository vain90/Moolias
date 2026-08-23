from __future__ import annotations

import pytest

from moolias.aliases import AliasRecord
from moolias.stats import StatsStore
from moolias.stats_history import (
    HistoricalSenderEvent,
    HistoricalUsageEvent,
    StatsHistoryStore,
    perform_pending_backfill,
)
from moolias.stats_mode import StatsMode


@pytest.mark.asyncio
async def test_history_coverage_keeps_separate_mode_start_dates(tmp_path) -> None:
    path = tmp_path / "usage.sqlite3"
    stats_store = StatsStore(str(path))
    await stats_store.initialize()
    store = StatsHistoryStore(path)
    mailbox = "user@example.org"
    alias = "shop@example.org"

    await store.sync_mode(mailbox, StatsMode.BASIC, started_at=200)
    await store.request_backfill(mailbox, StatsMode.BASIC, requested_at=201)
    request = await store.pending_request(mailbox)
    assert request is not None
    await store.record_usage_events(
        [
            HistoricalUsageEvent("r1", mailbox, alias, "received", 100),
            HistoricalUsageEvent("s1", mailbox, alias, "sent", 110),
        ]
    )
    await store.complete_backfill(
        request,
        oldest_history_at=90,
        history_count=10,
        history_limit=1000,
        completed_at=210,
    )

    await store.sync_mode(mailbox, StatsMode.DOMAIN, started_at=300)
    await store.request_backfill(mailbox, StatsMode.DOMAIN, requested_at=301)
    request = await store.pending_request(mailbox)
    assert request is not None
    await store.record_sender_events(
        [
            HistoricalSenderEvent(
                "d1",
                mailbox,
                alias,
                "example.net",
                None,
                StatsMode.DOMAIN,
                250,
            )
        ]
    )
    await store.complete_backfill(
        request,
        oldest_history_at=150,
        history_count=20,
        history_limit=1000,
        completed_at=310,
    )

    await store.sync_mode(mailbox, StatsMode.FULL, started_at=400)
    await store.request_backfill(mailbox, StatsMode.FULL, requested_at=401)
    request = await store.pending_request(mailbox)
    assert request is not None
    await store.record_sender_events(
        [
            HistoricalSenderEvent(
                "f1",
                mailbox,
                alias,
                "example.net",
                "news@example.net",
                StatsMode.FULL,
                350,
            )
        ]
    )
    await store.complete_backfill(
        request,
        oldest_history_at=330,
        history_count=30,
        history_limit=1000,
        completed_at=410,
    )

    coverage = await store.coverage(mailbox)
    assert coverage[StatsMode.BASIC].live_started_at == 200
    assert coverage[StatsMode.BASIC].start_at == 90
    assert coverage[StatsMode.DOMAIN].live_started_at == 300
    assert coverage[StatsMode.DOMAIN].start_at == 150
    assert coverage[StatsMode.FULL].live_started_at == 400
    assert coverage[StatsMode.FULL].start_at == 330

    usage = await store.alias_usage(mailbox, [alias])
    assert usage[alias].received_count == 1
    assert usage[alias].sent_count == 1

    await store.sync_mode(mailbox, StatsMode.DOMAIN, started_at=500)
    downgraded = await store.coverage(mailbox)
    assert StatsMode.BASIC in downgraded
    assert StatsMode.DOMAIN in downgraded
    assert StatsMode.FULL not in downgraded
    assert not await store.sender_usage(mailbox, [alias], level=StatsMode.FULL)


class _Settings:
    usage_history_count = 1000


class _Mailcow:
    async def get_rspamd_history(self, count: int):
        assert count == 1000
        return [
            {
                "action": "clean",
                "message-id": "incoming-1",
                "sender_mime": "offers@example.net",
                "sender_smtp": "offers@example.net",
                "rcpt_smtp": ["shop@example.org"],
                "unix_time": 100,
            },
            {
                "action": "clean",
                "message-id": "outgoing-1",
                "user": "user@example.org",
                "sender_mime": "shop@example.org",
                "sender_smtp": "shop@example.org",
                "rcpt_smtp": ["customer@example.com"],
                "unix_time": 110,
            },
        ]


@pytest.mark.asyncio
async def test_pending_backfill_imports_only_data_allowed_by_full_mode(tmp_path) -> None:
    path = tmp_path / "usage.sqlite3"
    stats_store = StatsStore(str(path))
    await stats_store.initialize()
    history_store = StatsHistoryStore(path)
    mailbox = "user@example.org"
    alias = AliasRecord(
        id=1,
        address="shop@example.org",
        goto=mailbox,
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="Shop",
        sogo_visible=False,
        sender_allowed=True,
    )

    await history_store.sync_mode(mailbox, StatsMode.FULL, started_at=200)
    await history_store.request_backfill(mailbox, StatsMode.FULL, requested_at=201)
    result = await perform_pending_backfill(
        _Settings(),
        _Mailcow(),
        stats_store,
        mailbox,
        [alias],
    )

    assert result == {"usage": 2, "senders": 2, "history_count": 2}
    assert await history_store.pending_request(mailbox) is None

    usage = await history_store.alias_usage(mailbox, [alias.address])
    assert usage[alias.address].received_count == 1
    assert usage[alias.address].sent_count == 1

    domains = await history_store.sender_usage(
        mailbox,
        [alias.address],
        level=StatsMode.DOMAIN,
    )
    assert domains[alias.address][0].sender_key == "example.net"
    assert domains[alias.address][0].sender_address is None

    full = await history_store.sender_usage(
        mailbox,
        [alias.address],
        level=StatsMode.FULL,
    )
    assert full[alias.address][0].sender_key == "offers@example.net"
    assert full[alias.address][0].sender_address == "offers@example.net"
