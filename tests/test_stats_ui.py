from pathlib import Path

from fastapi.templating import Jinja2Templates

import moolias
from moolias.aliases import RESERVED_COMMENT, AliasRecord
from moolias.config import Settings
from moolias.i18n import translations
from moolias.stats_mode import StatsMode, StatsModeSource, StatsModeState
from moolias.usage import mailbox_stats_state, mailbox_usage_enabled

TEMPLATES = Jinja2Templates(directory=str(Path(moolias.__file__).resolve().parent / "templates"))


def settings(*, enabled: bool = True) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_USAGE_STATS=enabled,
        MOOLIAS_USAGE_TAG="moolias-stats",
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


class FakeMailcow:
    def __init__(self, *, mailbox_tags=(), domain_tags=()) -> None:
        self.mailbox_tags = list(mailbox_tags)
        self.domain_tags = list(domain_tags)
        self.mailbox_calls = 0
        self.domain_calls = 0

    async def get_mailbox(self, email: str):
        self.mailbox_calls += 1
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[1],
            "tags": self.mailbox_tags,
        }

    async def get_domain(self, domain: str):
        self.domain_calls += 1
        return {"domain": domain, "tags": self.domain_tags}


async def test_mailbox_mode_is_visible_as_effective_state():
    mailcow = FakeMailcow(
        mailbox_tags=["moolias-stats-domain"],
        domain_tags=["moolias-stats-full"],
    )

    state = await mailbox_stats_state(settings(), mailcow, "user@example.org")

    assert state.effective is StatsMode.DOMAIN
    assert state.source is StatsModeSource.MAILBOX
    assert await mailbox_usage_enabled(settings(), mailcow, "user@example.org")


async def test_stats_disabled_skips_mailcow_lookup():
    mailcow = FakeMailcow(mailbox_tags=["moolias-stats-full"])

    state = await mailbox_stats_state(settings(enabled=False), mailcow, "user@example.org")

    assert state.effective is StatsMode.OFF
    assert mailcow.mailbox_calls == 0
    assert mailcow.domain_calls == 0


def _stats_state(mode: StatsMode) -> StatsModeState:
    return StatsModeState(
        effective=mode,
        source=StatsModeSource.MAILBOX,
        mailbox_override=mode,
        domain_default=StatsMode.BASIC,
    )


def _alias() -> AliasRecord:
    return AliasRecord(
        id=1,
        address="amazon-k7@example.org",
        goto="user@example.org",
        domain="example.org",
        active=True,
        private_comment="",
        public_comment="Amazon",
        sogo_visible=True,
    )


def _reserved_alias() -> AliasRecord:
    return AliasRecord(
        id=2,
        address="feder-hafen-27@example.org",
        goto="user@example.org",
        domain="example.org",
        active=True,
        private_comment=RESERVED_COMMENT,
        public_comment="",
        sogo_visible=False,
    )


def _usage_stats(*, include_reserved: bool = False) -> dict:
    values = {
        "amazon-k7@example.org": {
            "received_count": 7,
            "sent_count": 3,
            "last_used_at": 1787167766,
        }
    }
    if include_reserved:
        values["feder-hafen-27@example.org"] = {
            "received_count": 2,
            "sent_count": 0,
            "last_used_at": 1787167800,
        }
    return values


def _sender_stats(*, include_reserved: bool = False) -> dict:
    values = {
        "amazon-k7@example.org": [
            {
                "sender_key": "news@amazon.de",
                "label": "news@amazon.de",
                "domain": "amazon.de",
                "received_count": 6,
                "last_received_at": 1787167766,
                "expected": True,
                "review_source": "automatic",
                "manual_expected": None,
                "match_token": "amazon",
            },
            {
                "sender_key": "odd@unexpected.example",
                "label": "odd@unexpected.example",
                "domain": "unexpected.example",
                "received_count": 1,
                "last_received_at": 1787167700,
                "expected": False,
                "review_source": "unreviewed",
                "manual_expected": None,
                "match_token": None,
            },
        ]
    }
    if include_reserved:
        values["feder-hafen-27@example.org"] = [
            {
                "sender_key": "sender@example.net",
                "label": "sender@example.net",
                "domain": "example.net",
                "received_count": 2,
                "last_received_at": 1787167800,
                "expected": False,
                "review_source": "unreviewed",
                "manual_expected": None,
                "match_token": None,
            }
        ]
    return values


def _base_context(mode: StatsMode) -> dict:
    return {
        "language": "de",
        "t": translations("de"),
        "return_to": "/aliases",
        "version": "0.2.0",
        "user": "user@example.org",
        "domain": "example.org",
        "catch_all": None,
        "csrf_token": "csrf",
        "stats_available": True,
        "stats_error": False,
        "stats_state": _stats_state(mode),
        "stats_mode_selection": mode.value,
        "stats_confirmation_mode": mode.value,
        "usage_stats_visible": mode is not StatsMode.OFF,
        "sender_protection_setting": {"enabled": False},
        "mailbox_quota": {},
    }


def render_dashboard(*, mode: StatsMode = StatsMode.FULL) -> str:
    alias = _alias()
    context = _base_context(mode)
    context.update(
        {
            "assigned": [alias],
            "assigned_total": 1,
            "filtered_total": 1,
            "reserved": [],
            "search_query": "",
            "status_filter": "all",
            "status_counts": {"all": 1, "active": 1, "disabled": 0, "unexpected": 1},
            "page": 1,
            "per_page": 25,
            "page_sizes": (10, 25, 50, 100),
            "total_pages": 1,
            "pagination_items": [1],
            "range_start": 1,
            "range_end": 1,
            "sort_mode": "last_used",
            "sort_direction": "desc",
            "usage_stats": _usage_stats(),
            "sender_stats": _sender_stats(),
            "unexpected_aliases": {alias.address.lower()},
            "service_icons": {},
            "icon_overrides": {},
            "icon_catalog": [],
        }
    )
    return TEMPLATES.get_template("dashboard.html").render(**context)


def render_offline_pool(*, mode: StatsMode = StatsMode.FULL) -> str:
    reserved_alias = _reserved_alias()
    context = _base_context(mode)
    context.update(
        {
            "return_to": "/offline-pool",
            "reserved": [reserved_alias],
            "used_reserved": [reserved_alias],
            "usage_stats": _usage_stats(include_reserved=True),
            "sender_stats": _sender_stats(include_reserved=True),
        }
    )
    return TEMPLATES.get_template("offline_pool.html").render(**context)


def test_dashboard_renders_usage_counts_and_sender_review():
    html = render_dashboard()

    assert "amazon-k7@example.org" in html
    assert "7 ↓ · 3 ↑" in html
    assert 'data-local-timestamp="1787167766"' in html
    assert "sender-stats-row expected" in html
    assert "sender-stats-row unexpected" in html
    assert "news@amazon.de" in html
    assert "odd@unexpected.example" in html
    assert "amazon" in html


def test_basic_mode_hides_sender_details_but_keeps_usage_counts():
    html = render_dashboard(mode=StatsMode.BASIC)

    assert "7 ↓ · 3 ↑" in html
    assert 'class="sender-stats"' not in html
    assert "news@amazon.de" not in html


def test_off_mode_hides_usage_and_sender_details():
    html = render_dashboard(mode=StatsMode.OFF)

    assert "amazon-k7@example.org" in html
    assert "7 ↓ · 3 ↑" not in html
    assert 'class="sender-stats"' not in html
    assert "news@amazon.de" not in html


def test_used_reserved_alias_is_highlighted_and_shows_sender_in_full_mode():
    html = render_offline_pool()

    assert "pool-item pool-item-used" in html
    assert "2 empfangen" in html
    assert 'data-local-timestamp="1787167800"' in html
    assert "sender@example.net" in html
    assert '/offline-pool/2/delete' not in html


def test_used_reserved_alias_in_basic_mode_shows_count_without_sender_identity():
    html = render_offline_pool(mode=StatsMode.BASIC)

    assert "pool-item pool-item-used" in html
    assert "2 empfangen" in html
    assert "sender@example.net" not in html
