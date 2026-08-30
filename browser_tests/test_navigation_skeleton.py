from __future__ import annotations

import re
import time

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _delay_alias_navigation(page: Page) -> None:
    def delayed(route):
        time.sleep(0.7)
        route.continue_()

    page.route("**/aliases", delayed)


def test_main_navigation_shows_skeleton_during_real_wait(page: Page, base_url: str) -> None:
    _login(page, base_url)
    expect(page.locator("link[data-navigation-loading-styles]")).to_have_count(1)
    _delay_alias_navigation(page)

    page.locator('.side-nav-link[href="/aliases"]').click(no_wait_after=True)

    expect(page.locator("html")).to_have_class(re.compile(r"\bnavigation-pending\b"))
    expect(page.locator("html")).to_have_attribute("data-navigation-target", "aliases")
    expect(page.locator(".app-main")).to_have_attribute("aria-busy", "true")

    page.wait_for_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("html")).not_to_have_class(re.compile(r"\bnavigation-pending\b"))
    expect(page.locator(".app-main")).not_to_have_attribute("aria-busy", "true")


def test_navigation_skeleton_respects_reduced_motion(page: Page, base_url: str) -> None:
    page.emulate_media(reduced_motion="reduce")
    _login(page, base_url)
    _delay_alias_navigation(page)

    page.locator('.side-nav-link[href="/aliases"]').click(no_wait_after=True)
    expect(page.locator("html")).to_have_class(re.compile(r"\bnavigation-pending\b"))

    animation_name = page.locator(".app-main").evaluate(
        "element => getComputedStyle(element, '::after').animationName"
    )
    display = page.locator(".app-main").evaluate(
        "element => getComputedStyle(element, '::after').display"
    )
    assert animation_name == "none"
    assert display == "none"
