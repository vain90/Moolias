from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.templating import Jinja2Templates

import moolias
from moolias import newsletters as newsletter_module
from moolias import ui as ui_module
from moolias.i18n import translations
from moolias.newsletter_store import Newsletter, NewsletterLink
from moolias.pool_ui import statistics_page

TEMPLATES = Jinja2Templates(directory=str(Path(moolias.__file__).resolve().parent / "templates"))


class _Templates:
    def TemplateResponse(self, request, template_name, context):
        return {"template": template_name, "context": context}


class _Mailcow:
    def __init__(self, mailbox_tags=()) -> None:
        self.mailbox_tags = list(mailbox_tags)
        self.mailbox_calls = 0

    async def get_mailbox(self, email: str):
        self.mailbox_calls += 1
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": self.mailbox_tags,
        }


class _Store:
    def __init__(self, newsletters=()) -> None:
        self.newsletters = list(newsletters)
        self.list_calls: list[str] = []

    async def list_for_mailbox(self, mailbox: str):
        self.list_calls.append(mailbox)
        return list(self.newsletters)


def _newsletter(
    newsletter_id: int,
    *,
    last_seen_at: int,
    unsubscribed_at: int | None = None,
    has_link: bool = False,
) -> Newsletter:
    links: tuple[NewsletterLink, ...] = ()
    if has_link:
        links = (
            NewsletterLink(
                id=newsletter_id,
                newsletter_id=newsletter_id,
                url=f"https://example.org/unsubscribe/{newsletter_id}",
                one_click=True,
                mailto=None,
                source_message_id=f"message-{newsletter_id}@example.org",
                discovered_at=last_seen_at,
                last_seen_at=last_seen_at,
            ),
        )
    return Newsletter(
        id=newsletter_id,
        mailbox="user@example.org",
        recipient_alias="alias@example.org",
        identity_key=f"sender:newsletter-{newsletter_id}@example.org",
        sender_name=f"Newsletter {newsletter_id}",
        sender_address=f"newsletter-{newsletter_id}@example.org",
        list_id=None,
        first_seen_at=last_seen_at - 10,
        last_seen_at=last_seen_at,
        message_count=1,
        latest_message_id=f"message-{newsletter_id}@example.org",
        unsubscribed_at=unsubscribed_at,
        links=links,
    )


async def _render_route(
    monkeypatch,
    *,
    server_enabled: bool,
    mailbox_tags=(),
    domain_tags=(),
    newsletters=(),
    mailbox_loaded: bool = True,
):
    mailcow = _Mailcow(mailbox_tags)
    store = _Store(newsletters)
    settings = SimpleNamespace(
        newsletter_management=server_enabled,
        newsletter_tag="moolias-newsletter",
    )
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                mailcow=mailcow,
            )
        )
    )
    state = {
        "user": "user@example.org",
        "usage_stats_visible": False,
        "stats_state": None,
        "mailbox_details": (
            {"username": "user@example.org", "tags": list(mailbox_tags)} if mailbox_loaded else None
        ),
        "domain_details": {"domain": "example.org", "tags": list(domain_tags)},
    }

    async def load_ui_state(_request):
        return dict(state)

    async def newsletter_store_for(_request):
        return store

    monkeypatch.setattr(ui_module, "_load_ui_state", load_ui_state)
    monkeypatch.setattr(ui_module, "_template_context", lambda request, **values: values)
    monkeypatch.setattr(ui_module, "TEMPLATES", _Templates())
    monkeypatch.setattr(newsletter_module, "newsletter_store_for", newsletter_store_for)

    response = await statistics_page(request)
    return response["context"], mailcow, store


async def test_server_disabled_hides_newsletter_statistics_without_policy_or_store_work(
    monkeypatch,
):
    context, mailcow, store = await _render_route(
        monkeypatch,
        server_enabled=False,
        mailbox_tags=["moolias-newsletter"],
        domain_tags=["moolias-newsletter"],
    )

    assert context["newsletter_statistics_visible"] is False
    assert mailcow.mailbox_calls == 0
    assert store.list_calls == []


async def test_mailbox_policy_disabled_hides_newsletter_statistics(monkeypatch):
    context, mailcow, store = await _render_route(
        monkeypatch,
        server_enabled=True,
        mailbox_tags=["moolias-newsletter-off"],
        domain_tags=["moolias-newsletter"],
    )

    assert context["newsletter_statistics_visible"] is False
    assert mailcow.mailbox_calls == 0
    assert store.list_calls == []


async def test_enabled_newsletter_statistics_reuse_loaded_policy_and_persisted_statuses(
    monkeypatch,
):
    newsletters = [
        _newsletter(1, last_seen_at=100, has_link=True),
        _newsletter(2, last_seen_at=200),
        _newsletter(3, last_seen_at=300, unsubscribed_at=400, has_link=True),
        _newsletter(4, last_seen_at=500, unsubscribed_at=400, has_link=True),
    ]

    async def request_bound_runtime_must_not_start(_request):
        raise AssertionError("Statistics must not start or scan the newsletter collector")

    monkeypatch.setattr(newsletter_module, "_runtime", request_bound_runtime_must_not_start)
    context, mailcow, store = await _render_route(
        monkeypatch,
        server_enabled=True,
        domain_tags=["moolias-newsletter"],
        newsletters=newsletters,
    )

    assert context["newsletter_statistics_visible"] is True
    assert context["newsletter_statistics"] == {
        "all": 4,
        "unsubscribable": 1,
        "no_link": 1,
        "unsubscribed": 1,
        "resumed": 1,
    }
    assert mailcow.mailbox_calls == 0
    assert store.list_calls == ["user@example.org"]


async def test_enabled_empty_newsletter_state_legitimately_shows_zero_counts(monkeypatch):
    context, _mailcow, store = await _render_route(
        monkeypatch,
        server_enabled=True,
        mailbox_tags=["moolias-newsletter"],
    )

    assert context["newsletter_statistics_visible"] is True
    assert context["newsletter_statistics"] == {
        "all": 0,
        "unsubscribable": 0,
        "no_link": 0,
        "unsubscribed": 0,
        "resumed": 0,
    }
    assert store.list_calls == ["user@example.org"]


async def test_enabled_newsletter_statistics_load_missing_mailbox_policy_once(monkeypatch):
    context, mailcow, store = await _render_route(
        monkeypatch,
        server_enabled=True,
        mailbox_tags=["moolias-newsletter"],
        mailbox_loaded=False,
    )

    assert context["newsletter_statistics_visible"] is True
    assert mailcow.mailbox_calls == 1
    assert store.list_calls == ["user@example.org"]


async def test_statistics_store_initialisation_does_not_start_newsletter_collector(tmp_path):
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                settings=SimpleNamespace(
                    newsletter_db_path=str(tmp_path / "newsletters.sqlite3")
                )
            )
        )
    )

    store = await newsletter_module.newsletter_store_for(request)

    assert request.app.state.newsletter_store is store
    assert not hasattr(request.app.state, "newsletter_collector")
    assert not hasattr(request.app.state, "newsletter_collector_task")


def _render_template(*, visible: bool, language: str) -> str:
    return TEMPLATES.get_template("statistics.html").render(
        language=language,
        t=translations(language),
        return_to="/statistics",
        version="1.3.4",
        user="user@example.org",
        csrf_token="csrf",
        mailcow_quota={"used": 0, "limit": 0, "own": 0},
        sender_protection_setting={"enabled": False},
        stats_available=False,
        stats_error=False,
        stats_state=None,
        stats_confirmation_mode=None,
        usage_stats_visible=False,
        newsletter_statistics_visible=visible,
        newsletter_statistics={
            "all": 14,
            "unsubscribable": 5,
            "no_link": 4,
            "unsubscribed": 3,
            "resumed": 2,
        },
    )


def test_newsletter_statistics_markup_is_absent_when_not_applicable():
    html = _render_template(visible=False, language="de")

    assert "data-newsletter-statistics" not in html
    assert 'href="/newsletters?status=all"' not in html


def test_newsletter_statistics_render_server_side_in_german_and_english():
    german = _render_template(visible=True, language="de")
    english = _render_template(visible=True, language="en")

    for html in (german, english):
        assert "data-newsletter-statistics" in html
        assert 'href="/newsletters?status=all"' in html
        assert 'href="/newsletters?status=unsubscribable"' in html
        assert 'href="/newsletters?status=no_link"' in html
        assert 'href="/newsletters?status=unsubscribed"' in html
        assert 'href="/newsletters?status=resumed"' in html
        for count in (14, 5, 4, 3, 2):
            assert f"<strong>{count}</strong>" in html

    assert "Newsletter-Verwaltung" in german
    assert "Abmeldbar" in german
    assert "Kein Link" in german
    assert "Abgemeldet" in german
    assert "Trotz Abmeldung" in german
    assert "Newsletter Management" in english
    assert "Unsubscribable" in english
    assert "No link" in english
    assert "Unsubscribed" in english
    assert "After unsubscribe" in english
