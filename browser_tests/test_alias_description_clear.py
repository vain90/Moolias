import re

from playwright.sync_api import Page, expect


def _login_de(page: Page, base_url: str) -> None:
    page.context.add_cookies(
        [{"name": "moolias_lang", "value": "de", "url": base_url}]
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _amazon_row(page: Page):
    return page.locator(
        '.alias-row:has([data-alias-select][data-address="amazon-k7@example.org"])'
    )


def test_alias_description_can_be_cleared_completely(page: Page, base_url: str) -> None:
    _login_de(page, base_url)
    page.goto(f"{base_url}/aliases")

    row = _amazon_row(page)
    row.locator(".alias-edit-action > summary").click()
    panel = row.locator(".edit-panel")
    description = panel.locator('textarea[name="private_description"]')
    expect(description).to_be_visible()

    description.fill("Temporäre Beschreibung")
    panel.get_by_role("button", name="Speichern").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

    row = _amazon_row(page)
    expect(row.locator(".alias-description-preview")).to_have_text(
        "Temporäre Beschreibung"
    )

    row.locator(".alias-edit-action > summary").click()
    panel = row.locator(".edit-panel")
    description = panel.locator('textarea[name="private_description"]')
    expect(description).to_have_value("Temporäre Beschreibung")
    description.fill("")
    panel.get_by_role("button", name="Speichern").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))

    row = _amazon_row(page)
    expect(row.locator(".alias-description-details")).to_have_count(0)

    row.locator(".alias-edit-action > summary").click()
    expect(
        row.locator('.edit-panel textarea[name="private_description"]')
    ).to_have_value("")
