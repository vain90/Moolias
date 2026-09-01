from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

import moolias

TEMPLATE_DIR = Path(moolias.__file__).resolve().parent / "templates"
TEMPLATES = Jinja2Templates(directory=str(TEMPLATE_DIR))


def _render_summary(*, language: str = "en", unsubscribed: int = 3, resumed: int = 2) -> str:
    return TEMPLATES.get_template("_newsletter_statistics.html").render(
        language=language,
        version="test",
        newsletter_statistics={
            "all": 14,
            "unsubscribable": 5,
            "no_link": 4,
            "unsubscribed": unsubscribed,
            "resumed": resumed,
        },
    )


def test_newsletter_statistics_use_two_large_summary_cards_and_existing_filters():
    html = _render_summary(language="de")

    assert html.count("data-newsletter-overview-card") == 1
    assert html.count("data-newsletter-success-card") == 1
    assert "newsletter-statistics-metrics" not in html
    assert "Newsletter-Übersicht" in html
    assert "Abmelde-Erfolg" in html
    assert 'href="/newsletters?status=all"' in html
    assert 'href="/newsletters?status=unsubscribable"' in html
    assert 'href="/newsletters?status=no_link"' in html
    assert 'href="/newsletters?status=unsubscribed"' in html
    assert 'href="/newsletters?status=resumed"' in html
    assert 'href="/newsletters"' in html


def test_newsletter_success_rate_uses_only_unsubscribe_outcomes():
    html = _render_summary(unsubscribed=3, resumed=2)

    assert 'data-newsletter-success-rate="60"' in html
    assert ">60%<" in html
    assert "5 unsubscribe outcomes" in html


def test_newsletter_success_rate_is_neutral_before_first_outcome():
    german = _render_summary(language="de", unsubscribed=0, resumed=0)
    english = _render_summary(language="en", unsubscribed=0, resumed=0)

    for html in (german, english):
        assert 'data-newsletter-success-rate=""' in html
        assert ">0%<" not in html
        assert ">–<" in html

    assert "Noch keine Abmeldung bewertet" in german
    assert "No unsubscribe outcome yet" in english


def test_newsletter_summary_is_placed_after_primary_cards_and_before_detail_sections():
    source = (TEMPLATE_DIR / "statistics.html").read_text(encoding="utf-8")
    include = '{% include "_newsletter_statistics.html" %}'

    assert "newsletter-statistics-metrics" not in source
    assert source.count(include) == 2

    usage_card = source.index("usage-profile-card")
    first_newsletter_summary = source.index(include)
    detail_toolbar = source.index("statistics-detail-toolbar")

    assert usage_card < first_newsletter_summary < detail_toolbar
