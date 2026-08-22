from __future__ import annotations

import json
import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-alias-results-region]")).to_be_visible()
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)


def test_sender_protection_lives_in_settings_and_updates_overview(
    page: Page,
    base_url: str,
) -> None:
    requests: list[dict[str, object]] = []
    state = {"blocked": False}

    def sender_protection_route(route, request) -> None:
        if request.method == "GET":
            route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {
                        "enabled": True,
                        "available": True,
                        "blocked": state["blocked"],
                        "managed": True,
                        "retry_after": 0,
                    }
                ),
            )
            return

        payload = request.post_data_json
        requests.append(payload)
        assert request.headers.get("x-csrf-token")
        assert set(payload) == {"blocked"}
        state["blocked"] = bool(payload["blocked"])
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {
                    "blocked": state["blocked"],
                    "managed": True,
                    "retry_after": 1,
                }
            ),
        )

    page.route("**/aliases/sender-protection", sender_protection_route)
    _login(page, base_url)

    page.locator("[data-open-settings]").click()
    settings_drawer = page.locator("[data-settings-drawer]")
    expect(settings_drawer).to_have_attribute("aria-hidden", "false")
    protection = settings_drawer.locator("[data-sender-protection-settings]")
    expect(protection).to_be_visible()

    switch = protection.locator('input[role="switch"]')
    switch_control = protection.locator(".switch-control")
    expect(switch).not_to_be_checked()
    expect(protection.locator("[data-sender-protection-state]")).to_have_text("Not protected")

    switch_control.click()

    expect(switch).to_be_checked()
    expect(switch).to_be_disabled()
    expect(protection.locator("[data-sender-protection-state]")).to_have_text("Protected")
    expect(protection.locator("[data-sender-protection-message]")).to_contain_text("1 second")
    assert requests == [{"blocked": True}]

    page.wait_for_timeout(1100)
    expect(switch).to_be_enabled()

    page.goto(f"{base_url}/overview")
    expect(page.locator("[data-primary-protection-state]")).to_have_text("Protected", timeout=5000)
    expect(page.locator("[data-primary-protection-action]")).to_be_hidden()

    page.locator('[data-open-settings-section="protection"]').first.click()
    settings_drawer = page.locator("[data-settings-drawer]")
    protection = settings_drawer.locator("[data-sender-protection-settings]")
    switch = protection.locator('input[role="switch"]')
    switch_control = protection.locator(".switch-control")
    expect(switch).to_be_checked()
    switch_control.click()

    expect(switch).not_to_be_checked()
    expect(page.locator("[data-primary-protection-state]")).to_have_text("Not protected")
    expect(page.locator("[data-primary-protection-action]")).to_be_visible()
    assert requests == [{"blocked": True}, {"blocked": False}]
