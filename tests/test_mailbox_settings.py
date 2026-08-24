from __future__ import annotations

from moolias.mailbox_settings import MailboxSettingsStore


async def test_newsletter_preference_is_tristate_and_per_mailbox(tmp_path):
    path = tmp_path / "moolias-state.sqlite3"
    store = MailboxSettingsStore(path)

    assert await store.newsletter_enabled("alice@example.org") is None
    assert await store.newsletter_enabled("bob@example.org") is None

    await store.set_newsletter_enabled("Alice@Example.org", True)
    await store.set_newsletter_enabled("bob@example.org", False)

    assert await store.newsletter_enabled("alice@example.org") is True
    assert await store.newsletter_enabled("BOB@example.org") is False

    await store.set_newsletter_enabled("alice@example.org", False)
    assert await store.newsletter_enabled("ALICE@example.org") is False

    reopened = MailboxSettingsStore(path)
    assert await reopened.newsletter_enabled("alice@example.org") is False
    assert await reopened.newsletter_enabled("bob@example.org") is False
