from __future__ import annotations

from types import SimpleNamespace

import pytest

from moolias import newsletters as newsletter_module
from moolias.newsletter_page_state import load_newsletter_page_state
from moolias.newsletters import NewsletterCollector
from moolias.ui import _load_ui_state


class _Request:
    def __init__(self, *, settings, mailcow, stats_store=None) -> None:
        self.session = {"user_email": "user@example.test", "csrf_token": "csrf"}
        self.state = SimpleNamespace()
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                settings=settings,
                mailcow=mailcow,
                stats_store=stats_store,
            )
        )
        self.query_params = {}


@pytest.mark.asyncio
async def test_ui_state_fetches_aliases_and_domain_concurrently(tmp_path):
    calls: list[str] = []

    class Mailcow:
        async def list_aliases(self):
            calls.append("aliases-start")
            await __import__("asyncio").sleep(0)
            assert "domain-start" in calls
            return []

        async def get_domain(self, domain):
            assert domain == "example.test"
            calls.append("domain-start")
            await __import__("asyncio").sleep(0)
            assert "aliases-start" in calls
            return {
                "aliases_in_domain": 0,
                "max_num_aliases_for_domain": 100,
                "tags": [],
            }

    settings = SimpleNamespace(
        usage_stats=False,
        usage_db_path=str(tmp_path / "stats.sqlite3"),
        usage_poll_seconds=60,
        usage_stale_polls=3,
    )
    state = await _load_ui_state(_Request(settings=settings, mailcow=Mailcow()))

    assert calls[:2] == ["aliases-start", "domain-start"]
    assert state["mailcow_aliases"] == []
    assert state["mailcow_quota"] == {"used": 0, "limit": 100, "own": 0}


@pytest.mark.asyncio
async def test_ui_state_reuses_access_revalidation_mailbox(tmp_path):
    class Mailcow:
        async def list_aliases(self):
            return []

        async def get_domain(self, domain):
            return {
                "aliases_in_domain": 0,
                "max_num_aliases_for_domain": 100,
                "tags": [],
            }

        async def get_mailbox(self, email):
            raise AssertionError("mailbox must be reused from request state")

    class StatsStore:
        path = tmp_path / "stats.sqlite3"

        async def sender_mode(self, mailbox):
            return None

        async def sync_sender_modes(self, values):
            return None

    settings = SimpleNamespace(
        usage_stats=True,
        usage_tag="moolias-stats",
        usage_db_path=str(tmp_path / "stats.sqlite3"),
        usage_poll_seconds=60,
        usage_stale_polls=3,
    )
    request = _Request(settings=settings, mailcow=Mailcow(), stats_store=StatsStore())
    request.state.mailbox = {"username": "user@example.test", "tags": []}

    state = await _load_ui_state(request)

    assert state["mailbox_details"] is request.state.mailbox
    assert state["stats_state"] is not None


@pytest.mark.asyncio
async def test_newsletter_state_skips_heavy_usage_and_sender_reads(tmp_path):
    class Mailcow:
        async def list_aliases(self):
            return []

        async def get_domain(self, domain):
            assert domain == "example.test"
            return {
                "aliases_in_domain": 0,
                "max_num_aliases_for_domain": 100,
                "tags": [],
            }

        async def get_mailbox(self, email):
            raise AssertionError("mailbox must be reused from request state")

    class StatsStore:
        path = tmp_path / "stats.sqlite3"

        async def sender_mode(self, mailbox):
            return None

        async def sync_sender_modes(self, values):
            return None

        async def alias_usage(self, mailbox, aliases):
            raise AssertionError("newsletter state must not read alias usage")

        async def sender_usage(self, mailbox, aliases):
            raise AssertionError("newsletter state must not read sender usage")

    settings = SimpleNamespace(
        usage_stats=True,
        usage_tag="moolias-stats",
    )
    request = _Request(settings=settings, mailcow=Mailcow(), stats_store=StatsStore())
    request.state.mailbox = {"username": "user@example.test", "tags": []}

    state = await load_newsletter_page_state(request)

    assert state["assigned_all"] == []
    assert state["mailbox_details"] is request.state.mailbox
    assert state["stats_state"] is not None
    assert "usage_stats" not in state
    assert "sender_stats" not in state


@pytest.mark.asyncio
async def test_newsletter_page_tracks_without_waiting_for_scan(monkeypatch):
    class Store:
        async def list_for_mailbox(self, mailbox):
            assert mailbox == "user@example.test"
            return []

    class Collector:
        last_error = None
        last_success_at = None

        def __init__(self):
            self.tracked = []
            self.scan_called = False

        def track(self, mailbox):
            self.tracked.append(mailbox)

        async def scan_mailbox(self, mailbox):
            self.scan_called = True

    class Templates:
        def TemplateResponse(self, request, template_name, context):
            return {"template": template_name, "context": context}

    collector = Collector()
    settings = SimpleNamespace(
        newsletter_management=True,
        newsletter_tag="moolias-newsletter",
    )
    request = _Request(settings=settings, mailcow=SimpleNamespace())

    async def fake_newsletter_page_state(_request):
        return {
            "assigned_all": [],
            "mailcow_aliases": [],
            "mailbox_details": {"tags": ["moolias-newsletter"]},
        }

    async def fake_runtime(_request):
        return Store(), collector

    monkeypatch.setattr(
        newsletter_module,
        "load_newsletter_page_state",
        fake_newsletter_page_state,
    )
    monkeypatch.setattr(newsletter_module, "_runtime", fake_runtime)
    monkeypatch.setattr(newsletter_module, "_template_context", lambda request, **values: values)
    monkeypatch.setattr(newsletter_module, "TEMPLATES", Templates())

    response = await newsletter_module.newsletters_page(request)

    assert response["template"] == "newsletters.html"
    assert collector.tracked == ["user@example.test"]
    assert collector.scan_called is False


def test_tracking_new_mailbox_wakes_background_collector_once():
    collector = NewsletterCollector(
        SimpleNamespace(newsletter_poll_seconds=60),
        None,
        None,
    )

    assert collector._wake.is_set() is False
    collector.track("User@Example.Test")
    assert collector._wake.is_set() is True

    collector._wake.clear()
    collector.track("user@example.test")
    assert collector._wake.is_set() is False

    collector.track("other@example.test")
    assert collector._wake.is_set() is True
