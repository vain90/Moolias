from __future__ import annotations

from dataclasses import replace

from moolias.newsletter_store import NewsletterObservation, NewsletterStore


def observation(index: int, *, url: str | None = None) -> NewsletterObservation:
    return NewsletterObservation(
        mailbox="user@example.org",
        recipient_alias="shop@example.org",
        identity_key="sender:news@example.net",
        sender_name="Example News",
        sender_address="news@example.net",
        list_id=None,
        message_id=f"message-{index}@example.net",
        event_at=1_780_000_000 + index,
        unsubscribe_url=url,
        unsubscribe_mailto="mailto:leave@example.net" if url else None,
        one_click=bool(url),
    )


async def test_store_keeps_only_three_newest_different_links(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()

    for index in range(1, 5):
        await store.record(
            observation(index, url=f"https://example.net/unsubscribe/token-{index}")
        )

    newsletters = await store.list_for_mailbox("USER@example.org")
    assert len(newsletters) == 1
    newsletter = newsletters[0]
    assert newsletter.message_count == 4
    assert [link.url for link in newsletter.links] == [
        "https://example.net/unsubscribe/token-4",
        "https://example.net/unsubscribe/token-3",
        "https://example.net/unsubscribe/token-2",
    ]
    assert newsletter.latest_message_id == "message-4@example.net"


async def test_duplicate_message_does_not_inflate_count_but_can_add_link(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()

    base = observation(1)
    await store.record(base)
    await store.record(
        replace(
            base,
            unsubscribe_url="https://example.net/unsubscribe/recovered",
            one_click=True,
        )
    )

    newsletter = (await store.list_for_mailbox("user@example.org"))[0]
    assert newsletter.message_count == 1
    assert newsletter.latest_link is not None
    assert newsletter.latest_link.url.endswith("/recovered")


async def test_header_lookup_state_is_persisted_per_message(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()
    item = observation(1)
    await store.record(item)

    assert await store.headers_checked(item) is False
    await store.mark_headers_checked(item)
    assert await store.headers_checked(item) is True

    second = observation(2)
    await store.record(second)
    assert await store.headers_checked(second) is False


async def test_newsletter_without_recoverable_link_stays_visible(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()
    await store.record(observation(1))

    newsletter = (await store.list_for_mailbox("user@example.org"))[0]
    assert newsletter.message_count == 1
    assert newsletter.links == ()
    assert newsletter.direct_unsubscribe_available is False


async def test_new_message_after_unsubscribe_reactivates_newsletter(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()
    newsletter_id = await store.record(
        observation(1, url="https://example.net/unsubscribe/one")
    )
    await store.mark_unsubscribed(newsletter_id, "user@example.org", when=1_780_000_001)

    await store.record(
        observation(3, url="https://example.net/unsubscribe/two")
    )

    newsletter = await store.get(newsletter_id, "user@example.org")
    assert newsletter is not None
    assert newsletter.unsubscribed_at is None


async def test_from_now_watermark_ignores_older_history_and_header_lookup(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()
    await store.set_history_since("user@example.org", 1_780_000_010)

    old_item = observation(1, url="https://example.net/unsubscribe/old")
    assert await store.record(old_item) == 0
    assert await store.headers_checked(old_item) is True
    assert await store.list_for_mailbox("user@example.org") == []

    new_item = observation(11, url="https://example.net/unsubscribe/new")
    newsletter_id = await store.record(new_item)
    assert newsletter_id > 0
    assert await store.headers_checked(new_item) is False
    newsletters = await store.list_for_mailbox("user@example.org")
    assert len(newsletters) == 1
    assert newsletters[0].latest_link is not None
    assert newsletters[0].latest_link.url.endswith("/new")


async def test_backfill_watermark_allows_available_history(tmp_path):
    store = NewsletterStore(tmp_path / "newsletters.sqlite3")
    await store.initialize()
    await store.set_history_since("user@example.org", 0)

    old_item = observation(1)
    newsletter_id = await store.record(old_item)
    assert newsletter_id > 0
    assert await store.headers_checked(old_item) is False
    assert await store.history_since("user@example.org") == 0
