from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


def _purposes(page: Page) -> list[str]:
    return page.locator(".alias-table-row .alias-info > strong").all_text_contents()


def test_alias_table_headers_control_sorting(page: Page, base_url: str) -> None:
    _login(page, base_url)

    purpose = page.locator('.alias-sort-link[href*="sort=purpose"]')
    expect(purpose).to_be_visible()
    purpose.click()
    expect(page).to_have_url(re.compile(r"sort=purpose.*direction=asc|direction=asc.*sort=purpose"))
    assert _purposes(page) == ["Amazon", "Archive", "GitHub"]

    status = page.locator('.alias-sort-link[href*="sort=status"]')
    status.click()
    expect(page).to_have_url(re.compile(r"sort=status.*direction=asc|direction=asc.*sort=status"))
    assert _purposes(page) == ["Archive", "GitHub", "Amazon"]

    usage = page.locator('.alias-sort-link[href*="sort=usage"]')
    usage.click()
    expect(page).to_have_url(re.compile(r"sort=usage.*direction=desc|direction=desc.*sort=usage"))
    assert _purposes(page) == ["Amazon", "GitHub", "Archive"]

    last_used = page.locator('.alias-sort-link[href*="sort=last_used"]')
    last_used.click()
    expect(page).to_have_url(
        re.compile(r"sort=last_used.*direction=desc|direction=desc.*sort=last_used")
    )
    assert _purposes(page) == ["Amazon", "GitHub", "Archive"]


def test_copy_feedback_uses_checkmark(page: Page, base_url: str) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    _login(page, base_url)

    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    copy = row.locator("button.alias-copy-action")
    copy.click()
    expect(copy).to_have_text("✓", timeout=1000)
