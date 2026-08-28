from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW_JS = (ROOT / "moolias" / "static" / "review.js").read_text(encoding="utf-8")
REVIEW_CSS = (ROOT / "moolias" / "static" / "review.css").read_text(encoding="utf-8")
REVIEW_BEHAVIOR_JS = (ROOT / "moolias" / "static" / "review-behavior.js").read_text(
    encoding="utf-8"
)
ACTION_TEMPLATE = (ROOT / "moolias" / "templates" / "_action_required.html").read_text(
    encoding="utf-8"
)
OVERVIEW_TEMPLATE = (ROOT / "moolias" / "templates" / "overview.html").read_text(
    encoding="utf-8"
)
DASHBOARD_TEMPLATE = (ROOT / "moolias" / "templates" / "dashboard.html").read_text(
    encoding="utf-8"
)


def test_action_required_ui_is_owned_by_server_rendered_html():
    assert "data-action-required-dialog" in ACTION_TEMPLATE
    assert "data-action-sender-row" in ACTION_TEMPLATE
    assert "data-action-required-pool-form" in ACTION_TEMPLATE
    assert "data-review-replace-alias" in ACTION_TEMPLATE
    assert '{% include "_action_required.html" %}' in OVERVIEW_TEMPLATE
    assert '{% include "_action_required.html" %}' in DASHBOARD_TEMPLATE
    assert 'href="/overview?action=required"' in OVERVIEW_TEMPLATE
    assert 'href="/aliases?action=required"' in DASHBOARD_TEMPLATE


def test_action_required_javascript_does_not_reconstruct_server_ui():
    forbidden = (
        "document.createElement",
        ".innerHTML",
        ".outerHTML",
        "insertAdjacentHTML",
        "cloneNode",
        "document.importNode",
        "replaceChildren",
    )
    for source in (REVIEW_JS, REVIEW_BEHAVIOR_JS):
        for token in forbidden:
            assert token not in source


def test_expected_sender_action_refreshes_from_server_rendered_state():
    assert 'decision === "expected"' in REVIEW_JS
    assert "new DOMParser()" in REVIEW_JS
    assert "syncSenderRow" in REVIEW_JS
    assert "freshSenderRow" in REVIEW_JS
    assert "freshRow" in REVIEW_JS
    assert "classList.add(\"expected\")" not in REVIEW_JS
    assert "classList.remove(\"unexpected\")" not in REVIEW_JS


def test_expected_sender_feedback_and_alias_table_refresh_are_behavior_only():
    assert "actionDialogChanged = true" in REVIEW_JS
    assert 'window.location.pathname === "/aliases"' in REVIEW_JS
    assert "window.location.reload();" in REVIEW_JS
    assert "hideAfterResolvedFeedback" in REVIEW_JS
    assert "transition: border-color .45s ease" in REVIEW_CSS
    assert "@media (prefers-reduced-motion: reduce)" in REVIEW_CSS
