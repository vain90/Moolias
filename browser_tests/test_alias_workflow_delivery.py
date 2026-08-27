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


def _deactivation_form(workflow, mode: str):
    return workflow.locator(
        f'form:has(input[name="mode"][value="{mode}"])'
    )


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

    _record_delivery(e2e_db_path, workflow_id, old=True)
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_have_attribute(
        "data-alias-workflow-state",
        "old_received",
        timeout=6000,
    )
    expect(workflow).to_contain_text("An email still arrived at the old address.")
    expect(workflow).to_contain_text("The new address is still being checked.")
    expect(workflow.locator(".alias-workflow-deactivation")).to_have_count(0)

    _record_delivery(e2e_db_path, workflow_id, new=True)
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_have_attribute(
        "data-alias-workflow-state",
        "received",
        timeout=6000,
    )
    expect(workflow).to_contain_text("New email received. Please check your inbox.")

    deactivation = workflow.locator(".alias-workflow-deactivation")
    expect(deactivation).to_be_visible()
    later = _deactivation_form(workflow, "later")
    expect(later.locator("button")).to_have_class(re.compile(r"\bprimary\b"))

    _deactivation_form(workflow, "7d").locator("button").click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_contain_text("The old address will be disabled in 7 days.")

    _deactivation_form(workflow, "later").locator("button").click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).not_to_contain_text("The old address will be disabled in 7 days.")
    expect(_deactivation_form(workflow, "later").locator("button")).to_have_class(
        re.compile(r"\bprimary\b")
    )

    _deactivation_form(workflow, "30d").locator("button").click()
    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_contain_text("The old address will be disabled in 30 days.")

    now_form = _deactivation_form(workflow, "now")
    confirmation = now_form.locator('input[name="confirm_now"]')
    expect(confirmation).to_have_attribute("required", "")
    confirmation.check()
    now_form.locator('button[type="submit"]').click()

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
