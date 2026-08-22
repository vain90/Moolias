from __future__ import annotations

import re

from playwright.sync_api import Page, expect

AMAZON = "amazon-k7@example.org"
UNEXPECTED_SENDER = "odd@unexpected.example"


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)


def _open_amazon_senders(page: Page):
    trigger = _alias_row(page, AMAZON).locator("button.sender-stats-trigger")
    expect(trigger).to_be_visible()
    dialog_id = trigger.get_attribute("aria-controls")
    assert dialog_id
    trigger.click()
    dialog = page.locator(f"#{dialog_id}")
    expect(dialog).to_be_visible()
    return dialog


def _sender_row(dialog, sender: str):
    return dialog.locator(".sender-stats-row").filter(has_text=sender)


def _expect_alias_url(page: Page, base_url: str) -> None:
    pattern = re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$")
    expect(page).to_have_url(pattern, timeout=5000)


def test_full_mode_domain_approval_warns_and_can_be_overridden_per_address(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    dialog = _open_amazon_senders(page)
    sender = _sender_row(dialog, UNEXPECTED_SENDER)
    expect(sender).to_have_class(re.compile(r"\bunexpected\b"))
    expect(sender.locator('[data-expect-domain]')).to_be_visible()

    sender.locator('[data-expect-domain]').click()
    confirmation = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(confirmation).to_be_visible()
    expect(confirmation).to_contain_text("unexpected.example")
    confirmation.locator('[data-moolias-dialog-cancel]').click()
    expect(sender).to_have_class(re.compile(r"\bunexpected\b"))

    sender.locator('[data-expect-domain]').click()
    confirmation = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(confirmation).to_be_visible()
    confirmation.locator('[data-moolias-dialog-confirm]').click()

    _expect_alias_url(page, base_url)
    dialog = _open_amazon_senders(page)
    sender = _sender_row(dialog, UNEXPECTED_SENDER)
    expect(sender).to_have_class(re.compile(r"\bexpected\b"))
    expect(sender.locator('[data-specific-unexpected]')).to_be_visible()

    sender.locator('[data-specific-unexpected]').click()
    _expect_alias_url(page, base_url)

    dialog = _open_amazon_senders(page)
    sender = _sender_row(dialog, UNEXPECTED_SENDER)
    expect(sender).to_have_class(re.compile(r"\bunexpected\b"))
    expect(sender.locator('[data-specific-unexpected]')).to_be_visible()
    expect(sender.locator('[data-expect-domain]')).to_have_count(0)
