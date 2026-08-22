from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _service_badge(page: Page, address: str):
    return _alias_row(page, address).locator("[data-service-icon-for]")


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))


def test_bundled_service_logo_and_restricted_fallback(page: Page, base_url: str) -> None:
    _login(page, base_url)

    github_badge = _service_badge(page, "github-m4@example.org")
    github_svg = github_badge.locator("svg.service-logo")
    github_logo = github_svg.locator("use")
    expect(github_logo).to_have_count(1)
    expect(github_logo).to_have_attribute(
        "href",
        "/static/service-icons.svg#service-github",
    )
    assert github_svg.evaluate(
        "element => { const box = element.getBBox(); return box.width > 0 && box.height > 0; }"
    )

    amazon_badge = _service_badge(page, "amazon-k7@example.org")
    expect(amazon_badge.locator("svg.service-logo")).to_have_count(0)
    expect(amazon_badge).to_have_text("A")


def test_service_icon_picker_shows_logos_search_and_updates_alias(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    amazon_row = _alias_row(page, "amazon-k7@example.org")
    edit = amazon_row.locator("details.alias-edit-action")
    edit.locator("summary").click()

    select = amazon_row.locator("[data-alias-icon-select]")
    expect(select).to_be_hidden(timeout=5000)

    trigger = amazon_row.locator("[data-icon-picker-trigger]")
    expect(trigger).to_be_visible(timeout=5000)
    expect(trigger).to_contain_text("Amazon")
    trigger.click()

    dialog = page.locator("dialog[data-service-icon-picker-dialog]")
    expect(dialog).to_be_visible()
    search = dialog.locator("[data-icon-picker-search]")
    expect(search).to_be_focused()
    search.fill("PayPal")

    paypal = dialog.locator('[data-icon-picker-option="paypal"]')
    expect(paypal).to_be_visible()
    expect(paypal).to_contain_text("PayPal")
    expect(dialog.locator("[data-icon-picker-option]:visible")).to_have_count(1)
    paypal.click()

    expect(dialog).not_to_be_visible(timeout=5000)
    expect(select).to_have_value("paypal")

    amazon_badge = _service_badge(page, "amazon-k7@example.org")
    expect(amazon_badge.locator("svg.service-logo use")).to_have_attribute(
        "href",
        "/static/service-icons.svg#service-paypal",
    )
    expect(trigger).to_contain_text("PayPal")
