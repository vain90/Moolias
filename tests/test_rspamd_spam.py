from __future__ import annotations

from types import SimpleNamespace

import pytest

from moolias.rspamd_spam import (
    RspamdSpamStore,
    SenderSpamEvidence,
    SpamEvidenceEvent,
    apply_spam_evidence_to_state,
    spam_events_from_captured_senders,
)
from moolias.stats import SenderEvent
from moolias.stats_mode import StatsMode
from moolias.usage import _event_key


MAILBOX = "user@example.org"
ALIAS = "amazon-k7@example.org"


def _sender_event(item: dict, *, event_at: int) -> SenderEvent:
    return SenderEvent(
        event_key=_event_key("sender-detail", item, ALIAS, event_at),
        mailbox=MAILBOX,
        alias=ALIAS,
        sender_domain="amazon.de",
        sender_address="newsletter@amazon.de",
        mode="full",
        event_at=event_at,
    )


def test_rspamd_action_controls_spam_brake_instead_of_raw_score() -> None:
    clean = {
        "action": "clean",
        "message-id": "clean-high-score",
        "score": 99.0,
        "rcpt_smtp": [ALIAS],
        "unix_time": 100,
    }
    spam = {
        "action": "add header",
        "message-id": "spam-low-score",
        "score": 0.5,
        "rcpt_smtp": [ALIAS],
        "unix_time": 110,
    }

    events = spam_events_from_captured_senders(
        [clean, spam],
        [
            _sender_event(clean, event_at=100),
            _sender_event(spam, event_at=110),
        ],
    )

    assert len(events) == 2
    assert {event.detail_level for event in events} == {"domain", "full"}
    assert {event.score for event in events} == {0.5}
    assert {event.event_at for event in events} == {110}


@pytest.mark.asyncio
async def test_spam_evidence_is_aggregated_and_full_data_is_removed_on_downgrade(
    tmp_path,
) -> None:
    store = RspamdSpamStore(tmp_path / "usage.sqlite3")
    events = [
        SpamEvidenceEvent("d1", MAILBOX, ALIAS, "domain", "amazon.de", 100, 7.8),
        SpamEvidenceEvent("d2", MAILBOX, ALIAS, "domain", "amazon.de", 120, 8.4),
        SpamEvidenceEvent(
            "f1",
            MAILBOX,
            ALIAS,
            "full",
            "newsletter@amazon.de",
            100,
            7.8,
        ),
    ]

    assert await store.record_events(events) == 3
    assert await store.record_events(events) == 0

    domain = await store.evidence(MAILBOX, [ALIAS], level=StatsMode.DOMAIN)
    assert domain[ALIAS]["amazon.de"].spam_count == 2
    assert domain[ALIAS]["amazon.de"].max_score == 8.4
    assert domain[ALIAS]["amazon.de"].last_spam_at == 120

    full = await store.evidence(MAILBOX, [ALIAS], level=StatsMode.FULL)
    assert full[ALIAS]["newsletter@amazon.de"].spam_count == 1

    await store.sync_mode(MAILBOX, StatsMode.DOMAIN)
    assert await store.evidence(MAILBOX, [ALIAS], level=StatsMode.FULL) == {}
    domain = await store.evidence(MAILBOX, [ALIAS], level=StatsMode.DOMAIN)
    assert domain[ALIAS]["amazon.de"].spam_count == 2


@pytest.mark.parametrize("manual_expected, expected", [(None, False), (True, True), (False, False)])
def test_one_spam_hit_blocks_only_automatic_recognition(
    manual_expected: bool | None,
    expected: bool,
) -> None:
    row = {
        "sender_key": "newsletter@amazon.de",
        "label": "newsletter@amazon.de",
        "domain": "amazon.de",
        "received_count": 4,
        "last_received_at": 120,
        "expected": True,
        "automatic_expected": True,
        "review_source": "automatic",
        "manual_expected": manual_expected,
        "match_token": "amazon",
    }
    state = {
        "sender_stats": {ALIAS: [row]},
        "assigned_all": [SimpleNamespace(address=ALIAS, active=True)],
        "ignored_aliases": set(),
        "stats_summary": {},
        "action_required": {
            "used_pool": 0,
            "unexpected": 0,
            "unused_90": 0,
            "collector": 0,
            "base_count": 0,
        },
    }
    evidence = {
        ALIAS: {
            "newsletter@amazon.de": SenderSpamEvidence(
                spam_count=1,
                max_score=7.8,
                last_spam_at=120,
            )
        }
    }

    apply_spam_evidence_to_state(state, evidence)

    assert row["rspamd_spam"] is True
    assert row["spam_count"] == 1
    assert row["max_spam_score"] == 7.8
    assert row["automatic_expected"] is False
    assert row["expected"] is expected
    if manual_expected is True:
        assert row["review_source"] == "manual"
        assert state["unexpected_aliases"] == set()
        assert state["stats_summary"]["recognition_rate"] == 100
    else:
        assert ALIAS in state["unexpected_aliases"]
        assert state["stats_summary"]["recognition_rate"] == 0
