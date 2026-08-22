from __future__ import annotations

import re

from playwright.sync_api import Page, expect

UNUSED_POOL = "feder-hafen-27@example.org"


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))


def test_offline_pool_controls_stay_aligned_and_marker_hidden(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    expect(page.locator(".action-required-pool-marker:visible")).to_have_count(0)

    row = page.locator(".offline-pool-row").filter(has_text=UNUSED_POOL)
    expect(row).to_be_visible()

    assign_details = row.locator("details.pool-assign-action")
    expect(assign_details).to_be_visible()
    expect(assign_details).not_to_have_class(re.compile(r"\balias-edit-action\b"))

    assign = assign_details.locator("summary")
    copy = row.locator("[data-copy]")
    delete = row.locator('form[action$="/delete"] button')
    expect(assign).to_be_visible()
    expect(copy).to_be_visible()
    expect(delete).to_be_visible()

    assign_box = assign.bounding_box()
    copy_box = copy.bounding_box()
    delete_box = delete.bounding_box()
    assert assign_box and copy_box and delete_box
    assert assign_box["x"] + assign_box["width"] <= copy_box["x"] + 1
    assert copy_box["x"] + copy_box["width"] <= delete_box["x"] + 1

    delete_background = delete.evaluate("element => getComputedStyle(element).backgroundColor")
    assert delete_background not in {"rgba(0, 0, 0, 0)", "transparent"}


def test_full_statistics_switch_between_addresses_and_domains(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/statistics")

    expect(page.locator(".usage-profile-card")).to_be_visible()
    expect(
        page.locator(".statistics-card").filter(has_text="Needs review")
    ).to_have_count(0)

    detail_switch = page.locator(".statistics-detail-switch")
    expect(detail_switch).to_be_visible()
    expect(detail_switch.locator('a[href="/statistics?detail=address"]')).to_have_class(
        re.compile(r"\bcurrent\b")
    )

    sources = page.locator(".statistics-card").filter(has_text="Most active sources")
    destinations = page.locator(".statistics-card").filter(
        has_text="Most active destinations"
    )
    expect(sources).to_contain_text("news@amazon.de")
    expect(destinations).to_contain_text("customer@example.net")

    detail_switch.locator('a[href="/statistics?detail=domain"]').click()
    expect(page).to_have_url(re.compile(r"/statistics\?detail=domain$"))

    sources = page.locator(".statistics-card").filter(has_text="Most active sources")
    destinations = page.locator(".statistics-card").filter(
        has_text="Most active destinations"
    )
    expect(sources).to_contain_text("amazon.de")
    expect(sources).not_to_contain_text("news@amazon.de")
    expect(destinations).to_contain_text("example.net")
    expect(destinations).not_to_contain_text("customer@example.net")
