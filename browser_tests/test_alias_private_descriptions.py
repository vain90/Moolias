from __future__ import annotations

import re

from playwright.sync_api import Browser, Locator, Page, expect


def _login_de(page: Page, base_url: str) -> None:
    page.context.add_cookies(
        [{"name": "moolias_lang", "value": "de", "url": base_url}]
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _alias_row(page: Page, address: str) -> Locator:
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _amazon_row(page: Page) -> Locator:
    return _alias_row(page, "amazon-k7@example.org")


def test_alias_description_fields_are_server_rendered_without_javascript(
    browser: Browser,
    base_url: str,
) -> None:
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        _login_de(page, base_url)
        page.goto(f"{base_url}/aliases")

        warning = page.locator("[data-javascript-warning]")
        expect(warning).to_be_visible()
        expect(warning).to_contain_text("⚠ JavaScript ist deaktiviert.")
        expect(warning).to_contain_text("nicht oder nur sehr eingeschränkt nutzbar")
        expect(warning.locator("button")).to_have_count(0)
        expect(warning.locator("span")).to_have_count(0)

        warning_box = warning.bounding_box()
        content_box = warning.evaluate(
            """
            el => {
              const range = document.createRange();
              range.selectNodeContents(el);
              const rect = range.getBoundingClientRect();
              return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
              };
            }
            """
        )
        sidebar_box = page.locator("[data-app-sidebar]").bounding_box()
        viewport = page.viewport_size
        assert warning_box is not None
        assert sidebar_box is not None
        assert viewport is not None
        assert abs(warning_box["x"]) <= 1
        assert abs(warning_box["y"]) <= 1
        assert warning_box["width"] >= viewport["width"] - 2
        assert sidebar_box["y"] >= warning_box["y"] + warning_box["height"] - 1
        assert warning.evaluate(
            "el => getComputedStyle(el).backgroundColor"
        ) == "rgb(254, 243, 199)"
        assert warning.evaluate("el => getComputedStyle(el).display") == "block"
        assert warning.evaluate(
            "el => getComputedStyle(el).textAlign"
        ) == "center"
        assert content_box["x"] >= warning_box["x"] - 1
        assert content_box["y"] >= warning_box["y"] - 1
        assert content_box["x"] + content_box["width"] <= (
            warning_box["x"] + warning_box["width"] + 1
        )
        assert content_box["y"] + content_box["height"] <= (
            warning_box["y"] + warning_box["height"] + 1
        )

        page.set_viewport_size({"width": 390, "height": 844})
        page.reload()
        expect(warning).to_be_visible()
        assert warning.evaluate(
            "el => getComputedStyle(el).textAlign"
        ) == "left"
        mobile_warning_box = warning.bounding_box()
        mobile_content_box = warning.evaluate(
            """
            el => {
              const range = document.createRange();
              range.selectNodeContents(el);
              const rect = range.getBoundingClientRect();
              return {
                x: rect.x,
                y: rect.y,
                width: rect.width,
                height: rect.height,
              };
            }
            """
        )
        assert mobile_warning_box is not None
        assert mobile_content_box["x"] >= mobile_warning_box["x"] - 1
        assert mobile_content_box["y"] >= mobile_warning_box["y"] - 1
        assert mobile_content_box["x"] + mobile_content_box["width"] <= (
            mobile_warning_box["x"] + mobile_warning_box["width"] + 1
        )
        assert mobile_content_box["y"] + mobile_content_box["height"] <= (
            mobile_warning_box["y"] + mobile_warning_box["height"] + 1
        )

        expect(page.locator('link[data-alias-description-styles="1"]')).to_have_count(1)
        expect(page.locator(".alias-table-head > span").nth(1)).to_contain_text(
            "Alias Name / Alias-Adresse"
        )

        create_link = page.locator("[data-open-create-alias]")
        expect(create_link).to_have_attribute("href", "/aliases?create=1")

        row = _amazon_row(page)
        expect(row.locator("[data-alias-edit-address] code")).to_have_text(
            "amazon-k7@example.org"
        )
        expect(
            row.locator('.edit-panel textarea[name="private_description"]')
        ).to_have_count(1)
        replacement_link = row.locator("[data-alias-workflow-replace]")
        expect(replacement_link).to_have_text("Alias ersetzen")
        expect(replacement_link).to_have_attribute("href", "/aliases?replace=1")
        expect(row.locator(".alias-toggle-action button")).to_have_text(
            "Alias deaktivieren"
        )
        expect(
            page.locator(
                'dialog[data-create-alias-dialog] textarea[name="private_description"]'
            )
        ).to_have_count(1)

        page.goto(f"{base_url}/aliases?replace=1")
        replacement_dialog = page.locator("dialog[data-alias-replacement-dialog][open]")
        expect(replacement_dialog).to_be_visible()
        expect(replacement_dialog.locator("[data-alias-replacement-form]")).to_have_attribute(
            "action", "/aliases/1/replace"
        )
        expect(replacement_dialog).to_contain_text("amazon-k7@example.org")

        page.goto(f"{base_url}/aliases?create=1")
        expect(page.locator("dialog[data-create-alias-dialog][open]")).to_be_visible()
    finally:
        context.close()


def test_alias_description_edit_and_table_preview(page: Page, base_url: str) -> None:
    _login_de(page, base_url)
    page.goto(f"{base_url}/aliases")

    expect(page.locator("[data-javascript-warning]")).to_have_count(0)

    identity_heading = page.locator(".alias-table-head > span").nth(1)
    expect(identity_heading).to_contain_text("Alias Name / Alias-Adresse")
    expect(page.locator('link[data-alias-description-styles="1"]')).to_have_count(1)
    assert identity_heading.evaluate(
        "el => getComputedStyle(el, '::after').content"
    ) == '"Beschreibung"'

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

    empty_info = _alias_row(page, "github-m4@example.org").locator(".alias-info")
    assert empty_info.evaluate(
        "el => getComputedStyle(el, '::after').content"
    ) == '"–"'

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

    address_box = row.locator(".alias-info > code").bounding_box()
    details_box = details.bounding_box()
    assert address_box is not None
    assert details_box is not None
    assert details_box["x"] > address_box["x"] + 40

    details.locator("summary").click()
    expect(details.locator(".alias-description-popover")).to_have_text(full_text)

    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    row = _amazon_row(page)
    details = row.locator(".alias-description-details")
    expect(details).to_be_visible()
    expect(details.locator(".alias-description-preview")).to_be_hidden()
    expect(details.locator(".alias-description-info")).to_be_visible()
    assert page.locator(".alias-table-head > span").nth(1).evaluate(
        "el => getComputedStyle(el, '::after').content"
    ) == '""'
    details.locator("summary").click()
    expect(details.locator(".alias-description-popover")).to_have_text(full_text)


def test_offline_pool_assignment_accepts_description(page: Page, base_url: str) -> None:
    _login_de(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    row = page.locator('.offline-pool-row[data-alias-id="10"]')
    details = row.locator('details[data-pool-inline-assign="10"]')
    expect(details).to_be_visible(timeout=5000)
    details.locator("summary").click()
    expect(details).to_have_attribute("open", "")

    name = details.locator('input[name="description"]')
    description = details.locator('textarea[name="private_description"]')
    expect(name.locator("xpath=..")).to_contain_text("Alias Name")
    expect(description.locator("xpath=..")).to_contain_text("Beschreibung")

    name.fill("Hotel")
    description.fill("Geschäftsreise und Hotelrechnungen")
    details.get_by_role("button", name="Zuordnen").click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/offline-pool(?:[?#].*)?$"))

    page.goto(f"{base_url}/aliases?q=feder-hafen-27")
    row = page.locator(
        '.alias-row:has([data-alias-select][data-address="feder-hafen-27@example.org"])'
    )
    expect(row.locator(".alias-info > strong")).to_have_text("Hotel")
    expect(row.locator(".alias-description-preview")).to_have_text(
        "Geschäftsreise und Hotelrechnungen"
    )