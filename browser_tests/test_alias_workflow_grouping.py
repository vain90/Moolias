from __future__ import annotations

import re

from playwright.sync_api import Page, expect

OLD_ADDRESS = "github-m4@example.org"
NEW_ADDRESS = "github-safe@example.org"


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))


def _create_named_alias(page: Page, base_url: str, name: str, local_part: str) -> None:
    page.goto(f"{base_url}/aliases?create=1")
    dialog = page.locator("dialog[data-create-alias-dialog][open]")
    expect(dialog).to_be_visible()
    dialog.locator('input[name="description"]').fill(name)
    dialog.locator('label.mode-option:has(input[value="custom"])').click()
    dialog.locator('input[name="local_part"]').fill(local_part)
    dialog.locator('button[type="submit"]').click()

    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_be_visible(timeout=5000)
    workflow.locator("[data-alias-workflow-done]").click()
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


def _assert_pair(page: Page, workflow_id: str) -> None:
    rows = page.locator(f'[data-alias-workflow-row="{workflow_id}"]')
    expect(rows).to_have_count(2)
    expect(rows.nth(0)).to_have_attribute("data-alias-workflow-role", "old")
    expect(rows.nth(1)).to_have_attribute("data-alias-workflow-role", "new")
    expect(rows.nth(0)).to_contain_text(OLD_ADDRESS)
    expect(rows.nth(1)).to_contain_text(NEW_ADDRESS)


def test_replacement_pair_stays_together_under_search_sort_filter_and_pagination(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    # Together with the existing Amazon and Archive rows, these seven aliases put
    # the GitHub replacement group exactly across a 10-row page boundary if rows
    # were paginated independently instead of as one replacement group.
    for number in range(1, 8):
        _create_named_alias(
            page,
            base_url,
            f"B{number:02d}",
            f"pair-b{number:02d}",
        )

    page.goto(f"{base_url}/aliases?replace=2")
    replacement = page.locator("dialog[data-alias-replacement-dialog][open]")
    expect(replacement).to_be_visible()
    replacement.locator(
        'label.mode-option:has(input[name="mode"][value="custom"])'
    ).click()
    replacement.locator('input[name="local_part"]').fill("github-safe")
    replacement.locator('button[type="submit"]').click()

    workflow = page.locator("dialog[data-alias-workflow-dialog][open]")
    expect(workflow).to_be_visible(timeout=5000)
    workflow_id = workflow.get_attribute("data-alias-workflow-id")
    assert workflow_id

    page.goto(
        f"{base_url}/aliases?q=github-safe&status=active&per_page=10"
        "&sort=purpose&direction=asc"
    )
    _assert_pair(page, workflow_id)
    expect(page.locator(".alias-list .alias-row")).to_have_count(2)

    page.goto(
        f"{base_url}/aliases?status=active&per_page=10&sort=purpose&direction=asc&page=1"
    )
    expect(page.locator(f'[data-alias-workflow-row="{workflow_id}"]')).to_have_count(0)
    expect(page.locator(".alias-list .alias-row")).to_have_count(9)

    page.goto(
        f"{base_url}/aliases?status=active&per_page=10&sort=purpose&direction=asc&page=2"
    )
    _assert_pair(page, workflow_id)

    page.goto(
        f"{base_url}/aliases?status=active&per_page=25&sort=usage&direction=desc"
    )
    _assert_pair(page, workflow_id)
