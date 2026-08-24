from moolias.newsletter_mode import (
    NewsletterMode,
    NewsletterModeSource,
    replace_mailbox_newsletter_tags,
    resolve_newsletter_mode,
)

BASE = "moolias-newsletter"


def test_newsletter_mode_defaults_to_off_without_tags():
    state = resolve_newsletter_mode([], [], BASE)
    assert state.effective is NewsletterMode.OFF
    assert state.source is NewsletterModeSource.NONE
    assert state.mailbox_override is None
    assert state.domain_default is None
    assert state.enabled is False


def test_newsletter_mode_inherits_domain_on():
    state = resolve_newsletter_mode([], [BASE], BASE)
    assert state.effective is NewsletterMode.ON
    assert state.source is NewsletterModeSource.DOMAIN
    assert state.mailbox_override is None
    assert state.domain_default is NewsletterMode.ON
    assert state.enabled is True


def test_mailbox_off_overrides_domain_on():
    state = resolve_newsletter_mode([f"{BASE}-off"], [BASE], BASE)
    assert state.effective is NewsletterMode.OFF
    assert state.source is NewsletterModeSource.MAILBOX
    assert state.mailbox_override is NewsletterMode.OFF
    assert state.domain_default is NewsletterMode.ON


def test_mailbox_on_overrides_domain_off():
    state = resolve_newsletter_mode([BASE], [f"{BASE}-off"], BASE)
    assert state.effective is NewsletterMode.ON
    assert state.source is NewsletterModeSource.MAILBOX
    assert state.mailbox_override is NewsletterMode.ON
    assert state.domain_default is NewsletterMode.OFF


def test_conflicting_mailbox_tags_fail_closed():
    state = resolve_newsletter_mode([BASE, f"{BASE}-off"], [BASE], BASE)
    assert state.effective is NewsletterMode.OFF
    assert state.conflict is True
    assert state.conflict_source is NewsletterModeSource.MAILBOX


def test_conflicting_domain_tags_fail_closed_without_mailbox_override():
    state = resolve_newsletter_mode([], [BASE, f"{BASE}-off"], BASE)
    assert state.effective is NewsletterMode.OFF
    assert state.conflict is True
    assert state.conflict_source is NewsletterModeSource.DOMAIN


def test_mailbox_override_wins_even_if_domain_tags_conflict():
    state = resolve_newsletter_mode([BASE], [BASE, f"{BASE}-off"], BASE)
    assert state.effective is NewsletterMode.ON
    assert state.source is NewsletterModeSource.MAILBOX
    assert state.conflict is False


def test_replace_mailbox_newsletter_tags_preserves_unrelated_tags():
    assert replace_mailbox_newsletter_tags(
        ["keep-me", f"{BASE}-off"],
        BASE,
        "on",
    ) == ["keep-me", BASE]

    assert replace_mailbox_newsletter_tags(
        ["keep-me", BASE],
        BASE,
        "off",
    ) == ["keep-me", f"{BASE}-off"]

    assert replace_mailbox_newsletter_tags(
        ["keep-me", BASE],
        BASE,
        "inherit",
    ) == ["keep-me"]
