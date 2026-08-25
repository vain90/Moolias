from __future__ import annotations

from moolias.aliases import AliasRecord
from moolias.newsletter_forwarding import (
    cache_linked_mailcow_mailboxes,
    direct_mailcow_forwards_to_mailbox,
    forwarded_newsletter_tag,
    forwarded_newsletters_enabled,
    linked_mailcow_mailbox_cache_ready,
    linked_mailcow_mailboxes,
    replace_forwarded_newsletter_tag,
)

MAILBOX = "hidden.pk@kreis-home.de"
BASE_TAG = "moolias-newsletter"


def _alias(
    alias_id: int,
    address: str,
    goto: str,
    *,
    domain: str | None = None,
    active: bool = True,
    catch_all: bool = False,
    name: str = "",
) -> AliasRecord:
    return AliasRecord(
        id=alias_id,
        address=address,
        goto=goto,
        domain=domain or address.rsplit("@", 1)[-1],
        active=active,
        private_comment="",
        public_comment=name,
        is_catch_all=catch_all,
    )


def _mailbox(
    username: str,
    tags: list[str],
    *,
    active: object = "1",
    name: str = "",
) -> dict[str, object]:
    return {
        "username": username,
        "tags": tags,
        "active": active,
        "name": name,
    }


def test_direct_mailcow_forwards_only_returns_external_direct_single_target_aliases():
    cache_linked_mailcow_mailboxes([], MAILBOX, BASE_TAG)
    aliases = [
        _alias(1, "normal@kreis-home.de", MAILBOX),
        _alias(2, "old@example.net", MAILBOX, name="Alte Adresse"),
        _alias(3, "shared@example.net", f"{MAILBOX},other@example.net"),
        _alias(4, "inactive@example.net", MAILBOX, active=False),
        _alias(5, "wrong@example.net", "other@example.net"),
        _alias(6, "@example.net", MAILBOX, catch_all=True),
    ]

    forwarded = direct_mailcow_forwards_to_mailbox(aliases, MAILBOX)

    assert [alias.address for alias in forwarded] == ["old@example.net"]
    assert forwarded[0].name == "Alte Adresse"
    assert forwarded[0].source == "alias"


def test_linked_mailboxes_require_matching_source_and_target_tags():
    mailboxes = [
        _mailbox(
            MAILBOX,
            ["moolias-newsletter-link-private-target"],
            name="Hauptpostfach",
        ),
        _mailbox(
            "old@example.net",
            ["moolias-newsletter-link-private-source"],
            name="Altes Postfach",
        ),
        _mailbox(
            "other@example.net",
            ["moolias-newsletter-link-other-source"],
        ),
        _mailbox(
            "inactive@example.net",
            ["moolias-newsletter-link-private-source"],
            active="0",
        ),
    ]

    linked = linked_mailcow_mailboxes(mailboxes, MAILBOX, BASE_TAG)

    assert [item.address for item in linked] == ["old@example.net"]
    assert linked[0].name == "Altes Postfach"
    assert linked[0].source == "linked_mailbox"


def test_linked_mailbox_cache_is_reused_by_collector_forward_lookup():
    linked = [
        _mailbox(MAILBOX, ["moolias-newsletter-link-legacy-target"]),
        _mailbox(
            "legacy@example.org",
            ["moolias-newsletter-link-legacy-source"],
            name="Legacy Mailbox",
        ),
    ]
    cache_linked_mailcow_mailboxes(linked, MAILBOX, BASE_TAG)

    assert linked_mailcow_mailbox_cache_ready(MAILBOX) is True
    forwarded = direct_mailcow_forwards_to_mailbox([], MAILBOX)

    assert [item.address for item in forwarded] == ["legacy@example.org"]
    assert forwarded[0].source == "linked_mailbox"

    cache_linked_mailcow_mailboxes([], MAILBOX, BASE_TAG)
    assert linked_mailcow_mailbox_cache_ready(MAILBOX) is True
    assert direct_mailcow_forwards_to_mailbox([], MAILBOX) == []


def test_link_id_uses_configured_newsletter_base_tag():
    mailboxes = [
        _mailbox(MAILBOX, ["custom-news-link-family-target"]),
        _mailbox("old@example.net", ["custom-news-link-family-source"]),
    ]

    linked = linked_mailcow_mailboxes(mailboxes, MAILBOX, "custom-news")

    assert [item.address for item in linked] == ["old@example.net"]


def test_forwarded_newsletter_tag_is_explicit_per_mailbox_flag():
    assert forwarded_newsletter_tag(BASE_TAG) == "moolias-newsletter-forwarded"
    assert forwarded_newsletters_enabled(
        ["keep-me", "MOOLIAS-NEWSLETTER-FORWARDED"],
        BASE_TAG,
    ) is True
    assert forwarded_newsletters_enabled(
        ["keep-me", "moolias-newsletter"],
        BASE_TAG,
    ) is False


def test_replace_forwarded_newsletter_tag_preserves_unrelated_mailbox_tags():
    enabled = replace_forwarded_newsletter_tag(
        ["keep-me", "moolias-newsletter"],
        BASE_TAG,
        True,
    )
    assert enabled == [
        "keep-me",
        "moolias-newsletter",
        "moolias-newsletter-forwarded",
    ]

    disabled = replace_forwarded_newsletter_tag(
        enabled,
        BASE_TAG,
        False,
    )
    assert disabled == ["keep-me", "moolias-newsletter"]
