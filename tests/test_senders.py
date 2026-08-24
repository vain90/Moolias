from moolias.senders import registered_domain_label, sender_match_token, sender_matches_alias


def test_service_name_matches_registered_sender_domain():
    assert sender_match_token(
        "amazon-k7@example.org",
        "Amazon",
        "amazon.de",
    ) == "amazon"
    assert sender_matches_alias(
        "amazon-k7@example.org",
        "Amazon",
        "mail.amazon.de",
    )


def test_approved_short_brands_match_exact_registered_domain_labels():
    assert sender_match_token(
        "ing-bank-k7@example.org",
        "ING - Bank",
        "info.ing.de",
    ) == "ing"
    assert sender_match_token(
        "dm-k7@example.org",
        "DM",
        "news.dm.de",
    ) == "dm"


def test_short_brand_exceptions_require_exact_alias_tokens():
    assert not sender_matches_alias(
        "bank-k7@example.org",
        "Ingredients Bank",
        "info.ing.de",
    )
    assert not sender_matches_alias(
        "drogerie-k7@example.org",
        "Drugstore",
        "news.dm.de",
    )
    assert not sender_matches_alias(
        "dmv-k7@example.org",
        "DMV service",
        "news.dm.de",
    )


def test_compound_brand_matches_complete_registered_domain_identity():
    alias = "takko-fashion-k7@example.org"
    name = "TAKKO Fashion - App"

    assert sender_match_token(alias, name, "contact.takko-fashion.com") == "takko-fashion"
    assert sender_match_token(alias, name, "contact.takkofashion.com") == "takkofashion"

    assert not sender_matches_alias(alias, name, "contact.takko-service.com")
    assert not sender_matches_alias(alias, name, "contact.takko-fashion-service.com")
    assert not sender_matches_alias(alias, name, "contact.takko-fashions.com")


def test_multilabel_public_suffix_uses_registered_domain_label():
    assert registered_domain_label("service.vodafone.co.uk") == "vodafone"
    assert sender_matches_alias(
        "vodafone-k7@example.org",
        "Vodafone - MeinVodafone",
        "service.vodafone.co.uk",
    )


def test_private_suffix_tenants_do_not_create_brand_trust():
    assert registered_domain_label("attacker.github.io") == "attacker"
    assert not sender_matches_alias(
        "github-m4@example.org",
        "GitHub",
        "github.github.io",
    )


def test_hyphenated_or_embedded_brand_domains_do_not_auto_match():
    alias = "vodafone-k7@example.org"
    name = "Vodafone - MeinVodafone"

    assert not sender_matches_alias(alias, name, "kundenservice.vodafone-mail.com")
    assert not sender_matches_alias(alias, name, "kundenservice.vodafone-service.com")
    assert not sender_matches_alias(alias, name, "vodafone-example.com")
    assert not sender_matches_alias(alias, name, "mail-vodafone.example.net")


def test_lookalike_domains_do_not_auto_match():
    alias = "vodafone-k7@example.org"
    name = "Vodafone - MeinVodafone"

    assert not sender_matches_alias(alias, name, "kundenservice.vodafonee.com")
    assert not sender_matches_alias(alias, name, "vodaf0ne.com")


def test_brand_in_subdomain_does_not_auto_match():
    assert not sender_matches_alias(
        "vodafone-k7@example.org",
        "Vodafone - MeinVodafone",
        "vodafone.login-example.com",
    )


def test_prefix_only_match_is_not_enough():
    assert not sender_matches_alias(
        "amazon-k7@example.org",
        "Amazon",
        "amazonaws.com",
    )


def test_generic_alias_words_do_not_auto_approve_sender():
    assert not sender_matches_alias(
        "shop-k7@example.org",
        "Newsletter Shop",
        "shop.example.net",
    )


def test_private_description_can_supply_a_conservative_exact_brand_hint():
    assert sender_match_token(
        "random-k7@example.org",
        "Audio account",
        "mail.audible.de",
        private_description="Invoices and Audible audiobooks",
    ) == "audible"


def test_private_description_does_not_promote_generic_words():
    assert not sender_matches_alias(
        "random-k7@example.org",
        "Private account",
        "support.example.org",
        private_description="Newsletter support and login messages",
    )


def test_private_description_does_not_get_short_brand_exceptions():
    assert not sender_matches_alias(
        "random-k7@example.org",
        "Drugstore purchases",
        "news.dm.de",
        private_description="DM receipts",
    )


def test_private_description_does_not_create_compound_brand_identity():
    assert not sender_matches_alias(
        "random-k7@example.org",
        "Clothing",
        "mail.takko-fashion.com",
        private_description="Takko Fashion orders",
    )


def test_unrelated_sender_remains_unexpected():
    assert not sender_matches_alias(
        "betten-leinetal@example.org",
        "Betten Leinetal",
        "gwdg.de",
        private_description="Furniture invoices",
    )
