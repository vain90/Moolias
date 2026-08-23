from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def test_public_branding_and_language_dropdown(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/", wait_until="networkidle")

    logo = page.locator(".hero-brand-logo")
    expect(logo).to_be_visible()
    expect(logo).to_have_attribute("src", re.compile(r"/static/icon-192\.webp"))

    dropdown = page.locator("details[data-language-dropdown]")
    expect(dropdown).to_be_visible()
    trigger = dropdown.locator("summary")
    expect(trigger.locator("svg.language-flag")).to_have_count(1)
    expect(trigger).not_to_contain_text("Deutsch")
    expect(trigger).not_to_contain_text("English")
    trigger.click()

    german = dropdown.locator('a.language-dropdown-option[lang="de"]')
    english = dropdown.locator('a.language-dropdown-option[lang="en"]')
    expect(german).to_be_visible()
    expect(english).to_be_visible()
    expect(german).to_contain_text("Deutsch")
    expect(english).to_contain_text("English")
    expect(german.locator("svg.language-flag")).to_have_count(1)
    expect(english.locator("svg.language-flag")).to_have_count(1)

    english.click()
    expect(page.locator("html")).to_have_attribute("lang", "en")
    trigger = page.locator("details[data-language-dropdown] summary")
    expect(trigger.locator("svg.language-flag")).to_have_count(1)
    expect(trigger).not_to_contain_text("English")


def test_logged_in_shell_uses_moolias_logo(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))

    logo = page.locator(".brand-mark-logo img")
    expect(logo).to_be_visible()
    expect(logo).to_have_attribute("src", re.compile(r"/static/icon-192\.webp"))

    language_dropdown = page.locator("header .language-dropdown")
    expect(language_dropdown).to_be_visible()
    trigger = language_dropdown.locator("summary")
    expect(trigger.locator("svg.language-flag")).to_have_count(1)
    expect(trigger).not_to_contain_text("Deutsch")

    language_box = language_dropdown.bounding_box()
    actions_box = page.locator("header .header-actions").bounding_box()
    assert language_box is not None
    assert actions_box is not None
    assert language_box["x"] + language_box["width"] <= actions_box["x"] + 1


def test_web_app_manifest_uses_moolias_icons(page: Page, base_url: str) -> None:
    response = page.request.get(f"{base_url}/static/manifest.webmanifest")
    assert response.ok
    manifest = response.json()

    assert manifest["name"] == "Moolias"
    assert manifest["display"] == "standalone"
    assert manifest["theme_color"] == "#07162f"

    icons = {item["sizes"]: item for item in manifest["icons"]}
    assert icons["180x180"]["src"] == "/static/icon-180.png"
    assert icons["180x180"]["type"] == "image/png"
    assert icons["192x192"]["src"] == "/static/icon-192.webp"
    assert icons["192x192"]["type"] == "image/webp"
    assert icons["512x512"]["src"] == "/static/icon-512.webp"
    assert icons["512x512"]["type"] == "image/webp"
    assert "maskable" in icons["192x192"]["purpose"]
    assert "maskable" in icons["512x512"]["purpose"]

    for item in icons.values():
        icon_response = page.request.get(f"{base_url}{item['src']}")
        assert icon_response.ok
        assert icon_response.headers["content-type"].startswith(item["type"])
        body = icon_response.body()
        if item["type"] == "image/png":
            assert body.startswith(b"\x89PNG\r\n\x1a\n")
        else:
            assert body.startswith(b"RIFF")
            assert body[8:12] == b"WEBP"
