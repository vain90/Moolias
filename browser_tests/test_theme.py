from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_theme_follows_system_and_persists_explicit_choice(page: Page, base_url: str) -> None:
    page.emulate_media(color_scheme="dark")
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

    root = page.locator("html")
    theme_color = page.locator('meta[name="theme-color"]')

    expect(root).to_have_attribute("data-theme-preference", "system")
    expect(root).to_have_attribute("data-theme", "dark")
    expect(theme_color).to_have_attribute("content", "#101418")

    page.locator("[data-open-settings]").click()
    drawer = page.locator("[data-settings-drawer]")
    expect(drawer).to_have_attribute("aria-hidden", "false")
    theme_select = drawer.locator("[data-theme-select]")
    expect(theme_select).to_have_value("system")

    drawer.locator('[data-theme-choice="light"]').click()
    expect(root).to_have_attribute("data-theme-preference", "light")
    expect(root).to_have_attribute("data-theme", "light")
    expect(theme_color).to_have_attribute("content", "#f6f8fa")
    assert page.evaluate("window.localStorage.getItem('moolias-theme')") == "light"

    page.reload()
    expect(root).to_have_attribute("data-theme", "light")
    page.locator("[data-open-settings]").click()
    drawer = page.locator("[data-settings-drawer]")
    expect(drawer.locator("[data-theme-select]")).to_have_value("light")

    drawer.locator('[data-theme-choice="system"]').click()
    expect(root).to_have_attribute("data-theme", "dark")
    assert page.evaluate("window.localStorage.getItem('moolias-theme')") == "system"

    page.emulate_media(color_scheme="light")
    expect(root).to_have_attribute("data-theme", "light")
    expect(theme_color).to_have_attribute("content", "#f6f8fa")
