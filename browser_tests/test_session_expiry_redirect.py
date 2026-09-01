from __future__ import annotations

import re

import pytest
from playwright.sync_api import Page, expect


PROTECTED_NAVIGATION_PATHS = (
    "/overview",
    "/aliases",
    "/offline-pool",
    "/newsletters",
    "/statistics",
)


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


@pytest.mark.parametrize("path", PROTECTED_NAVIGATION_PATHS)
def test_navigation_after_session_expiry_returns_to_login(
    page: Page,
    base_url: str,
    path: str,
) -> None:
    _login(page, base_url)

    # Keep the already-rendered authenticated page open while expiring the
    # browser session, matching the real idle-tab failure mode.
    page.context.clear_cookies()
    page.evaluate(
        """
        (targetPath) => {
          const link = document.querySelector(`.side-nav-link[href="${targetPath}"]`);
          if (!link) throw new Error(`Missing navigation link for ${targetPath}`);
          link.click();
        }
        """,
        path,
    )

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/(?:[?#].*)?$"))
    expect(page.locator("body")).not_to_contain_text("Authentication required")
