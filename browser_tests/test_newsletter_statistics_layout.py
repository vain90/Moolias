from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates
from playwright.sync_api import Page, expect

import moolias

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = Path(moolias.__file__).resolve().parent / "templates"
TEMPLATES = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _render_newsletter_statistics() -> str:
    return TEMPLATES.get_template("_newsletter_statistics.html").render(
        language="en",
        version="test",
        newsletter_statistics={
            "all": 14,
            "unsubscribable": 5,
            "no_link": 4,
            "unsubscribed": 3,
            "resumed": 2,
        },
    )


def _load_summary(page: Page, *, width: int, height: int) -> None:
    page.set_viewport_size({"width": width, "height": height})
    page.set_content(f"<main>{_render_newsletter_statistics()}</main>")
    page.add_style_tag(
        content="html, body { margin: 0; } main { padding: 20px; } "
        ".card { box-sizing: border-box; padding: 16px; border: 1px solid #ddd; }"
    )
    page.add_style_tag(
        path=str(REPOSITORY_ROOT / "moolias/static/newsletter-statistics.css")
    )


def test_newsletter_statistics_cards_are_two_columns_on_desktop(page: Page) -> None:
    _load_summary(page, width=1200, height=900)

    layout = page.locator("[data-newsletter-statistics]")
    cards = layout.locator(".newsletter-summary-card")
    expect(cards).to_have_count(2)
    expect(page.locator("[data-newsletter-success-card]")).to_have_attribute(
        "data-newsletter-success-card", ""
    )
    expect(page.locator("[data-newsletter-success-rate]")).to_have_attribute(
        "data-newsletter-success-rate", "60"
    )
    expect(page.locator("[data-newsletter-success-card]")).to_contain_text("60%")

    first = cards.nth(0).bounding_box()
    second = cards.nth(1).bounding_box()
    assert first is not None
    assert second is not None
    assert abs(first["y"] - second["y"]) <= 1
    assert second["x"] > first["x"]


def test_newsletter_statistics_cards_stack_on_mobile(page: Page) -> None:
    _load_summary(page, width=390, height=844)

    cards = page.locator("[data-newsletter-statistics] .newsletter-summary-card")
    expect(cards).to_have_count(2)

    first = cards.nth(0).bounding_box()
    second = cards.nth(1).bounding_box()
    assert first is not None
    assert second is not None
    assert second["y"] > first["y"] + first["height"] - 1
    assert abs(first["x"] - second["x"]) <= 1
