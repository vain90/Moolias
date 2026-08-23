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
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


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
    expect(trigger).to_have_attribute("aria-label", re.compile(r"Alias logo: Amazon"))
    expect(trigger).not_to_contain_text("Amazon")
    trigger.click()

    dialog = page.locator("dialog[data-service-icon-picker-dialog]")
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2")).to_have_text("Choose alias logo")
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
    expect(trigger).to_have_attribute("aria-label", re.compile(r"Alias logo: PayPal"))
    expect(trigger).not_to_contain_text("PayPal")


def test_alias_edit_panel_uses_compact_logo_and_bottom_actions(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    row = _alias_row(page, "amazon-k7@example.org")
    edit = row.locator("details.alias-edit-action")
    edit.locator("summary").click()

    panel = edit.locator(".edit-panel")
    trigger = panel.locator("[data-icon-picker-trigger]")
    expect(trigger).to_be_visible(timeout=5000)
    expect(panel.locator(".service-icon-picker-label > span")).to_have_text("Alias logo")

    purpose = panel.locator('input[name="description"]')
    expect(purpose.locator("xpath=..").locator(".alias-field-caption")).to_have_text(
        "Alias name / purpose"
    )

    replace = panel.locator("[data-replace-alias]")
    disable = panel.locator(".alias-toggle-action button")
    expect(replace).to_have_text("Replace alias")
    expect(disable).to_have_text("Disable alias")

    trigger_box = trigger.bounding_box()
    purpose_box = purpose.bounding_box()
    replace_box = replace.bounding_box()
    disable_box = disable.bounding_box()
    assert trigger_box and purpose_box and replace_box and disable_box
    assert trigger_box["y"] < purpose_box["y"]
    assert replace_box["y"] < disable_box["y"]
    assert abs(replace_box["width"] - disable_box["width"]) <= 1
    expect(panel.locator(".hint").filter(has_text="Creates a new alias")).to_have_count(0)


def test_generated_service_logo_renders_from_local_sprite(page: Page, base_url: str) -> None:
    _login(page, base_url)

    amazon_row = _alias_row(page, "amazon-k7@example.org")
    amazon_row.locator("details.alias-edit-action > summary").click()
    trigger = amazon_row.locator("[data-icon-picker-trigger]")
    expect(trigger).to_be_visible(timeout=5000)
    trigger.click()

    dialog = page.locator("dialog[data-service-icon-picker-dialog]")
    search = dialog.locator("[data-icon-picker-search]")
    search.fill("Lufthansa")
    lufthansa = dialog.locator('[data-icon-picker-option="lufthansa"]')
    expect(lufthansa).to_be_visible()
    expect(dialog.locator("[data-icon-picker-option]:visible")).to_have_count(1)
    lufthansa.click()

    expect(dialog).not_to_be_visible(timeout=5000)
    badge = _service_badge(page, "amazon-k7@example.org")
    logo = badge.locator("svg.service-logo")
    expect(logo.locator("use")).to_have_attribute(
        "href",
        "/static/service-icons.generated.svg#service-lufthansa",
    )
    assert logo.evaluate(
        "element => { const box = element.getBBox(); return box.width > 0 && box.height > 0; }"
    )
