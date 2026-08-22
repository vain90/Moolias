from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _open_action_required(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)

    page.goto(f"{base_url}/overview")
    action = page.locator("[data-action-required-open]")
    expect(action).to_be_visible()
    action.click()

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    expect(page.locator("dialog[data-action-required-dialog]")).to_be_visible(timeout=5000)


def _assert_wheel_scrolls_action_content(page: Page, target_selector: str) -> None:
    content = page.locator("dialog[data-action-required-dialog] .action-required-content")
    content.evaluate("element => { element.scrollTop = 0; }")
    page.locator(target_selector).hover()
    page.mouse.wheel(0, 220)
    page.wait_for_function(
        """() => document.querySelector(
            'dialog[data-action-required-dialog] .action-required-content'
        ).scrollTop > 0"""
    )


def test_used_offline_alias_does_not_trap_action_required_scrolling(
    page: Page,
    base_url: str,
) -> None:
    page.set_viewport_size({"width": 900, "height": 520})
    _open_action_required(page, base_url)

    dialog = page.locator("dialog[data-action-required-dialog]")
    content = dialog.locator(".action-required-content")
    pool_list = dialog.locator(".action-required-pool-form .used-pool-list")
    pool_row = dialog.locator('[data-pool-alias-id="11"]')
    sender_list = pool_row.locator(".sender-stats-list")

    expect(pool_row).to_be_visible()
    expect(sender_list).to_be_visible()
    assert content.evaluate("element => element.scrollHeight > element.clientHeight")

    assert pool_list.evaluate("element => getComputedStyle(element).overflowY") == "visible"
    assert sender_list.evaluate("element => getComputedStyle(element).overflowY") == "visible"

    _assert_wheel_scrolls_action_content(
        page,
        'dialog[data-action-required-dialog] [data-pool-alias-id="11"] .used-pool-identity > code',
    )
    _assert_wheel_scrolls_action_content(
        page,
        'dialog[data-action-required-dialog] [data-pool-alias-id="11"] .sender-stats-list',
    )
