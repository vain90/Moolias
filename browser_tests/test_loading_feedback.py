from __future__ import annotations

import re

from playwright.sync_api import Page, expect


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def test_statistics_mode_history_choice_shows_processing_dialog(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/statistics")

    page.locator("[data-open-settings]").click()
    form = page.locator(".usage-mode-form")
    expect(form).to_be_visible()

    page.evaluate("document.body.dataset.statsEffective = 'off'")
    form.locator('select[name="mode"]').select_option("full")
    page.evaluate(
        """
        () => {
          const form = document.querySelector('.usage-mode-form');
          form.addEventListener('submit', (event) => {
            if (form.querySelector('input[name="backfill_history"]')) event.preventDefault();
          }, { capture: true });
        }
        """
    )

    form.locator('button[type="submit"]').click()
    choice = page.locator(".stats-history-choice-dialog")
    expect(choice).to_be_visible()
    choice.locator(".stats-history-choice-actions .button.primary").click()

    processing = page.locator(".stats-processing-dialog")
    expect(processing).to_be_visible()
    expect(processing).to_contain_text("Updating statistics")
    expect(processing).to_contain_text("available history is being evaluated")
    expect(processing.locator("progress")).to_be_visible()


def test_statistics_mode_downgrade_shows_confirmation_and_processing_dialog(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/statistics")

    page.locator("[data-open-settings]").click()
    form = page.locator(".usage-mode-form")
    expect(form).to_be_visible()

    page.evaluate("document.body.dataset.statsEffective = 'full'")
    form.locator('select[name="mode"]').select_option("domain")
    page.evaluate(
        """
        () => {
          const form = document.querySelector('.usage-mode-form');
          form.addEventListener('submit', (event) => {
            if (form.querySelector('input[name="confirm_downgrade"]')) event.preventDefault();
          }, { capture: true });
        }
        """
    )

    form.locator('button[type="submit"]').click()
    confirmation = page.locator('dialog[data-moolias-dialog="confirm"]')
    expect(confirmation).to_be_visible()
    expect(confirmation).to_contain_text("Change statistics mode?")
    expect(confirmation).to_contain_text("permanently deleted")
    confirmation.locator("[data-moolias-dialog-confirm]").click()

    expect(form.locator('input[name="confirm_downgrade"]')).to_have_value("1")
    processing = page.locator(".stats-processing-dialog")
    expect(processing).to_be_visible()
    expect(processing).to_contain_text("Updating statistics")
    expect(processing).to_contain_text("Details that are no longer permitted are being deleted")
    expect(processing.locator("progress")).to_be_visible()


def test_action_required_dialog_uses_server_rendered_content_without_loading_fetch(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    dialog = page.locator("dialog[data-action-required-dialog]")
    expect(dialog.locator("[data-action-required-unexpected-section]")).to_have_count(1)
    expect(dialog.locator("[data-action-sender-row]")).to_have_count(2)

    page.evaluate(
        """
        () => {
          window.__actionRequiredUnexpectedFetches = 0;
          const originalFetch = window.fetch.bind(window);
          window.fetch = (input, init) => {
            const url = input instanceof Request ? input.url : String(input);
            if (url.includes('/aliases') && url.includes('status=unexpected')) {
              window.__actionRequiredUnexpectedFetches += 1;
            }
            return originalFetch(input, init);
          };
        }
        """
    )

    page.locator("[data-action-required-open]").click()
    expect(dialog).to_be_visible()
    expect(dialog.locator("[data-action-required-unexpected-section]")).to_be_visible()
    expect(dialog.locator(".action-required-loading")).to_have_count(0)
    expect(dialog.locator(".action-required-progress")).to_have_count(0)
    assert page.evaluate("window.__actionRequiredUnexpectedFetches") == 0


def test_usage_evidence_link_has_spacing_from_usage_summary(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/statistics")

    link = page.locator(".usage-evidence-link")
    expect(link).to_be_visible()
    expect(link).to_have_class(re.compile(r"\btop-gap\b"))
    margin_top = link.evaluate("element => parseFloat(getComputedStyle(element).marginTop)")
    assert margin_top >= 10
