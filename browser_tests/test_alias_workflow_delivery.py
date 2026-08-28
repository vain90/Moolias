from __future__ import annotations

import re
import sqlite3
import time
from pathlib import Path

from playwright.sync_api import Page, expect

OLD_ADDRESS = "amazon-k7@example.org"
NEW_ADDRESS = "amazon-migrate@example.org"


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _record_delivery(
    database: Path,
    workflow_id: int,
    *,
    old: bool = False,
    new: bool = False,
) -> None:
    received_at = int(time.time())
    assignments = []
    values: list[int] = []
    if old:
        assignments.append("old_mail_received_at = ?")
        values.append(received_at)
    if new:
        assignments.extend(
            [
                "new_mail_received_at = ?",
                "watcher_active = 0",
                "bypass_clear_requested_at = ?",
            ]
        )
        values.extend([received_at, received_at])
    assert assignments
    values.append(workflow_id)
    with sqlite3.connect(database, timeout=10) as connection:
        connection.execute(
            f"UPDATE alias_workflows SET {', '.join(assignments)} WHERE id = ?",
            values,
        )


def _deactivation_form(workflow):
    return workflow.locator("form.alias-workflow-deactivation-form")


def _deactivation_option(workflow, mode: str):
    return _deactivation_form(workflow).locator(f'input[name="mode"][value="{mode}"]')


def test_replacement_delivery_updates_ui_and_all_deactivation_choices(
    page: Page,
    base_url: str,
    e2e_db_path: Path,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/aliases?replace=1")

    replacement = page.locator("dialog[data-alias-replacement-dialog][open]")
    expect(replacement).to_be_visible()
    replacement.locator(
        'label.mode-option:has(input[name="mode"][value="custom"])'
    ).click()
    replacement.locator('input[name="local_part"]').fill("amazon-migrate")
    replacement.locator('button[type="submit"]').click()

    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_be_visible(timeout=5000)
    workflow_id_text = workflow.get_attribute("data-alias-workflow-id")
    assert workflow_id_text
    workflow_id = int(workflow_id_text)
    expect(workflow).to_have_attribute("data-alias-workflow-state", "waiting")
    expect(workflow.locator(".alias-workflow-wait-spinner")).to_be_visible()
    expect(workflow).to_contain_text("Waiting for the first email to this alias.")
    expect(workflow).not_to_contain_text("only feedback and is not a requirement")

    old_row = page.locator(
        f'.alias-row:has([data-alias-select][data-address="{OLD_ADDRESS}"])'
    )
    new_row = page.locator(
        f'.alias-row:has([data-alias-select][data-address="{NEW_ADDRESS}"])'
    )
    expect(old_row).to_have_class(re.compile(r"\balias-migration-old\b"))
    expect(new_row).to_have_class(re.compile(r"\balias-migration-new\b"))

    page.evaluate("window.__mooliasNoReload = 'alive'")
    workflow.locator("[data-alias-workflow-done]").click()
    expect(workflow).not_to_be_visible()
    assert page.evaluate("window.__mooliasNoReload") == "alive"
    assert "workflow=" not in page.url

    status_link = new_row.locator(
        ".alias-workflow-row-state [data-open-alias-workflow]"
    )
    expect(status_link).to_have_attribute("href", f"/aliases?workflow={workflow_id}")
    with page.expect_navigation(wait_until="load"):
        status_link.click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    workflow = page.locator(
        f'dialog[data-alias-workflow-dialog][data-alias-workflow-id="{workflow_id}"]'
    )
    expect(workflow).to_be_visible(timeout=5000)
    assert workflow.evaluate("element => element.matches(':modal')")
    assert page.evaluate("window.__mooliasNoReload") is None

    workflow.locator(".dialog-close").click()
    expect(workflow).not_to_be_visible()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases$"))

    new_row = page.locator(
        f'.alias-row:has([data-alias-select][data-address="{NEW_ADDRESS}"])'
    )
    page.evaluate("window.__mooliasNoReload = 'alive'")
    new_alias_id = new_row.locator("[data-alias-select]").get_attribute("value")
    assert new_alias_id
    new_row.locator("details.alias-edit-action > summary").click()
    deactivation_link = new_row.locator("[data-open-replacement-deactivation]")
    expect(deactivation_link).to_have_attribute("href", f"/aliases?deactivate={new_alias_id}")
    with page.expect_navigation(wait_until="load"):
        deactivation_link.click()
    assert page.evaluate("window.__mooliasNoReload") is None
    expect(page).to_have_url(
        re.compile(rf"{re.escape(base_url)}/aliases\?deactivate={new_alias_id}$")
    )
    replacement_deactivation = page.locator(
        "dialog[data-replacement-deactivation-dialog]"
    )
    expect(replacement_deactivation).to_be_visible(timeout=5000)
    assert replacement_deactivation.evaluate("element => element.matches(':modal')")
    expect(page.locator("dialog:modal")).to_have_count(1)
    page.evaluate("window.__mooliasNoReload = 'alive'")
    replacement_deactivation.locator(".dialog-close").click()
    expect(replacement_deactivation).not_to_be_visible()
    assert page.evaluate("window.__mooliasNoReload") == "alive"
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases$"))

    new_row = page.locator(
        f'.alias-row:has([data-alias-select][data-address="{NEW_ADDRESS}"])'
    )
    status_link = new_row.locator(
        ".alias-workflow-row-state [data-open-alias-workflow]"
    )
    expect(status_link).to_have_attribute("href", f"/aliases?workflow={workflow_id}")
    with page.expect_navigation(wait_until="load"):
        status_link.click()
    workflow = page.locator(
        f'dialog[data-alias-workflow-dialog][data-alias-workflow-id="{workflow_id}"]'
    )
    expect(workflow).to_be_visible(timeout=5000)

    deactivation = workflow.locator(".alias-workflow-deactivation")
    expect(deactivation).to_be_visible()
    expect(_deactivation_option(workflow, "later")).to_be_checked()
    expect(_deactivation_option(workflow, "now")).to_have_count(1)
    expect(_deactivation_option(workflow, "1d")).to_have_count(1)
    expect(_deactivation_option(workflow, "7d")).to_have_count(1)
    expect(_deactivation_option(workflow, "30d")).to_have_count(1)
    expect(workflow.locator('input[name="confirm_now"]')).to_have_count(0)

    initial_url = page.url
    deactivation.locator('label:has(input[name="mode"][value="1d"])').click()
    expect(_deactivation_option(workflow, "1d")).to_be_checked()
    assert page.url == initial_url
    expect(workflow).not_to_contain_text("The old address will be disabled in 1 day.")

    _deactivation_form(workflow).locator('button[type="submit"]').click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_contain_text("The old address will be disabled in 1 day.")
    expect(_deactivation_option(workflow, "1d")).to_be_checked()
    expect(workflow.locator(".alias-workflow-wait-spinner")).to_be_visible()

    deactivation = workflow.locator(".alias-workflow-deactivation")
    deactivation.locator('label:has(input[name="mode"][value="later"])').click()
    expect(_deactivation_option(workflow, "later")).to_be_checked()
    _deactivation_form(workflow).locator('button[type="submit"]').click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).not_to_contain_text("The old address will be disabled in 1 day.")

    _record_delivery(e2e_db_path, workflow_id, old=True)
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_have_attribute(
        "data-alias-workflow-state",
        "old_received",
        timeout=6000,
    )
    expect(workflow).to_contain_text("An email still arrived at the old address.")
    expect(workflow).to_contain_text("No email has been detected at the new address yet.")
    expect(workflow.locator(".alias-workflow-wait-spinner")).to_be_visible()
    expect(workflow.locator(".alias-workflow-deactivation")).to_be_visible()

    deactivation = workflow.locator(".alias-workflow-deactivation")
    deactivation.locator('label:has(input[name="mode"][value="30d"])').click()
    _deactivation_form(workflow).locator('button[type="submit"]').click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_contain_text("The old address will be disabled in 30 days.")

    deactivation = workflow.locator(".alias-workflow-deactivation")
    deactivation.locator('label:has(input[name="mode"][value="later"])').click()
    _deactivation_form(workflow).locator('button[type="submit"]').click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(_deactivation_option(workflow, "later")).to_be_checked()

    workflow.locator("[data-alias-workflow-done]").click()
    expect(workflow).not_to_be_visible()

    _record_delivery(e2e_db_path, workflow_id, new=True)
    page.goto(f"{base_url}/overview?action=required")
    action_dialog = page.locator("dialog[data-action-required-dialog]")
    expect(action_dialog).to_be_visible()
    action = action_dialog.locator(
        f'[data-open-alias-workflow="{workflow_id}"]'
    )
    expect(action).to_contain_text("Complete alias change")
    expect(action).to_have_attribute("href", f"/aliases?workflow={workflow_id}")
    page.evaluate("window.__actionRequiredNoReload = 'alive'")

    with page.expect_navigation(wait_until="load"):
        action.click()
    expect(page).to_have_url(
        re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"),
        timeout=5000,
    )
    assert page.evaluate("window.__actionRequiredNoReload") is None
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_be_visible(timeout=5000)
    expect(workflow).to_have_attribute("data-alias-workflow-state", "received")
    expect(workflow).to_contain_text("New email received. Please check your inbox.")
    expect(workflow.locator(".alias-workflow-wait-spinner")).to_have_count(0)
    expect(page.locator('link[data-alias-workflow-styles="1"]')).to_have_count(1)
    status_background = workflow.locator(".alias-workflow-status.received").evaluate(
        "element => getComputedStyle(element).backgroundColor"
    )
    assert status_background != "rgba(0, 0, 0, 0)"

    deactivation = workflow.locator(".alias-workflow-deactivation")
    deactivation.locator('label:has(input[name="mode"][value="now"])').click()
    expect(_deactivation_option(workflow, "now")).to_be_checked()
    _deactivation_form(workflow).locator('button[type="submit"]').click()

    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_have_attribute("data-alias-workflow-state", "received")
    expect(workflow).to_contain_text("Alias change completed.")

    page.goto(f"{base_url}/aliases")
    old_row = page.locator(
        f'.alias-row:has([data-alias-select][data-address="{OLD_ADDRESS}"])'
    )
    new_row = page.locator(
        f'.alias-row:has([data-alias-select][data-address="{NEW_ADDRESS}"])'
    )
    expect(old_row.locator("[data-alias-select]")).to_have_attribute("data-active", "0")
    expect(new_row.locator("[data-alias-select]")).to_have_attribute("data-active", "1")
    expect(old_row).not_to_have_class(re.compile(r"\balias-migration-(?:old|new)\b"))
    expect(new_row).not_to_have_class(re.compile(r"\balias-migration-(?:old|new)\b"))

    old_history = old_row.locator(".alias-replacement-history-link")
    expect(old_history).to_contain_text(f"Replaced by · {NEW_ADDRESS}")
    expect(old_history).to_have_attribute(
        "href",
        f"/aliases?q={NEW_ADDRESS.replace('@', '%40')}",
    )
    new_history = new_row.locator(".alias-replacement-history-link")
    expect(new_history).to_contain_text(f"Replaced · {OLD_ADDRESS}")
    expect(new_history).to_have_attribute(
        "href",
        f"/aliases?q={OLD_ADDRESS.replace('@', '%40')}",
    )

    old_history.click()
    expect(page).to_have_url(re.compile(r"/aliases\?q=amazon-migrate%40example\.org$"))
    expect(
        page.locator(f'[data-alias-select][data-address="{NEW_ADDRESS}"]')
    ).to_have_count(1)
    expect(
        page.locator(f'[data-alias-select][data-address="{OLD_ADDRESS}"]')
    ).to_have_count(0)
