from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_JS = (ROOT / "moolias" / "static" / "alias-workflow.js").read_text(encoding="utf-8")
WORKFLOW_CSS = (ROOT / "moolias" / "static" / "alias-workflow.css").read_text(encoding="utf-8")
WORKFLOW_TEMPLATE = (ROOT / "moolias" / "templates" / "_alias_workflow.html").read_text(
    encoding="utf-8"
)
DASHBOARD_TEMPLATE = (ROOT / "moolias" / "templates" / "dashboard.html").read_text(
    encoding="utf-8"
)


def test_alias_workflow_ui_is_owned_by_server_rendered_html():
    assert "data-alias-workflow-dialog" in WORKFLOW_TEMPLATE
    assert "data-alias-replacement-dialog" in WORKFLOW_TEMPLATE
    assert "data-alias-replacement-form" in WORKFLOW_TEMPLATE
    assert 'method="post"' in WORKFLOW_TEMPLATE
    assert "{% include \"_alias_workflow.html\" %}" in DASHBOARD_TEMPLATE
    assert 'href="/static/alias-workflow.css' in DASHBOARD_TEMPLATE


def test_alias_workflow_javascript_does_not_reconstruct_server_ui():
    forbidden = (
        "document.createElement",
        ".innerHTML",
        ".outerHTML",
        "insertAdjacentHTML",
        "cloneNode",
        "document.head.append",
    )
    for token in forbidden:
        assert token not in WORKFLOW_JS


def test_alias_workflow_links_use_normal_server_navigation():
    assert "data-open-alias-workflow" in DASHBOARD_TEMPLATE
    assert "const workflowTrigger" not in WORKFLOW_JS
    assert "workflowPageUrl" not in WORKFLOW_JS
    assert "openRenderedDialog(\n        workflowTrigger" not in WORKFLOW_JS
    assert "window.location.reload();" in WORKFLOW_JS
    assert "data-open-replacement-deactivation" in DASHBOARD_TEMPLATE


def test_alias_workflow_ui_does_not_expose_mail_system_internals():
    rendered_source = WORKFLOW_TEMPLATE.casefold()
    for term in ("greylist", "rspamd", "mailcow"):
        assert term not in rendered_source


def test_alias_workflow_old_delivery_state_uses_server_state_name():
    assert ".alias-workflow-status.old_received" in WORKFLOW_CSS
    assert ".alias-workflow-status.old-received" not in WORKFLOW_CSS
