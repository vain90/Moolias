from __future__ import annotations

import re

from playwright.sync_api import Page, expect

AMAZON = "amazon-k7@example.org"
GITHUB = "github-m4@example.org"
ARCHIVE = "archive-r8@example.org"


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


def _purposes(page: Page) -> list[str]:
    return page.locator(".alias-table-row .alias-info > strong").all_text_contents()


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _assert_no_reload(page: Page) -> None:
    assert page.evaluate("window.__mooliasNoReload") == "alive"


def test_alias_table_headers_control_sorting(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.evaluate("window.__mooliasNoReload = 'alive'")

    purpose = page.locator('.alias-sort-link[href*="sort=purpose"]')
    expect(purpose).to_be_visible()
    purpose.click()
    expect(page).to_have_url(re.compile(r"sort=purpose.*direction=asc|direction=asc.*sort=purpose"))
    assert _purposes(page) == ["Amazon", "Archive", "GitHub"]
    _assert_no_reload(page)

    status = page.locator('.alias-sort-link[href*="sort=status"]')
    status.click()
    expect(page).to_have_url(re.compile(r"sort=status.*direction=asc|direction=asc.*sort=status"))
    assert _purposes(page) == ["Archive", "GitHub", "Amazon"]
    _assert_no_reload(page)

    usage = page.locator('.alias-sort-link[href*="sort=usage"]')
    usage.click()
    expect(page).to_have_url(re.compile(r"sort=usage.*direction=desc|direction=desc.*sort=usage"))
    assert _purposes(page) == ["Amazon", "GitHub", "Archive"]
    _assert_no_reload(page)

    last_used = page.locator('.alias-sort-link[href*="sort=last_used"]')
    last_used.click()
    expect(page).to_have_url(
        re.compile(r"sort=last_used.*direction=desc|direction=desc.*sort=last_used")
    )
    assert _purposes(page) == ["Amazon", "GitHub", "Archive"]
    _assert_no_reload(page)


def test_alias_list_view_controls_stay_reload_free_and_rebind_behaviors(
    page: Page,
    base_url: str,
) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    _login(page, base_url)
    page.evaluate("window.__mooliasNoReload = 'alive'")

    search = page.locator("[data-live-search]")
    search.fill("GitHub")
    expect(page.locator(".alias-table-row")).to_have_count(1, timeout=5000)
    expect(_alias_row(page, GITHUB)).to_have_count(1)
    expect(page.locator(".alias-sort-link")).to_have_count(4)
    _assert_no_reload(page)

    copy = _alias_row(page, GITHUB).locator("button.alias-copy-action")
    copy.click()
    expect(copy).to_have_text("✓", timeout=1000)

    page.locator("[data-search-clear]").click()
    expect(page.locator(".alias-table-row")).to_have_count(3, timeout=5000)
    _assert_no_reload(page)

    disabled = page.locator('.status-filters a[href*="status=disabled"]')
    disabled.click()
    expect(page).to_have_url(re.compile(r"[?&]status=disabled(?:&|$)"))
    expect(page.locator(".alias-table-row")).to_have_count(1, timeout=5000)
    expect(_alias_row(page, ARCHIVE)).to_have_count(1)
    _assert_no_reload(page)

    page_size = page.locator("[data-page-size]")
    page_size.select_option("10")
    expect(page).to_have_url(re.compile(r"[?&]per_page=10(?:&|$)"))
    expect(page.locator("[data-page-size]")).to_have_value("10")
    _assert_no_reload(page)

    active = page.locator('.status-filters a[href*="status=active"]')
    active.click()
    expect(page).to_have_url(re.compile(r"[?&]status=active(?:&|$)"))
    expect(_alias_row(page, AMAZON)).to_have_count(1, timeout=5000)
    expect(_alias_row(page, GITHUB)).to_have_count(1)
    _assert_no_reload(page)

    github_select = _alias_row(page, GITHUB).locator("[data-alias-select]")
    github_select.check()
    bulk_action = page.locator("[data-bulk-action-select]")
    expect(bulk_action).to_be_enabled()
    bulk_action.select_option("disable")
    page.locator("[data-bulk-toolbar] .bulk-actions button").click()
    expect(_alias_row(page, GITHUB)).to_have_count(0, timeout=5000)
    expect(_alias_row(page, AMAZON)).to_have_count(1)
    _assert_no_reload(page)


def test_individual_alias_toggle_updates_without_document_reload(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.locator('.status-filters a[href*="status=disabled"]').click()
    expect(_alias_row(page, ARCHIVE)).to_have_count(1, timeout=5000)
    page.evaluate("window.__mooliasNoReload = 'alive'")

    archive = _alias_row(page, ARCHIVE)
    archive.locator("details.alias-edit-action > summary").click()
    archive.locator("form.alias-toggle-action button[type='submit']").click()

    expect(_alias_row(page, ARCHIVE)).to_have_count(0, timeout=5000)
    _assert_no_reload(page)


def test_cleared_live_search_does_not_return_when_filter_changes(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/aliases?q=GitHub")

    active_filter = page.locator('.status-filters a[href*="status=active"]')
    expect(active_filter).to_have_attribute("href", re.compile(r"[?&]q=GitHub(?:&|$)"))

    page.locator("[data-search-clear]").click()
    page.wait_for_function("() => !new URLSearchParams(window.location.search).has('q')")

    expect(active_filter).not_to_have_attribute("href", re.compile(r"[?&]q="))
    active_filter.click()
    assert page.evaluate("() => new URLSearchParams(window.location.search).get('q')") is None


def test_copy_feedback_uses_checkmark(page: Page, base_url: str) -> None:
    page.context.grant_permissions(["clipboard-read", "clipboard-write"], origin=base_url)
    _login(page, base_url)

    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    copy = row.locator("button.alias-copy-action")
    copy.click()
    expect(copy).to_have_text("✓", timeout=1000)
