from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.context.add_cookies(
        [{"name": "moolias_lang", "value": "de", "url": base_url}]
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _expect_step(page: Page, number: int, title: str) -> None:
    tour = page.locator(".tour-popover")
    expect(tour).to_be_visible()
    expect(tour).to_contain_text(f"Schritt {number} / 13")
    expect(tour).to_contain_text(title)


def _next(page: Page) -> None:
    page.locator(".tour-popover").get_by_role("button", name="Weiter").click()


def test_first_visit_offers_and_completes_guided_tour(page: Page, base_url: str) -> None:
    _login(page, base_url)

    invite = page.locator("[data-tour-invite]")
    expect(invite).to_be_visible()
    expect(invite).to_contain_text("Neu bei Moolias?")

    invite.locator("[data-start-tour-invite]").click()
    _expect_step(page, 1, "Warum Moolias?")

    _next(page)
    _expect_step(page, 2, "Deine Übersicht")

    _next(page)
    _expect_step(page, 3, "Hauptadresse schützen")

    _next(page)
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    _expect_step(page, 4, "Für jeden Dienst ein Alias")

    _next(page)
    _expect_step(page, 5, "Neuen Alias erstellen")

    _next(page)
    _expect_step(page, 6, "Aliase verwalten")

    _next(page)
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/offline-pool(?:[?#].*)?$"))
    _expect_step(page, 7, "Offline-Pool")

    _next(page)
    _expect_step(page, 8, "Später den Zweck zuordnen")

    _next(page)
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/statistics(?:[?#].*)?$"))
    _expect_step(page, 9, "Optionale Nutzungsstatistiken")

    _next(page)
    _expect_step(page, 10, "Nicht erkannte Absender")

    _next(page)
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    _expect_step(page, 11, "Handlungsbedarf")

    _next(page)
    _expect_step(page, 12, "Einstellungen")

    _next(page)
    _expect_step(page, 13, "Hilfe ist immer erreichbar")

    page.locator(".tour-popover").get_by_role("button", name="Fertig").click()
    expect(page.locator(".tour-popover")).not_to_be_visible()


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
    _expect_step(page, 1, "Warum Moolias?")
