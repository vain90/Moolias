from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def test_main_navigation_shows_skeleton_during_real_wait(page: Page, base_url: str) -> None:
    _login(page, base_url)
    expect(page.locator("link[data-navigation-loading-styles]")).to_have_count(1)

    state = page.evaluate(
        """
        () => {
          document.querySelector('.side-nav-link[href="/aliases"]').click();
          const root = document.documentElement;
          const main = document.querySelector('.app-main');
          return {
            pending: root.classList.contains('navigation-pending'),
            target: root.dataset.navigationTarget || '',
            busy: main?.getAttribute('aria-busy') || '',
          };
        }
        """
    )

    assert state == {"pending": True, "target": "aliases", "busy": "true"}
    page.wait_for_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("html")).not_to_have_class(re.compile(r"\bnavigation-pending\b"))
    expect(page.locator(".app-main")).not_to_have_attribute("aria-busy", "true")


def test_navigation_skeleton_respects_reduced_motion(page: Page, base_url: str) -> None:
    page.emulate_media(reduced_motion="reduce")
    _login(page, base_url)

    state = page.evaluate(
        """
        () => {
          document.querySelector('.side-nav-link[href="/aliases"]').click();
          const root = document.documentElement;
          const main = document.querySelector('.app-main');
          const style = getComputedStyle(main, '::after');
          return {
            pending: root.classList.contains('navigation-pending'),
            animationName: style.animationName,
            display: style.display,
          };
        }
        """
    )

    assert state["pending"] is True
    assert state["animationName"] == "none"
    assert state["display"] == "none"
    page.wait_for_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
