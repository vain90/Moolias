from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, Route, expect

ROOT = Path(__file__).resolve().parents[1]
NEWSLETTERS_JS = (ROOT / "moolias" / "static" / "newsletters.js").read_text(
    encoding="utf-8"
)


def _newsletter_page(query: str = "") -> str:
    if query.casefold() == "github":
        rows = """
        <tr class="newsletter-row"><td>GitHub Digest</td><td>
          <button type="button" data-newsletter-details-toggle="newsletter-details-2"
                  aria-expanded="false">Details</button>
        </td></tr>
        <tr id="newsletter-details-2" class="newsletter-details-row" hidden>
          <td>GitHub details</td>
        </tr>
        """
    else:
        rows = """
        <tr class="newsletter-row"><td>Amazon News</td><td></td></tr>
        <tr class="newsletter-row"><td>GitHub Digest</td><td></td></tr>
        """

    return f"""<!doctype html>
<html lang="en">
<body>
<section data-newsletter-page>
  <section class="card newsletter-management-card">
    <div class="newsletter-toolbar">
      <div class="search-box newsletter-search-box">
        <input class="search" type="search" value="{query}"
               data-newsletter-search autocomplete="off">
        <button type="button" data-newsletter-search-clear
                {'hidden' if not query else ''}>Clear</button>
      </div>
      <nav class="newsletter-status-filters">
        <a href="/newsletters?status=all&q={query}&per_page=50">All</a>
        <a href="/newsletters?status=resumed&q={query}&per_page=50">Resumed</a>
      </nav>
    </div>
    <div class="newsletter-table-wrap">
      <table><tbody>{rows}</tbody></table>
    </div>
    <div class="pagination-bar newsletter-pagination-bar">
      <span class="pagination-summary">results</span>
      <form method="get" action="/newsletters">
        <input type="hidden" name="status" value="resumed">
        <input type="hidden" name="q" value="{query}">
        <select name="per_page"><option value="50" selected>50</option></select>
      </form>
    </div>
  </section>
</section>
</body>
</html>"""


def test_newsletter_search_updates_results_without_page_navigation(page: Page) -> None:
    requested_urls: list[str] = []

    def serve(route: Route) -> None:
        requested_urls.append(route.request.url)
        query = parse_qs(urlparse(route.request.url).query).get("q", [""])[0]
        route.fulfill(
            status=200,
            content_type="text/html",
            body=_newsletter_page(query),
        )

    page.route("http://moolias.test/**", serve)
    navigations: list[str] = []
    page.on(
        "framenavigated",
        lambda frame: navigations.append(frame.url) if frame == page.main_frame else None,
    )

    page.goto("http://moolias.test/newsletters?status=resumed&per_page=50")
    initial_navigation_count = len(navigations)
    page.add_script_tag(content=NEWSLETTERS_JS)

    search = page.locator("[data-newsletter-search]")
    search.fill("GitHub")

    expect(page.locator(".newsletter-row")).to_have_count(1, timeout=5000)
    expect(page.locator(".newsletter-row")).to_contain_text("GitHub Digest")
    expect(page).to_have_url(
        "http://moolias.test/newsletters?status=resumed&per_page=50&page=1&q=GitHub"
    )
    assert len(navigations) == initial_navigation_count

    live_requests = [url for url in requested_urls[1:] if "q=GitHub" in url]
    assert live_requests
    live_query = parse_qs(urlparse(live_requests[-1]).query)
    assert live_query["status"] == ["resumed"]
    assert live_query["per_page"] == ["50"]
    assert live_query["page"] == ["1"]

    details = page.locator("#newsletter-details-2")
    expect(details).to_be_hidden()
    page.locator("[data-newsletter-details-toggle]").click()
    expect(details).to_be_visible()

    page.locator("[data-newsletter-search-clear]").click()
    expect(page.locator(".newsletter-row")).to_have_count(2, timeout=5000)
    expect(search).to_be_focused()
    expect(page).to_have_url(
        "http://moolias.test/newsletters?status=resumed&per_page=50&page=1"
    )
    assert len(navigations) == initial_navigation_count


def test_newsletter_live_search_uses_alias_style_request_control() -> None:
    assert "new AbortController()" in NEWSLETTERS_JS
    assert "searchController?.abort()" in NEWSLETTERS_JS
    assert "window.history.replaceState" in NEWSLETTERS_JS
    assert "window.location.assign" not in NEWSLETTERS_JS
    assert "window.setTimeout(refreshNewsletterResults, 250)" in NEWSLETTERS_JS
    assert 'headers: { "X-Moolias-Partial": "newsletter-results" }' in NEWSLETTERS_JS
