from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.context.add_cookies(
        [{"name": "moolias_lang", "value": "de", "url": base_url}]
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def test_first_visit_offers_guided_tour_and_tour_crosses_pages(page: Page, base_url: str) -> None:
    _login(page, base_url)

    invite = page.locator("[data-tour-invite]")
    expect(invite).to_be_visible()
    expect(invite).to_contain_text("Neu bei Moolias?")

    invite.locator("[data-start-tour-invite]").click()
    tour = page.locator(".tour-popover")
    expect(tour).to_be_visible()
    expect(tour).to_contain_text("Schritt 1 / 13")
    expect(tour).to_contain_text("Warum Moolias?")

    tour.get_by_role("button", name="Weiter").click()
    expect(tour).to_contain_text("Schritt 2 / 13")
    expect(tour).to_contain_text("Deine Übersicht")

    tour.get_by_role("button", name="Weiter").click()
    expect(tour).to_contain_text("Schritt 3 / 13")
    expect(tour).to_contain_text("Hauptadresse schützen")

    tour.get_by_role("button", name="Weiter").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    tour = page.locator(".tour-popover")
    expect(tour).to_contain_text("Schritt 4 / 13")
    expect(tour).to_contain_text("Für jeden Dienst ein Alias")

    tour.get_by_role("button", name="Überspringen").click()
    expect(tour).not_to_be_visible()


def test_help_explains_aliases_and_can_restart_tour(page: Page, base_url: str) -> None:
    _login(page, base_url)

    page.locator("[data-tour-invite] .button.ghost").click()
    page.locator("[data-open-help-dialog]").click()

    help_dialog = page.locator("[data-help-dialog]")
    expect(help_dialog).to_be_visible()
    expect(help_dialog).to_contain_text("Moolias einfach erklärt")
    expect(help_dialog).to_contain_text("Warum überhaupt Aliase?")
    expect(help_dialog).to_contain_text("Ein Dienst, ein Alias")
    expect(help_dialog).to_contain_text("Statistiken und Hinweise")

    help_dialog.locator("[data-start-tour]").click()
    expect(help_dialog).not_to_be_visible()
    expect(page.locator(".tour-popover")).to_contain_text("Schritt 1 / 13")
