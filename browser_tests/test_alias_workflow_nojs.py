from __future__ import annotations

import re

from playwright.sync_api import Browser, expect


def test_alias_creation_workflow_works_without_javascript(
    browser: Browser,
    base_url: str,
) -> None:
    context = browser.new_context(java_script_enabled=False)
    try:
        page = context.new_page()
        page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
        expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))

        page.goto(f"{base_url}/aliases?create=1")
        create_dialog = page.locator("dialog[data-create-alias-dialog][open]")
        expect(create_dialog).to_be_visible()
        create_dialog.locator('input[name="description"]').fill("No JavaScript")

        with page.expect_navigation(wait_until="load"):
            create_dialog.locator('button[type="submit"]').click()

        workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
        expect(workflow).to_be_visible()
        expect(workflow).to_have_attribute("data-alias-workflow-state", "waiting")
        expect(workflow).to_contain_text("Alias created successfully")
        expect(workflow).to_contain_text("Waiting for the first email to this address.")
        expect(workflow.locator("[data-alias-workflow-name]")).to_have_text("No JavaScript")
        address = workflow.locator("[data-alias-workflow-address]").inner_text().strip()
        assert address.endswith("@example.org")

        with page.expect_navigation(wait_until="load"):
            workflow.get_by_role("button", name="Stop waiting").click()

        workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
        expect(workflow).to_be_visible()
        expect(workflow).to_have_attribute("data-alias-workflow-state", "stopped")
        expect(workflow).to_contain_text("The check is paused. You can resume it at any time.")
        expect(workflow.locator("[data-alias-workflow-address]")).to_have_text(address)

        page.goto(f"{base_url}/aliases")
        row = page.locator(
            f'.alias-row:has([data-alias-select][data-address="{address}"])'
        )
        expect(row).to_have_count(1)
        expect(row.locator("[data-alias-select]")).to_have_attribute("data-active", "1")
    finally:
        context.close()
