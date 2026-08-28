from __future__ import annotations

from pathlib import Path


def _rule(css: str, selector: str) -> str:
    return css.split(f"{selector} {{", 1)[1].split("}", 1)[0]


def test_replacement_link_icon_has_subtle_border():
    root = Path(__file__).resolve().parents[1]
    css = (root / "moolias/static/ui-polish.css").read_text()

    rule = _rule(css, ".alias-migration-link-icon")

    assert "border: 1px solid var(--line-strong);" in rule


def test_alias_service_logos_grow_without_resizing_badges():
    root = Path(__file__).resolve().parents[1]
    shell_css = (root / "moolias/static/shell.css").read_text()
    polish_css = (root / "moolias/static/ui-polish.css").read_text()

    badge_rule = _rule(shell_css, ".service-badge")
    logo_rule = _rule(polish_css, ".service-badge .service-logo")

    assert "width: 31px;" in badge_rule
    assert "height: 31px;" in badge_rule
    assert "width: 21px;" in logo_rule
    assert "height: 21px;" in logo_rule
