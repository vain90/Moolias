import pytest

from moolias.aliases import (
    RESERVED_COMMENT,
    RESERVED_MARKER,
    USED_RESERVED_MARKER,
    AliasRecord,
    is_mailbox_catch_all,
    is_owned_alias,
    is_primary_mailbox_alias,
    load_words,
    mailbox_domain,
    named_local_part,
    readable_local_part,
    slugify,
    update_private_comment,
    validate_local_part,
)


def test_mailbox_domain_is_derived_from_login():
    assert mailbox_domain("Hidden.PK@Sky-Post.de") == "sky-post.de"


def test_slugify_is_stable_and_ascii():
    assert slugify("Müller & Amazon Privat") == "muller-amazon-privat"


def test_named_alias_uses_two_easy_to_dictate_suffix_characters():
    allowed = set("abcdefghjkmnpqrstuvwxyz23456789")
    for _ in range(100):
        local_part = named_local_part("Müller & Amazon")
        slug, suffix = local_part.rsplit("-", 1)
        assert slug == "muller-amazon"
        assert len(suffix) == 2
        assert set(suffix) <= allowed
        assert validate_local_part(local_part) == local_part


def test_local_part_is_conservative():
    assert validate_local_part("amazon-k7") == "amazon-k7"
    with pytest.raises(ValueError):
        validate_local_part("Not Allowed!")


@pytest.mark.parametrize("language", ["de", "en"])
def test_wordlists_are_short_unique_and_varied(language: str):
    words = load_words(language)
    assert 200 <= len(words) <= 250
    assert len(words) == len(set(words))
    assert max(map(len, words)) <= 6


@pytest.mark.parametrize("language", ["de", "en"])
def test_readable_aliases_are_compact_valid_local_parts(language: str):
    for _ in range(100):
        local_part = readable_local_part(language)
        parts = local_part.split("-")
        assert len(parts) == 3
        assert len(parts[0]) <= 6
        assert len(parts[1]) <= 6
        assert len(parts[2]) == 2 and parts[2].isdigit()
        assert len(local_part) <= 16
        assert validate_local_part(local_part) == local_part


def test_owned_alias_requires_exact_single_target_and_same_domain():
    alias = AliasRecord(
        id=1,
        address="amazon-k7@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="Invoices and Marketplace",
        public_comment="Amazon",
        sogo_visible=True,
    )
    assert alias.name == "Amazon"
    assert alias.description == "Amazon"
    assert alias.private_description == "Invoices and Marketplace"
    assert alias.description.private_description == "Invoices and Marketplace"
    assert is_owned_alias(alias, "hidden@example.org")
    assert not is_owned_alias(alias, "other@example.org")

    shared = AliasRecord(
        id=2,
        address="shared@example.org",
        goto="hidden@example.org,other@example.org",
        domain="example.org",
        active=True,
        private_comment="Shared admin note",
        public_comment="Shared",
    )
    assert not is_owned_alias(shared, "hidden@example.org")


def test_primary_mailbox_alias_is_detected_separately():
    primary = AliasRecord(
        id=7,
        address="hidden@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="",
        sender_allowed=False,
    )
    assert is_primary_mailbox_alias(primary, "hidden@example.org")
    assert not is_primary_mailbox_alias(primary, "other@example.org")


def test_active_catch_all_for_mailbox_is_detected_without_exposing_targets():
    catch_all = AliasRecord(
        id=8,
        address="@example.org",
        goto="hidden@example.org,other@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="",
        is_catch_all=True,
    )
    assert is_mailbox_catch_all(catch_all, "hidden@example.org")
    assert is_mailbox_catch_all(catch_all, "other@example.org")
    assert not is_mailbox_catch_all(catch_all, "nobody@example.org")

    inactive = AliasRecord(
        id=9,
        address="@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=False,
        private_comment="",
        public_comment="",
        is_catch_all=True,
    )
    assert not is_mailbox_catch_all(inactive, "hidden@example.org")


def test_only_moolias_markers_are_hidden_from_private_description():
    alias = AliasRecord(
        id=3,
        address="private@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="Private shopping [Family]\n[moolias:reserved-used]",
        public_comment="Amazon",
    )
    assert alias.private_description == "Private shopping [Family]"
    assert alias.is_reserved
    assert alias.is_reserved_used


def test_non_moolias_brackets_and_old_marker_text_are_plain_description():
    alias = AliasRecord(
        id=4,
        address="plain@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment="[cowcloak:reserved]\n[reserved] Offline alias\n[Family]",
        public_comment="Plain",
    )
    assert not alias.is_reserved
    assert not alias.is_reserved_used
    assert alias.private_description == "[cowcloak:reserved]\n[reserved] Offline alias\n[Family]"


def test_moolias_status_updates_preserve_human_text_and_other_markers():
    original = "Amazon orders [Family]\n[moolias:reserved]\n[moolias:future-state]"
    updated = update_private_comment(
        original,
        add_markers={USED_RESERVED_MARKER},
        remove_markers={RESERVED_MARKER},
    )
    alias = AliasRecord(
        id=5,
        address="pool@example.org",
        goto="hidden@example.org",
        domain="example.org",
        active=True,
        private_comment=updated,
        public_comment="",
    )
    assert alias.private_description == "Amazon orders [Family]"
    assert alias.markers == frozenset({"reserved-used", "future-state"})
    assert alias.is_reserved_used


def test_reserved_comment_constant_is_current_moolias_marker_only():
    assert RESERVED_COMMENT == "[moolias:reserved]"
