from __future__ import annotations

import re

from playwright.sync_api import Locator, Page, expect


def _login_de(page: Page, base_url: str) -> None:
    page.context.add_cookies(
        [{"name": "moolias_lang", "value": "de", "url": base_url}]
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _amazon_row(page: Page) -> Locator:
    return page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )


def test_alias_description_edit_and_table_preview(page: Page, base_url: str) -> None:
    _login_de(page, base_url)
    page.goto(f"{base_url}/aliases")

    expect(page.locator(".alias-table-head")).to_contain_text(
        "Alias Name / Alias-Adresse"
    )

    row = _amazon_row(page)
    row.locator(".alias-edit-action > summary").click()
    panel = row.locator(".edit-panel")

    expect(panel.locator("[data-alias-edit-address] code")).to_have_text(
        "amazon-k7@example.org"
    )
    expect(
        panel.locator('[name="description"]').locator("xpath=..")
    ).to_contain_text("Alias Name")
    description = panel.locator('textarea[name="private_description"]')
    expect(description).to_be_visible()
    expect(description.locator("xpath=..")).to_contain_text("Beschreibung")
    expect(panel).not_to_contain_text("privaten Mailcow-Kommentar")

    textarea_box = description.bounding_box()
    form_box = panel.locator('form[action$="/metadata"]').bounding_box()
    assert textarea_box is not None
    assert form_box is not None
    assert textarea_box["width"] >= form_box["width"] - 2
    assert textarea_box["height"] >= 90

    full_text = (
        "Bestellungen, Rechnungen, Marketplace und Audible für den privaten Einkauf"
    )
    description.fill(full_text)
    panel.get_by_role("button", name="Speichern").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

    row = _amazon_row(page)
    details = row.locator(".alias-description-details")
    expect(details).to_be_visible()
    expect(details.locator(".alias-description-preview")).to_have_text(full_text)
    assert details.locator(".alias-description-preview").evaluate(
        "el => getComputedStyle(el).textOverflow"
    ) == "ellipsis"

    details.locator("summary").click()
    expect(details.locator(".alias-description-popover")).to_have_text(full_text)

    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    row = _amazon_row(page)
    details = row.locator(".alias-description-details")
    expect(details.locator(".alias-description-preview")).to_be_hidden()
    expect(details.locator(".alias-description-info")).to_be_visible()
    details.locator("summary").click()
    expect(details.locator(".alias-description-popover")).to_have_text(full_text)


def test_offline_pool_assignment_accepts_description(page: Page, base_url: str) -> None:
    _login_de(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    dialog = page.locator('[data-assign-dialog="10"]')
    page.locator('[data-open-assign-dialog="10"]').first.click()
    expect(dialog).to_be_visible()

    name = dialog.locator('input[name="description"]')
    description = dialog.locator('textarea[name="private_description"]')
    expect(name.locator("xpath=..")).to_contain_text("Alias Name")
    expect(description.locator("xpath=..")).to_contain_text("Beschreibung")

    name.fill("Hotel")
    description.fill("Geschäftsreise und Hotelrechnungen")
    dialog.get_by_role("button", name="Zuordnen").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/offline-pool(?:[?#].*)?$"))

    page.goto(f"{base_url}/aliases?q=feder-hafen-27")
    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="feder-hafen-27@example.org"])'
    )
    expect(row.locator(".alias-info > strong")).to_have_text("Hotel")
    expect(row.locator(".alias-description-preview")).to_have_text(
        "Geschäftsreise und Hotelrechnungen"
    )
