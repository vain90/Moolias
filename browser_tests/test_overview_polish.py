from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def test_header_language_spacing_matches_action_spacing(page: Page, base_url: str) -> None:
    _login(page, base_url)

    language_box = page.locator("header .language-dropdown").bounding_box()
    settings_box = page.locator(
        'header .header-icon-button[data-open-settings]'
    ).bounding_box()
    help_box = page.locator("header .help-trigger").bounding_box()

    assert language_box is not None
    assert settings_box is not None
    assert help_box is not None

    language_to_settings = settings_box["x"] - (
        language_box["x"] + language_box["width"]
    )
    settings_to_help = help_box["x"] - (
        settings_box["x"] + settings_box["width"]
    )

    assert 7 <= language_to_settings <= 9
    assert abs(language_to_settings - settings_to_help) <= 1


def test_recent_aliases_show_name_above_address(page: Page, base_url: str) -> None:
    _login(page, base_url)

    row = page.locator(".recent-alias-row", has_text="amazon-k7@example.org")
    expect(row).to_be_visible()

    identity = row.locator(".recent-alias-identity")
    expect(identity.locator("strong")).to_have_text("Amazon")
    expect(identity.locator("small")).to_have_text("amazon-k7@example.org")
