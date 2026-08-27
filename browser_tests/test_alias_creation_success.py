from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def test_alias_creation_shows_loading_overlay_while_post_is_delayed(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    page.locator("[data-open-create-alias]").click()
    create_dialog = page.locator("dialog[data-create-alias-dialog]")
    expect(create_dialog).to_be_visible()

    create_dialog.locator('input[name="description"]').fill("Loading overlay")
    create_dialog.locator('label.mode-option:has(input[value="custom"])').click()
    create_dialog.locator('input[name="local_part"]').fill("loading-overlay")

    page.evaluate(
        """
        () => {
          const form = document.querySelector("[data-alias-create-form]");
          form.addEventListener("submit", (event) => {
            event.preventDefault();
            window.setTimeout(() => {
              HTMLFormElement.prototype.submit.call(form);
            }, 1000);
          }, { once: true });
        }
        """
    )

    submit = create_dialog.locator('button[type="submit"]')
    submit.click()

    loading = page.locator("dialog[data-alias-create-loading-dialog]")
    expect(loading).to_be_visible(timeout=500)
    assert loading.evaluate("(dialog) => dialog.matches(':modal')")
    expect(loading).to_contain_text("Creating alias …")
    expect(loading.locator(".alias-create-loading-spinner")).to_be_visible()
    expect(submit).to_be_disabled()

    result = page.locator('dialog[data-alias-workflow-dialog][open]')
    expect(result).to_be_visible(timeout=5000)
    expect(result).to_contain_text("Alias created successfully")
    expect(result.locator("[data-alias-workflow-address]")).to_have_text(
        "loading-overlay@example.org"
    )
    expect(loading).not_to_be_visible()


def test_alias_creation_shows_copyable_activation_workflow(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=base_url,
    )

    page.locator("[data-open-create-alias]").click()
    create_dialog = page.locator("dialog[data-create-alias-dialog]")
    expect(create_dialog).to_be_visible()

    create_dialog.locator('input[name="description"]').fill("Issue 111")
    create_dialog.locator('label.mode-option:has(input[value="custom"])').click()
    create_dialog.locator('input[name="local_part"]').fill("issue-111")
    create_dialog.locator('button[type="submit"]').click()

    result = page.locator('dialog[data-alias-workflow-dialog][open]')
    expect(result).to_be_visible(timeout=5000)
    assert result.evaluate("(dialog) => dialog.matches(':modal')")

    close = result.locator(".dialog-close")
    close_box = close.bounding_box()
    icon_box = close.locator("svg.ui-icon").bounding_box()
    assert close_box and icon_box
    close_center = (
        close_box["x"] + close_box["width"] / 2,
        close_box["y"] + close_box["height"] / 2,
    )
    icon_center = (
        icon_box["x"] + icon_box["width"] / 2,
        icon_box["y"] + icon_box["height"] / 2,
    )
    assert abs(close_center[0] - icon_center[0]) <= 1
    assert abs(close_center[1] - icon_center[1]) <= 1

    expect(result).to_have_attribute("data-alias-workflow-state", "waiting")
    expect(result).to_contain_text("Alias created successfully")
    expect(result).to_contain_text("Waiting for the first email to this address.")
    expect(result.locator("[data-alias-workflow-name]")).to_have_text("Issue 111")
    expect(result.locator("[data-alias-workflow-address]")).to_have_text(
        "issue-111@example.org"
    )
    workflow_text = result.inner_text().casefold()
    assert "greylist" not in workflow_text
    assert "rspamd" not in workflow_text
    assert "mailcow" not in workflow_text

    result.locator("[data-alias-workflow-copy]").click()
    expect(result.locator("[data-alias-workflow-copy]")).to_have_text("Copied")
    assert page.evaluate("navigator.clipboard.readText()") == "issue-111@example.org"

    result.locator("[data-alias-workflow-done]").click()
    expect(result).to_have_count(0, timeout=5000)
    expect(_alias_row(page, "issue-111@example.org")).to_have_count(1, timeout=5000)
