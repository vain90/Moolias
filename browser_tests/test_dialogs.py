from __future__ import annotations

import re
from pathlib import Path

from playwright.sync_api import Locator, Page, expect

UNUSED_POOL = "feder-hafen-27@example.org"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


def _pool_item(page: Page, address: str):
    return page.locator(".offline-pool-row").filter(has_text=address)


def _dialog_surface_point(dialog: Locator) -> dict[str, float]:
    point = dialog.evaluate(
        """dialog => {
          const rect = dialog.getBoundingClientRect();
          for (let y = rect.top + 4; y < rect.bottom - 4; y += 4) {
            for (let x = rect.left + 4; x < rect.right - 4; x += 4) {
              if (document.elementFromPoint(x, y) === dialog) return { x, y };
            }
          }
          return null;
        }"""
    )
    assert point is not None, "dialog has no visible surface point owned by the <dialog> element"
    return point


def _click_dialog_surface(page: Page, dialog: Locator, *, times: int = 1) -> None:
    point = _dialog_surface_point(dialog)
    for _ in range(times):
        page.mouse.click(point["x"], point["y"])
        expect(dialog).to_be_visible()


def _click_dialog_backdrop(page: Page, dialog: Locator) -> None:
    box = dialog.bounding_box()
    assert box is not None
    if box["x"] >= 8:
        x = box["x"] - 6
        y = box["y"] + box["height"] / 2
    else:
        x = box["x"] + box["width"] / 2
        y = max(1, box["y"] - 6)
    page.mouse.click(x, y)


def test_destructive_confirmation_is_internal_and_cancellable(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    unused = _pool_item(page, UNUSED_POOL)
    unused.locator('form[action$="/delete"] button').click()

    dialog = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(dialog).to_be_visible()
    expect(dialog.locator('[data-moolias-dialog-cancel]')).to_be_focused()
    dialog.locator('[data-moolias-dialog-cancel]').click()
    expect(_pool_item(page, UNUSED_POOL)).to_have_count(1)

    _pool_item(page, UNUSED_POOL).locator('form[action$="/delete"] button').click()
    dialog = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(dialog).to_be_visible()
    dialog.locator('[data-moolias-dialog-confirm]').click()
    expect(_pool_item(page, UNUSED_POOL)).to_have_count(0, timeout=5000)


def test_dialog_surface_clicks_do_not_dismiss_create_alias_or_help(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    opener = page.locator("[data-open-create-alias]")
    opener.click()
    dialog = page.locator("dialog[data-create-alias-dialog]")
    expect(dialog).to_be_visible()

    alias_name = dialog.locator('input[name="description"]')
    alias_name.fill("Amazon")
    _click_dialog_surface(page, dialog, times=12)
    expect(alias_name).to_have_value("Amazon")

    dialog.locator("label").first.click(position={"x": 5, "y": 5})
    expect(dialog).to_be_visible()
    expect(alias_name).to_have_value("Amazon")

    _click_dialog_backdrop(page, dialog)
    expect(dialog).not_to_be_visible()

    for _ in range(5):
        opener.click()
        expect(dialog).to_be_visible()
        _click_dialog_surface(page, dialog, times=3)
        dialog.locator("[data-close-create-alias]").click()
        expect(dialog).not_to_be_visible()

    page.locator("[data-open-help-dialog]").click()
    help_dialog = page.locator("dialog[data-help-dialog]")
    expect(help_dialog).to_be_visible()
    _click_dialog_surface(page, help_dialog, times=8)
    expect(help_dialog).to_be_visible()
    _click_dialog_backdrop(page, help_dialog)
    expect(help_dialog).not_to_be_visible()


def test_shared_confirmation_distinguishes_dialog_surface_from_backdrop(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    _pool_item(page, UNUSED_POOL).locator('form[action$="/delete"] button').click()
    dialog = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(dialog).to_be_visible()

    _click_dialog_surface(page, dialog, times=10)
    expect(dialog).to_be_visible()
    expect(_pool_item(page, UNUSED_POOL)).to_have_count(1)

    _click_dialog_backdrop(page, dialog)
    expect(dialog).not_to_be_visible()
    expect(_pool_item(page, UNUSED_POOL)).to_have_count(1)


def test_create_alias_dialog_surface_is_safe_on_mobile(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)

    page.locator("[data-open-create-alias]").click()
    dialog = page.locator("dialog[data-create-alias-dialog]")
    expect(dialog).to_be_visible()
    alias_name = dialog.locator('input[name="description"]')
    alias_name.fill("Mobile alias")

    _click_dialog_surface(page, dialog, times=12)
    expect(dialog).to_be_visible()
    expect(alias_name).to_have_value("Mobile alias")

    page.keyboard.press("Escape")
    expect(dialog).not_to_be_visible()


def test_statistics_downgrade_uses_internal_confirmation(page: Page, base_url: str) -> None:
    _login(page, base_url)

    page.locator("[data-open-settings]").click()
    settings_drawer = page.locator("[data-settings-drawer]")
    expect(settings_drawer).to_have_attribute("aria-hidden", "false")

    form = settings_drawer.locator(".usage-mode-form")
    form.locator('select[name="mode"]').select_option("basic")
    form.locator('button[type="submit"]').click()

    dialog = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(dialog).to_be_visible()
    dialog.locator('[data-moolias-dialog-cancel]').click()
    expect(page.locator("body")).to_have_attribute("data-stats-effective", "full")


def test_bulk_failure_is_rendered_inside_moolias(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.route("**/aliases/bulk", lambda route: route.fulfill(status=500, body="failed"))

    page.locator("[data-alias-select]").first.check()
    action_select = page.locator("[data-bulk-action-select]")
    expect(action_select).to_be_enabled()
    action_select.select_option("disable")
    apply = page.locator(".bulk-actions button")
    expect(apply).to_be_enabled()
    apply.click()

    dialog = page.locator('dialog[data-moolias-dialog="message"]')
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog.locator('[data-moolias-dialog-confirm]')).to_be_visible()


def test_confirmation_fits_mobile_viewport(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    _pool_item(page, UNUSED_POOL).locator('form[action$="/delete"] button').click()
    dialog = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(dialog).to_be_visible()

    box = dialog.bounding_box()
    assert box is not None
    assert box["x"] >= 0
    assert box["y"] >= 0
    assert box["x"] + box["width"] <= 390
    assert box["y"] + box["height"] <= 844


def test_newsletter_one_click_does_not_fall_back_to_stale_generic_confirm(
    page: Page,
    base_url: str,
) -> None:
    page.set_content(
        f"""
        <!doctype html>
        <html lang="de">
          <head><base href="{base_url}/"></head>
          <body>
            <section data-newsletter-page>
              <form
                method="post"
                action="/newsletters/1/unsubscribe"
                data-confirm="Diesen Newsletter jetzt per One-Click abmelden?"
              >
                <input type="hidden" name="csrf_token" value="e2e">
                <button type="submit">Abmelden</button>
              </form>
            </section>
          </body>
        </html>
        """
    )

    page.add_script_tag(path=str(REPOSITORY_ROOT / "moolias/static/dialogs.js"))
    # app.js intentionally runs first and binds the legacy data-confirm listener.
    page.add_script_tag(path=str(REPOSITORY_ROOT / "moolias/static/app.js"))
    page.add_script_tag(path=str(REPOSITORY_ROOT / "moolias/static/newsletters.js"))

    page.route(
        "**/newsletters/1/unsubscribe",
        lambda route: route.fulfill(
            status=200,
            content_type="text/html",
            body="<html><body>newsletter submit reached server</body></html>",
        ),
    )

    page.locator('form[action="/newsletters/1/unsubscribe"] button').click()
    dialog = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(dialog).to_be_visible()
    expect(dialog.locator("h2")).to_have_text("Newsletter abmelden?")
    expect(dialog).not_to_contain_text("undefined")

    with page.expect_request("**/newsletters/1/unsubscribe") as request_info:
        dialog.locator('[data-moolias-dialog-confirm]').click()

    assert request_info.value.method == "POST"
    expect(page.locator("body")).to_contain_text("newsletter submit reached server", timeout=5000)
