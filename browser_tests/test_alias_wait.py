from __future__ import annotations

import re

from playwright.sync_api import Browser, Page, Route, expect


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
    expect(active.locator("[data-alias-wait-button] use")).to_have_attribute(
        "href",
        "/static/ui-icons.svg#icon-mail-search",
    )
    expect(disabled.locator("[data-alias-wait-button]")).to_have_count(0)

    page.goto(f"{base_url}/offline-pool")
    offline = page.locator(
        '.offline-pool-row[data-alias-address="feder-hafen-27@example.org"]'
    )
    expect(offline.locator("[data-alias-wait-button]")).to_be_visible()
    expect(offline.locator("[data-alias-wait-button] use")).to_have_attribute(
        "href",
        "/static/ui-icons.svg#icon-mail-search",
    )


def test_wait_action_opens_workflow_style_dialog(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/aliases")

    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    button = row.locator("[data-alias-wait-button]")
    button.click()

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    dialog = page.locator("[data-alias-manual-wait-dialog]")
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog).to_contain_text("Wait for email")
    expect(dialog.locator("[data-alias-manual-wait-address]")).to_have_text(
        "amazon-k7@example.org"
    )
    expect(dialog.locator("[data-alias-manual-wait-message]")).to_have_text(
        "Waiting for the next email to this alias."
    )

    expect(row.locator("[data-alias-wait-indicator]")).to_be_visible(timeout=5000)
    expect(row.locator("[data-alias-wait-button]")).to_have_attribute(
        "aria-label",
        "Restart waiting period",
    )


def test_offline_wait_action_opens_same_dialog(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    row = page.locator(
        '.offline-pool-row[data-alias-address="feder-hafen-27@example.org"]'
    )
    row.locator("[data-alias-wait-button]").click()

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/offline-pool(?:[?#].*)?$"))
    dialog = page.locator("[data-alias-manual-wait-dialog]")
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator("[data-alias-manual-wait-address]")).to_have_text(
        "feder-hafen-27@example.org"
    )
    expect(dialog.locator("[data-alias-manual-wait-message]")).to_have_text(
        "Waiting for the next email to this alias."
    )


def test_wait_dialog_reports_received_mail(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/aliases")

    def received_workflow(route: Route) -> None:
        if route.request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body='{"state":"received"}',
            )
            return
        route.continue_()

    page.route(re.compile(r".*/aliases/workflows/\d+$"), received_workflow)

    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )
    row.locator("[data-alias-wait-button]").click()

    dialog = page.locator("[data-alias-manual-wait-dialog]")
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator("[data-alias-manual-wait-message]")).to_have_text(
        "New email received. Please check your inbox.",
        timeout=7000,
    )
    expect(dialog.locator("[data-alias-manual-wait-spinner]")).to_be_hidden()
    expect(dialog.locator("[data-alias-manual-wait-stop]")).to_be_hidden()


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
