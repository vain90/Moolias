from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect


def _login(page: Page, base_url: str) -> None:
    page.context.add_cookies(
        [{"name": "moolias_lang", "value": "de", "url": base_url}]
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _viewport_rect(locator: Locator) -> dict[str, float]:
    return locator.evaluate(
        """element => {
            const rect = element.getBoundingClientRect();
            return {
                x: rect.x,
                y: rect.y,
                top: rect.top,
                right: rect.right,
                bottom: rect.bottom,
                left: rect.left,
                width: rect.width,
                height: rect.height,
            };
        }"""
    )


def _expect_target_and_popover_in_view(page: Page) -> None:
    tour = page.locator(".tour-popover")
    viewport = page.viewport_size
    assert viewport is not None

    popover_rect = _viewport_rect(tour)
    assert popover_rect["left"] >= -1
    assert popover_rect["top"] >= -1
    assert popover_rect["right"] <= viewport["width"] + 1
    assert popover_rect["bottom"] <= viewport["height"] + 1

    selector = tour.get_attribute("data-tour-target") or ""
    if not selector:
        return

    target = page.locator(selector).first
    expect(target).to_be_visible()
    target_rect = _viewport_rect(target)

    visible_top = max(0.0, target_rect["top"])
    visible_bottom = min(float(viewport["height"]), target_rect["bottom"])
    visible_left = max(0.0, target_rect["left"])
    visible_right = min(float(viewport["width"]), target_rect["right"])

    assert visible_bottom - visible_top >= min(32.0, target_rect["height"])
    assert visible_right - visible_left >= min(32.0, target_rect["width"])


def _expect_step(page: Page, number: int, title: str) -> None:
    tour = page.locator(".tour-popover")
    expect(tour).to_be_visible()
    expect(tour).to_contain_text(f"Schritt {number} / 13")
    expect(tour).to_contain_text(title)
    _expect_target_and_popover_in_view(page)


def _next(page: Page) -> None:
    page.locator(".tour-popover").get_by_role("button", name="Weiter").click()


def _run_complete_tour(page: Page, base_url: str) -> None:
    invite = page.locator("[data-tour-invite]")
    expect(invite).to_be_visible()
    expect(invite).to_contain_text("Neu bei Moolias?")

    invite.locator("[data-start-tour-invite]").click()
    _expect_step(page, 1, "Warum Moolias?")

    _next(page)
    _expect_step(page, 2, "Deine Übersicht")

    _next(page)
    _expect_step(page, 3, "Hauptadresse schützen")
    expect(page.locator(".tour-popover")).to_contain_text("Administrator")

    _next(page)
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    _expect_step(page, 4, "Für jeden Dienst ein Alias")

    create_button_rect = _viewport_rect(page.locator("[data-open-create-alias]"))
    assert create_button_rect["top"] >= 0
    assert create_button_rect["top"] < 260
    assert create_button_rect["bottom"] <= page.viewport_size["height"]

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
    expect(page.locator(".tour-popover")).to_contain_text("Administrator")

    _next(page)
    _expect_step(page, 10, "Nicht erkannte Absender")

    _next(page)
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    _expect_step(page, 11, "Handlungsbedarf")

    _next(page)
    _expect_step(page, 12, "Einstellungen")
    expect(page.locator(".tour-popover")).to_contain_text("Administrator")

    _next(page)
    _expect_step(page, 13, "Hilfe ist immer erreichbar")

    page.locator(".tour-popover").get_by_role("button", name="Fertig").click()
    expect(page.locator(".tour-popover")).not_to_be_visible()


def test_first_visit_offers_and_completes_guided_tour(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 1440, "height": 900})
    _login(page, base_url)
    _run_complete_tour(page, base_url)


def test_mobile_guided_tour_keeps_targets_in_view(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    _run_complete_tour(page, base_url)


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
