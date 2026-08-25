from __future__ import annotations

from moolias.aliases import AliasRecord
from moolias.newsletter_forwarding import (
    direct_mailcow_forwards_to_mailbox,
    forwarded_newsletter_tag,
    forwarded_newsletters_enabled,
    replace_forwarded_newsletter_tag,
)

MAILBOX = "hidden.pk@kreis-home.de"


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


def test_direct_mailcow_forwards_only_returns_external_direct_single_target_aliases():
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


def test_forwarded_newsletter_tag_is_explicit_per_mailbox_flag():
    assert forwarded_newsletter_tag("moolias-newsletter") == (
        "moolias-newsletter-forwarded"
    )
    assert forwarded_newsletters_enabled(
        ["keep-me", "MOOLIAS-NEWSLETTER-FORWARDED"],
        "moolias-newsletter",
    ) is True
    assert forwarded_newsletters_enabled(
        ["keep-me", "moolias-newsletter"],
        "moolias-newsletter",
    ) is False


def test_replace_forwarded_newsletter_tag_preserves_unrelated_mailbox_tags():
    enabled = replace_forwarded_newsletter_tag(
        ["keep-me", "moolias-newsletter"],
        "moolias-newsletter",
        True,
    )
    assert enabled == [
        "keep-me",
        "moolias-newsletter",
        "moolias-newsletter-forwarded",
    ]

    disabled = replace_forwarded_newsletter_tag(
        enabled,
        "moolias-newsletter",
        False,
    )
    assert disabled == ["keep-me", "moolias-newsletter"]
