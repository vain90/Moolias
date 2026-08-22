from __future__ import annotations

import asyncio
import os
import re

from fastapi.testclient import TestClient

from moolias.aliases import AliasRecord
from moolias.config import Settings
from moolias.review_settings import AliasReviewSettingsStore
from moolias.stats import SenderEvent

os.environ.setdefault("MOOLIAS_BASE_URL", "https://aliases.example.org")
os.environ.setdefault("MOOLIAS_SESSION_SECRET", "x" * 64)
os.environ.setdefault("MAILCOW_URL", "https://mail.example.org")
os.environ.setdefault("MAILCOW_API_KEY", "secret")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_ID", "client")
os.environ.setdefault("MAILCOW_OAUTH_CLIENT_SECRET", "oauth-secret")

import moolias.main as main_module  # noqa: E402

USER = "user@example.org"
OTHER_USER = "other@example.org"


class NoopUsageCollector:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def run_forever(self) -> None:
        await asyncio.Future()


class FakeMailcow:
    def __init__(self, aliases: list[AliasRecord], *, mode_tag: str) -> None:
        self.aliases = aliases
        self.mode_tag = mode_tag

    async def close(self) -> None:
        pass

    async def get_mailbox(self, email: str):
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": [self.mode_tag],
        }

    async def get_domain(self, domain: str):
        return {"domain": domain, "tags": []}

    async def list_aliases(self) -> list[AliasRecord]:
        return list(self.aliases)


def _aliases() -> list[AliasRecord]:
    aliases = [
        AliasRecord(
            id=index,
            address=f"alias-{index:02d}@example.org",
            goto=USER,
            domain="example.org",
            active=True,
            private_comment="",
            public_comment=f"Item {index:02d}",
        )
        for index in range(1, 30)
    ]
    aliases.append(
        AliasRecord(
            id=30,
            address="brand-k7@example.org",
            goto=USER,
            domain="example.org",
            active=True,
            private_comment="",
            public_comment="Brand",
        )
    )
    aliases.append(
        AliasRecord(
            id=99,
            address=USER,
            goto=USER,
            domain="example.org",
            active=True,
            private_comment="",
            public_comment="",
        )
    )
    return aliases


def _settings(tmp_path) -> Settings:
    return Settings(
        MOOLIAS_BASE_URL="https://aliases.example.org",
        MOOLIAS_SESSION_SECRET="x" * 64,
        MOOLIAS_COOKIE_SECURE=False,
        MOOLIAS_USAGE_STATS=True,
        MOOLIAS_USAGE_TAG="moolias-stats",
        MOOLIAS_USAGE_DB_PATH=str(tmp_path / "stats.sqlite3"),
        MAILCOW_URL="https://mail.example.org",
        MAILCOW_API_KEY="secret",
        MAILCOW_OAUTH_CLIENT_ID="client",
        MAILCOW_OAUTH_CLIENT_SECRET="oauth-secret",
    )


def _login(client: TestClient) -> None:
    response = client.get(
        "/oauth/callback?code=test&state=test",
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/aliases"


async def _seed_sender_state(store) -> None:
    started_at = await store.tracking_started_at()
    await store.sync_sender_modes(
        {USER: "full", OTHER_USER: "full"},
        now=started_at + 1,
    )

    events = [
        SenderEvent(
            f"sender-{index}",
            USER,
            f"alias-{index:02d}@example.org",
            "outside.example",
            f"sender{index}@outside.example",
            "full",
            started_at + 10 + index,
        )
        for index in range(1, 29)
    ]
    events.extend(
        [
            SenderEvent(
                "other-mailbox-only",
                OTHER_USER,
                "alias-29@example.org",
                "outside.example",
                "other@outside.example",
                "full",
                started_at + 100,
            ),
            SenderEvent(
                "automatic-brand",
                USER,
                "brand-k7@example.org",
                "brand.com",
                "news@brand.com",
                "full",
                started_at + 101,
            ),
        ]
    )
    await store.record_senders(events)
    await store.set_sender_expectation(
        USER,
        "alias-02@example.org",
        "sender2@outside.example",
        True,
    )
    await AliasReviewSettingsStore(store.path).set_ignore_unexpected(
        USER,
        "alias-01@example.org",
        True,
    )


def _unexpected_count(html: str) -> int:
    match = re.search(
        r'data-unexpected-filter[^>]*>\s*Unexpected\s*<span>(\d+)</span>',
        html,
        flags=re.DOTALL,
    )
    assert match is not None
    return int(match.group(1))


def _row_count(html: str) -> int:
    return html.count('<article class="alias-row')


def _client(monkeypatch, tmp_path, *, mode_tag: str):
    fake = FakeMailcow(_aliases(), mode_tag=mode_tag)

    async def fake_exchange_code(_settings, _code):
        return {"email": USER}

    monkeypatch.setattr(main_module, "MailcowClient", lambda _settings: fake)
    monkeypatch.setattr(main_module, "UsageCollector", NoopUsageCollector)
    monkeypatch.setattr(main_module, "exchange_code", fake_exchange_code)
    monkeypatch.setattr(main_module, "validate_oauth_state", lambda _request, _state: None)

    app = main_module.create_app(_settings(tmp_path))
    return TestClient(app), app


def test_unexpected_filter_count_search_and_pagination_are_server_side(
    monkeypatch,
    tmp_path,
):
    client, app = _client(monkeypatch, tmp_path, mode_tag="moolias-stats-full")
    with client:
        _login(client)
        asyncio.run(_seed_sender_state(app.state.stats_store))

        response = client.get(
            "/aliases?status=unexpected&per_page=10&page=2&sort=last_used&direction=asc"
        )
        assert response.status_code == 200
        html = response.text
        assert _unexpected_count(html) == 26
        assert _row_count(html) == 10
        assert 'data-address="alias-13@example.org"' in html
        assert 'data-address="alias-22@example.org"' in html
        assert 'data-address="alias-12@example.org"' not in html
        assert 'data-address="alias-23@example.org"' not in html
        assert 'href="/aliases?status=unexpected' in html

        searched = client.get(
            "/aliases?status=unexpected&q=Item%202&per_page=10&page=1"
        )
        assert searched.status_code == 200
        searched_html = searched.text
        assert _unexpected_count(searched_html) == 26
        assert _row_count(searched_html) == 9
        assert 'data-address="alias-20@example.org"' in searched_html
        assert 'data-address="alias-28@example.org"' in searched_html
        assert 'data-address="alias-29@example.org"' not in searched_html

        all_unexpected = client.get("/aliases?status=unexpected&per_page=100")
        all_html = all_unexpected.text
        assert 'data-address="alias-01@example.org"' not in all_html
        assert 'data-address="alias-02@example.org"' not in all_html
        assert 'data-address="brand-k7@example.org"' not in all_html
        assert 'data-address="alias-29@example.org"' not in all_html


def test_unexpected_filter_is_empty_without_sender_detail(monkeypatch, tmp_path):
    client, app = _client(monkeypatch, tmp_path, mode_tag="moolias-stats")
    with client:
        _login(client)
        asyncio.run(_seed_sender_state(app.state.stats_store))

        response = client.get("/aliases?status=unexpected&per_page=10")
        assert response.status_code == 200
        assert _unexpected_count(response.text) == 0
        assert _row_count(response.text) == 0
