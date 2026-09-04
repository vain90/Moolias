from __future__ import annotations

import re

from playwright.sync_api import Browser, Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def test_wait_action_is_available_for_normal_and_offline_aliases(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    page.goto(f"{base_url}/aliases")
    active = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    disabled = page.locator(
        '.alias-row:has([data-alias-select][data-address="archive-r8@example.org"])'
    )
    expect(active.locator("[data-alias-wait-button]")).to_be_visible()
    expect(disabled.locator("[data-alias-wait-button]")).to_have_count(0)

    page.goto(f"{base_url}/offline-pool")
    offline = page.locator(
        '.offline-pool-row[data-alias-address="feder-hafen-27@example.org"]'
    )
    expect(offline.locator("[data-alias-wait-button]")).to_be_visible()


def test_wait_action_shows_active_state_after_restart(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/aliases")

    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    button = row.locator("[data-alias-wait-button]")
    button.click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    expect(row.locator("[data-alias-wait-indicator]")).to_be_visible(timeout=5000)
    expect(row.locator("[data-alias-wait-button]")).to_have_attribute(
        "aria-label",
        "Restart waiting period",
    )


def test_existing_alias_wait_works_without_javascript(
    browser: Browser,
    base_url: str,
) -> None:
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        _login(page, base_url)
        page.goto(f"{base_url}/aliases")

        row = page.locator(
            '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
        )
        with page.expect_navigation(wait_until="load"):
            row.locator("[data-alias-wait-button]").click()
        expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

        page.goto(f"{base_url}/aliases/wait-status")
        expect(page.locator("body")).to_contain_text("amazon-k7@example.org")
    finally:
        context.close()
