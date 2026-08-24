from __future__ import annotations

import re

from playwright.sync_api import Page, expect

AMAZON = "amazon-k7@example.org"
GITHUB = "github-m4@example.org"
ARCHIVE = "archive-r8@example.org"
UNUSED_POOL = "feder-hafen-27@example.org"
USED_POOL = "mond-segel-42@example.org"


def _alias_row(page: Page, address: str):
    return page.locator(
        f'.alias-row:has([data-alias-select][data-address="{address}"])'
    )


def _pool_item(page: Page, address: str):
    return page.locator(".offline-pool-row").filter(has_text=address)


def _open_sender_dialog(page: Page, owner):
    trigger = owner.locator("button.sender-stats-trigger")
    expect(trigger).to_be_visible()
    dialog_id = trigger.get_attribute("aria-controls")
    assert dialog_id
    trigger.click()
    dialog = page.locator(f"#{dialog_id}")
    expect(dialog).to_be_visible()
    return dialog


def _login(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-alias-results-region]")).to_be_visible()


def _open_action_required(page: Page, base_url: str):
    page.goto(f"{base_url}/overview")
    trigger = page.locator("[data-action-required-open]")
    expect(trigger).to_be_visible()
    trigger.click()
    expect(page).to_have_url(
        re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"),
        timeout=5000,
    )
    dialog = page.locator("dialog[data-action-required-dialog]")
    expect(dialog).to_be_visible(timeout=5000)
    return dialog


def test_login_lands_on_overview_before_alias_management(page: Page, base_url: str) -> None:
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    expect(page.locator('.side-nav-link[href="/overview"]')).to_have_attribute(
        "aria-current", "page"
    )


def test_login_does_not_auto_open_action_required_without_login_marker(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    dialog = _open_action_required(page, base_url)
    expect(dialog).to_contain_text("Action required")
    expect(dialog).to_contain_text("Used offline aliases")
    expect(dialog).to_contain_text(USED_POOL)
    expect(dialog).to_contain_text("Unexpected senders")
    expect(dialog).to_contain_text(AMAZON)
    expect(dialog).to_contain_text("odd@unexpected.example")
    expect(page.locator("dialog[open]")).to_have_count(1)

    dialog.locator(".dialog-close").click()
    page.reload()
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)


def test_fresh_login_auto_opens_action_required_on_overview_once(
    page: Page,
    base_url: str,
) -> None:
    page.goto(f"{base_url}/", wait_until="networkidle")
    page.evaluate(
        "sessionStorage.setItem('moolias-action-required-after-login', '1')"
    )
    page.goto(f"{base_url}/oauth/callback?code=e2e&state=e2e")

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    dialog = page.locator("dialog[data-action-required-dialog]")
    expect(dialog).to_be_visible(timeout=5000)
    expect(dialog).to_contain_text("Used offline aliases")
    expect(dialog).to_contain_text(USED_POOL)
    expect(dialog).to_contain_text("Unexpected senders")
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))

    dialog.locator(".dialog-close").click()
    page.reload()
    expect(page.locator("dialog[data-action-required-dialog][open]")).to_have_count(0)


def test_live_search_keeps_server_unexpected_filter_and_filtering_works(
    page: Page,
    base_url: str,
) -> None:
    requested_urls: list[str] = []
    page.on("request", lambda request: requested_urls.append(request.url))
    _login(page, base_url)

    search = page.locator("[data-live-search]")
    search.fill("GitHub")

    expect(page.locator(".alias-list .alias-row")).to_have_count(1, timeout=5000)
    expect(_alias_row(page, GITHUB)).to_have_count(1)

    unexpected = page.locator("[data-unexpected-filter]")
    expect(unexpected).to_be_visible()
    expect(unexpected.locator("span")).to_have_text("1", timeout=5000)

    page.locator("[data-search-clear]").click()
    expect(_alias_row(page, AMAZON)).to_have_count(1, timeout=5000)
    expect(unexpected).to_be_visible()

    unexpected.click()
    expect(page).to_have_url(re.compile(r"[?&]status=unexpected(?:&|$)"))
    expect(page.locator(".alias-list .alias-row")).to_have_count(1, timeout=5000)
    expect(_alias_row(page, AMAZON)).to_have_count(1)
    expect(_alias_row(page, GITHUB)).to_have_count(0)

    search = page.locator("[data-live-search]")
    search.fill("GitHub")
    expect(page.locator(".alias-list .alias-row")).to_have_count(0, timeout=5000)
    expect(page).to_have_url(re.compile(r"[?&]status=unexpected(?:&|$)"))

    assert not any(
        "status=all" in url and "per_page=100" in url
        for url in requested_urls
    )


def test_sender_review_updates_action_required_with_fresh_state(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    sender_dialog = _open_sender_dialog(page, _alias_row(page, AMAZON))
    expect(sender_dialog).to_contain_text("news@amazon.de")
    unexpected_sender = sender_dialog.locator(".sender-stats-row.unexpected")
    expect(unexpected_sender).to_contain_text("odd@unexpected.example")

    unexpected_sender.locator('.sender-review-form button[type="submit"]').click()
    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/aliases(?:[?#].*)?$"))
    expect(page.locator("[data-unexpected-filter] span")).to_have_text("0", timeout=5000)

    dialog = _open_action_required(page, base_url)
    expect(dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)).to_have_count(0)
    expect(dialog).to_contain_text("Used offline aliases")


def test_action_required_can_disable_per_alias_unexpected_review(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    dialog = _open_action_required(page, base_url)

    amazon_review = dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)
    checkbox = amazon_review.locator(".sender-review-settings input[type=checkbox]")
    expect(checkbox).not_to_be_checked()
    with page.expect_navigation(wait_until="load"):
        checkbox.check()

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    page.goto(f"{base_url}/aliases")
    expect(page.locator("[data-unexpected-filter] span")).to_have_text("0", timeout=5000)


def test_action_required_can_replace_alias_and_continue(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    action_dialog = _open_action_required(page, base_url)

    amazon_review = action_dialog.locator(".unexpected-review-alias").filter(has_text=AMAZON)
    replace_button = amazon_review.locator('[data-review-replace-alias="1"]')
    expect(replace_button).to_be_visible()
    replace_button.click()

    replacement_dialog = page.locator("dialog.assign-dialog[open]").filter(
        has=page.locator('input[name="replacement-mode"]')
    )
    expect(replacement_dialog).to_be_visible()
    replacement_dialog.locator(
        'label.mode-option:has(input[value="custom"])'
    ).click()
    replacement_dialog.locator(".address-input input").fill("amazon-safe")
    replacement_dialog.locator(".button.primary").click()

    result_dialog = page.locator("dialog.assign-dialog-single[open]").filter(
        has_text="Alias replaced"
    )
    expect(result_dialog).to_be_visible(timeout=5000)
    expect(result_dialog).to_contain_text("amazon-safe@example.org")
    with page.expect_navigation(wait_until="load"):
        result_dialog.locator(".dialog-close").click()

    page.goto(f"{base_url}/aliases")
    old_alias = _alias_row(page, AMAZON)
    expect(old_alias).to_have_count(1)
    expect(old_alias.locator("[data-alias-select]")).to_have_attribute("data-active", "0")
    new_alias = _alias_row(page, "amazon-safe@example.org")
    expect(new_alias).to_have_count(1)
    expect(new_alias.locator(".alias-info strong")).to_have_text("Amazon")
    expect(new_alias.locator("[data-alias-select]")).to_have_attribute("data-sogo", "1")


def test_used_offline_alias_stays_protected_and_pool_export_excludes_it(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    used = _pool_item(page, USED_POOL)
    unused = _pool_item(page, UNUSED_POOL)
    expect(used).to_have_count(1)
    expect(unused).to_have_count(1)
    expect(page.locator(".pool-table-head")).to_be_visible()

    expect(used.locator('form[action$="/delete"]')).to_have_count(0)
    expect(unused.locator('form[action$="/delete"]')).to_have_count(1)
    expect(unused.locator("button.sender-stats-trigger")).to_have_count(0)

    used_assign_box = used.locator("details.pool-assign-action > summary").bounding_box()
    unused_assign_box = unused.locator("details.pool-assign-action > summary").bounding_box()
    used_copy_box = used.locator("[data-copy]").bounding_box()
    unused_copy_box = unused.locator("[data-copy]").bounding_box()
    assert used_assign_box and unused_assign_box and used_copy_box and unused_copy_box
    assert abs(used_assign_box["x"] - unused_assign_box["x"]) <= 1
    assert abs(used_copy_box["x"] - unused_copy_box["x"]) <= 1
    assert used_assign_box["x"] < used_copy_box["x"]

    sender_dialog = _open_sender_dialog(page, used)
    expect(sender_dialog).to_contain_text("booking@example.net")
    sender_dialog.locator(".dialog-close").click()

    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=base_url,
    )
    page.locator("[data-copy-pool]").click()
    clipboard = page.evaluate("navigator.clipboard.readText()")
    assert UNUSED_POOL in clipboard
    assert USED_POOL not in clipboard

    text_link = page.locator('a[href="/aliases/pool.txt"]')
    expect(text_link).to_have_attribute("target", "_blank")

    exported = page.evaluate(
        "async () => await (await fetch('/aliases/pool.txt')).text()"
    )
    assert UNUSED_POOL in exported
    assert USED_POOL not in exported


def test_offline_sender_review_uses_same_overlay_as_assigned_alias(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    assigned_dialog = _open_sender_dialog(page, _alias_row(page, AMAZON))
    assigned_classes = assigned_dialog.get_attribute("class")
    expect(assigned_dialog.locator(".sender-review-settings")).to_be_visible()
    assigned_dialog.locator(".dialog-close").click()

    page.goto(f"{base_url}/offline-pool")
    offline_dialog = _open_sender_dialog(page, _pool_item(page, USED_POOL))
    assert offline_dialog.get_attribute("class") == assigned_classes
    expect(offline_dialog.locator(".sender-review-settings")).to_be_visible()
    expect(offline_dialog.locator(".sender-review-form")).to_be_visible()
    expect(offline_dialog).to_contain_text("booking@example.net")
    expect(offline_dialog).to_contain_text("No longer flagged for review")


def test_ignoring_offline_sender_review_keeps_assignment_warning(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    used = _pool_item(page, USED_POOL)
    expect(used).to_have_class(re.compile(r"\bpool-item-used\b"))
    expect(used.locator(".alias-cell-status")).to_contain_text("Assign")

    dialog = _open_sender_dialog(page, used)
    checkbox = dialog.locator(".sender-review-settings input[type=checkbox]")
    expect(checkbox).not_to_be_checked()
    with page.expect_navigation(wait_until="load"):
        checkbox.check()

    used = _pool_item(page, USED_POOL)
    expect(used).to_have_count(1)
    expect(used).to_have_class(re.compile(r"\bpool-item-used\b"))
    expect(used.locator(".alias-cell-status")).to_contain_text("Assign")


def test_action_required_assigns_used_offline_alias(page: Page, base_url: str) -> None:
    _login(page, base_url)
    dialog = _open_action_required(page, base_url)

    row = dialog.locator('[data-pool-alias-id="11"]')
    expect(row).to_be_visible()
    row.locator(".used-pool-purpose input").fill("Hotel booking")
    with page.expect_navigation(wait_until="load"):
        dialog.locator(".used-pool-actions .primary").click()

    expect(page).to_have_url(re.compile(rf"{re.escape(base_url)}/overview(?:[?#].*)?$"))
    page.goto(f"{base_url}/aliases")
    assigned = _alias_row(page, USED_POOL)
    expect(assigned).to_have_count(1)
    expect(assigned.locator(".alias-info strong")).to_have_text("Hotel booking")

    page.goto(f"{base_url}/offline-pool")
    expect(_pool_item(page, USED_POOL)).to_have_count(0)


def test_default_alias_sort_puts_unexpected_sender_first(page: Page, base_url: str) -> None:
    _login(page, base_url)

    first = page.locator(".alias-list .alias-row [data-alias-select]").first
    expect(first).to_have_attribute("data-address", AMAZON)


def test_generic_alias_badge_uses_initials_instead_of_question_mark(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)

    badge = _alias_row(page, ARCHIVE).locator("[data-service-icon-for]")
    expect(badge).to_have_text("AR")
    expect(badge).not_to_have_text("?")


def test_alias_edit_panel_starts_with_logo_and_purpose_input(page: Page, base_url: str) -> None:
    _login(page, base_url)

    amazon = _alias_row(page, AMAZON)
    sogo = amazon.locator(".alias-cell-status .mini-meta")
    expect(sogo).to_have_text("SOGo")
    border_radius = sogo.evaluate("element => getComputedStyle(element).borderRadius")
    assert border_radius != "0px"

    edit = amazon.locator("details.alias-edit-action")
    edit.locator("summary").click()
    purpose_row = edit.locator(".alias-edit-purpose-row")
    expect(purpose_row).to_be_visible(timeout=5000)
    expect(purpose_row.locator("[data-icon-picker-trigger]")).to_be_visible()
    purpose = purpose_row.locator('input[name="description"]')
    expect(purpose).to_have_value("Amazon")
    expect(purpose.locator("xpath=..")).to_contain_text("Alias name")
    expect(edit.locator(".alias-edit-current-name")).to_have_count(0)
    expect(edit.locator('form[action$="/metadata"] button[type="submit"]')).to_have_class(
        re.compile(r"\bprimary\b")
    )
    expect(edit.locator(".alias-toggle-action button")).to_have_class(
        re.compile(r"\bdanger\b")
    )


def test_copy_button_turns_green_then_returns_to_copy_icon(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=base_url,
    )

    button = _alias_row(page, AMAZON).locator(".alias-copy-action")
    before = button.evaluate("element => getComputedStyle(element).backgroundColor")
    expect(button.locator("svg.ui-icon use")).to_have_attribute(
        "href", "/static/ui-icons.svg#icon-copy"
    )
    button.click()
    expect(button).to_have_text("✓")
    expect(button).to_have_class(re.compile(r"copy-success"))
    during = button.evaluate("element => getComputedStyle(element).backgroundColor")
    assert during != before

    page.wait_for_timeout(1300)
    expect(button).not_to_have_class(re.compile(r"copy-success"))
    expect(button.locator("svg.ui-icon use")).to_have_attribute(
        "href", "/static/ui-icons.svg#icon-copy"
    )


def test_overview_links_to_split_management_pages(page: Page, base_url: str) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/overview")

    expect(page.locator('.side-nav-link[href="/aliases"]')).to_be_visible()
    expect(page.locator('.side-nav-link[href="/offline-pool"]')).to_be_visible()
    expect(page.locator('.side-nav-link[href="/statistics"]')).to_be_visible()
    expect(page.locator(".recent-alias-list")).to_be_visible()


def test_expired_browser_session_redirects_to_login(page: Page, base_url: str) -> None:
    _login(page, base_url)

    page.context.clear_cookies()
    page.reload(wait_until="domcontentloaded")
    page.wait_for_url(re.compile(rf"{re.escape(base_url)}/?$"), timeout=5000)
    page.wait_for_load_state("networkidle")

    expect(page.locator('a[href="/login"]')).to_be_visible()
    expect(page.locator("body")).not_to_contain_text("Authentication required")


def test_mobile_action_required_and_alias_actions_stay_inside_viewport(
    page: Page,
    base_url: str,
) -> None:
    page.set_viewport_size({"width": 390, "height": 844})
    _login(page, base_url)

    dialog = _open_action_required(page, base_url)
    box = dialog.bounding_box()
    assert box
    assert box["x"] >= -1
    assert box["y"] >= -1
    assert box["x"] + box["width"] <= 391
    assert box["y"] + box["height"] <= 845
    dialog.locator(".dialog-close").click()

    page.goto(f"{base_url}/aliases")
    amazon_row = _alias_row(page, AMAZON)
    expect(amazon_row.locator(".alias-copy-action")).to_be_visible()
    edit = amazon_row.locator("details.alias-edit-action")
    edit.locator("summary").click()
    expect(edit.locator(".alias-toggle-action button")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth + 1")


def test_mobile_sidebar_stays_above_blurred_backdrop(page: Page, base_url: str) -> None:
    page.set_viewport_size({"width": 760, "height": 844})
    _login(page, base_url)

    page.locator("[data-mobile-nav]").click()
    sidebar = page.locator("[data-app-sidebar]")
    backdrop = page.locator("[data-drawer-backdrop]")
    expect(sidebar).to_have_class(re.compile(r"\bopen\b"))
    expect(backdrop).to_be_visible()

    sidebar_z = sidebar.evaluate("element => Number(getComputedStyle(element).zIndex)")
    backdrop_z = backdrop.evaluate("element => Number(getComputedStyle(element).zIndex)")
    assert sidebar_z > backdrop_z


def test_offline_pool_uses_primary_dropdown_for_supported_batch_sizes(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/offline-pool")

    trigger = page.locator("[data-pool-create-trigger]")
    expect(trigger).to_be_visible()
    expect(trigger).to_have_class(re.compile(r"\bprimary\b"))
    expect(trigger).to_contain_text("Offline alias")

    popover = page.locator("[data-pool-create-popover]")
    expect(popover).to_be_hidden()
    trigger.click()
    expect(popover).to_be_visible()
    counts = popover.locator('input[name="count"]').evaluate_all(
        "elements => elements.map((element) => element.value)"
    )
    assert counts == ["1", "5", "10"]
    expect(popover.locator('input[name="count"][value="20"]')).to_have_count(0)

    item = _pool_item(page, UNUSED_POOL)
    details = item.locator('details[data-pool-inline-assign="10"]')
    expect(details).to_be_visible(timeout=5000)
    details.locator("summary").click()
    expect(details).to_have_attribute("open", "")
    expect(page.locator("dialog[data-assign-dialog][open]")).to_have_count(0)

    description = details.locator('input[name="description"]')
    expect(description.locator("xpath=..")).to_contain_text("Alias name")
    expect(description).to_be_focused()


def test_global_controls_use_lucide_icons_and_semantic_quota_meter(
    page: Page,
    base_url: str,
) -> None:
    _login(page, base_url)
    page.goto(f"{base_url}/overview")

    expect(page.locator('.side-nav-link[href="/statistics"] use')).to_have_attribute(
        "href", "/static/ui-icons.svg#icon-chart-no-axes-combined"
    )
    expect(page.locator(".header-icon-button[data-open-settings] use")).to_have_attribute(
        "href", "/static/ui-icons.svg#icon-settings"
    )
    expect(page.locator(".account-chevron use")).to_have_attribute(
        "href", "/static/ui-icons.svg#icon-chevron-down"
    )

    page.locator("[data-account-button]").click()
    popover = page.locator("[data-account-popover]")
    expect(popover).to_be_visible()
    expect(popover).to_contain_text("are managed by Moolias")
    meter = popover.locator("meter.account-quota-meter")
    expect(meter).to_be_visible()
    used = float(meter.get_attribute("value") or "0")
    limit = float(meter.get_attribute("max") or "0")
    assert limit > 0
    assert 0 <= used < limit

    page.goto(f"{base_url}/statistics")
    expect(page.locator("h1")).to_have_text("Statistics")
    expect(page.locator("main")).not_to_contain_text("Statistics mode")
    review_link = page.locator('a[href="/aliases?status=unexpected"]')
    expect(review_link).to_have_text("Review now")
    destinations = page.locator(".statistics-card").filter(
        has_text="Most active destinations"
    )
    expect(destinations).to_contain_text("customer@example.net")
