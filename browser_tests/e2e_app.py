from __future__ import annotations

import asyncio
import os
import sqlite3
from dataclasses import replace
from pathlib import Path

from fastapi import Response

import moolias.main as main_module
from moolias.aliases import RESERVED_COMMENT, USED_RESERVED_COMMENT, AliasRecord
from moolias.config import Settings
from moolias.stats import SenderEvent, StatsStore, UsageEvent

USER = "user@example.org"
DOMAIN = "example.org"
DB_PATH = Path(os.environ.get("MOOLIAS_E2E_DB", "/tmp/moolias-browser-e2e.sqlite3"))
BASE_URL = os.environ.get("MOOLIAS_E2E_BASE_URL", "http://127.0.0.1:8765")


class FakeMailcow:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.mailbox_tags = ["moolias-stats-full"]
        self.domain_tags: list[str] = []
        self.aliases = {
            1: AliasRecord(
                id=1,
                address="amazon-k7@example.org",
                goto=USER,
                domain=DOMAIN,
                active=True,
                private_comment="",
                public_comment="Amazon",
                sogo_visible=True,
                sender_allowed=True,
            ),
            2: AliasRecord(
                id=2,
                address="github-m4@example.org",
                goto=USER,
                domain=DOMAIN,
                active=True,
                private_comment="",
                public_comment="GitHub",
                sogo_visible=False,
                sender_allowed=True,
            ),
            3: AliasRecord(
                id=3,
                address="archive-r8@example.org",
                goto=USER,
                domain=DOMAIN,
                active=False,
                private_comment="",
                public_comment="Archive",
                sogo_visible=False,
                sender_allowed=True,
            ),
            10: AliasRecord(
                id=10,
                address="feder-hafen-27@example.org",
                goto=USER,
                domain=DOMAIN,
                active=True,
                private_comment=RESERVED_COMMENT,
                public_comment="",
                sogo_visible=False,
                sender_allowed=True,
            ),
            11: AliasRecord(
                id=11,
                address="mond-segel-42@example.org",
                goto=USER,
                domain=DOMAIN,
                active=True,
                private_comment=USED_RESERVED_COMMENT,
                public_comment="",
                sogo_visible=False,
                sender_allowed=True,
            ),
            99: AliasRecord(
                id=99,
                address=USER,
                goto=USER,
                domain=DOMAIN,
                active=True,
                private_comment="",
                public_comment="",
                sogo_visible=False,
                sender_allowed=True,
            ),
        }
        self.next_alias_id = 100

    async def close(self) -> None:
        pass

    async def get_mailbox(self, email: str):
        return {
            "username": email,
            "domain": email.rsplit("@", 1)[-1],
            "tags": list(self.mailbox_tags),
        }

    async def get_domain(self, domain: str):
        return {
            "domain": domain,
            "tags": list(self.domain_tags),
            "max_num_aliases_for_domain": 50,
            "aliases_in_domain": len(self.aliases),
            "aliases_left": max(0, 50 - len(self.aliases)),
        }

    async def list_aliases(self) -> list[AliasRecord]:
        return [self.aliases[key] for key in sorted(self.aliases)]

    async def get_alias(self, alias_id: int) -> AliasRecord:
        return self.aliases[alias_id]

    async def set_mailbox_tags(self, email: str, tags: list[str]) -> None:
        assert email == USER
        self.mailbox_tags = list(tags)

    async def delete_mailbox_tags(self, email: str, tags: list[str]) -> None:
        assert email == USER
        removed = {tag.casefold() for tag in tags}
        self.mailbox_tags = [
            tag for tag in self.mailbox_tags if tag.casefold() not in removed
        ]

    async def create_alias(
        self,
        address: str,
        target: str,
        public_comment: str = "",
        *,
        private_comment: str = "",
        sogo_visible: bool = False,
    ) -> None:
        alias_id = self.next_alias_id
        self.next_alias_id += 1
        self.aliases[alias_id] = AliasRecord(
            id=alias_id,
            address=address,
            goto=target,
            domain=address.rsplit("@", 1)[-1],
            active=True,
            private_comment=private_comment,
            public_comment=public_comment,
            sogo_visible=sogo_visible,
            sender_allowed=True,
        )

    async def update_alias_preferences(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
    ) -> None:
        self.aliases[alias_id] = replace(
            self.aliases[alias_id],
            public_comment=public_comment,
            sogo_visible=sogo_visible,
        )

    async def assign_reserved_alias(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
    ) -> None:
        self.aliases[alias_id] = replace(
            self.aliases[alias_id],
            private_comment="",
            public_comment=public_comment,
            sogo_visible=sogo_visible,
        )

    async def set_active(self, alias_id: int, active: bool) -> None:
        await self.set_active_many([alias_id], active)

    async def set_active_many(self, alias_ids: list[int], active: bool) -> None:
        for alias_id in alias_ids:
            self.aliases[alias_id] = replace(self.aliases[alias_id], active=active)

    async def set_sogo_visible_many(self, alias_ids: list[int], visible: bool) -> None:
        for alias_id in alias_ids:
            self.aliases[alias_id] = replace(
                self.aliases[alias_id],
                sogo_visible=visible,
            )

    async def mark_reserved_alias_used(self, alias_id: int) -> None:
        alias = self.aliases[alias_id]
        if alias.is_reserved:
            self.aliases[alias_id] = replace(alias, private_comment=USED_RESERVED_COMMENT)

    async def delete_alias(self, alias_id: int) -> None:
        del self.aliases[alias_id]


class NoopUsageCollector:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def run_forever(self) -> None:
        await asyncio.Future()


MAILCOW = FakeMailcow()


async def fake_exchange_code(_settings, _code):
    return {"email": USER}


def fake_validate_oauth_state(_request, _state) -> None:
    pass


main_module.MailcowClient = lambda _settings: MAILCOW
main_module.UsageCollector = NoopUsageCollector
main_module.exchange_code = fake_exchange_code
main_module.validate_oauth_state = fake_validate_oauth_state

SETTINGS = Settings(
    MOOLIAS_BASE_URL=BASE_URL,
    MOOLIAS_SESSION_SECRET="e2e-session-secret-" * 4,
    MOOLIAS_COOKIE_SECURE=False,
    MOOLIAS_TRUSTED_HOSTS="127.0.0.1,localhost",
    MOOLIAS_USAGE_STATS=True,
    MOOLIAS_USAGE_TAG="moolias-stats",
    MOOLIAS_USAGE_DB_PATH=str(DB_PATH),
    MOOLIAS_USAGE_POLL_SECONDS=60,
    MOOLIAS_USAGE_HISTORY_COUNT=1000,
    MAILCOW_URL="https://mail.example.org",
    MAILCOW_API_KEY="e2e-api-key",
    MAILCOW_OAUTH_CLIENT_ID="e2e-client",
    MAILCOW_OAUTH_CLIENT_SECRET="e2e-secret",
)

app = main_module.create_app(SETTINGS)


def _clear_statistics(path: Path) -> None:
    tables = (
        "alias_icon_settings",
        "sender_alias_settings",
        "sender_expectations",
        "sender_usage",
        "sender_processed_events",
        "sender_mode_state",
        "alias_usage",
        "processed_events",
    )
    with sqlite3.connect(path, timeout=10) as connection:
        existing = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        for table in tables:
            if table in existing:
                connection.execute(f"DELETE FROM {table}")


async def _seed_statistics(store: StatsStore) -> None:
    started_at = await store.tracking_started_at()
    await store.sync_sender_modes({USER: "full"}, now=started_at + 1)

    await store.record_received(
        [
            UsageEvent("amazon-received-1", USER, "amazon-k7@example.org", started_at + 2),
            UsageEvent("amazon-received-2", USER, "amazon-k7@example.org", started_at + 3),
            UsageEvent("github-received-1", USER, "github-m4@example.org", started_at + 4),
            UsageEvent("pool-received-1", USER, "mond-segel-42@example.org", started_at + 5),
            UsageEvent("pool-received-2", USER, "mond-segel-42@example.org", started_at + 6),
        ]
    )
    await store.record_sent(
        [
            UsageEvent("amazon-sent-1", USER, "amazon-k7@example.org", started_at + 7),
        ]
    )
    await store.record_senders(
        [
            SenderEvent(
                "amazon-sender-1",
                USER,
                "amazon-k7@example.org",
                "amazon.de",
                "news@amazon.de",
                "full",
                started_at + 2,
            ),
            SenderEvent(
                "amazon-sender-2",
                USER,
                "amazon-k7@example.org",
                "amazon.de",
                "news@amazon.de",
                "full",
                started_at + 3,
            ),
            SenderEvent(
                "amazon-unexpected-1",
                USER,
                "amazon-k7@example.org",
                "unexpected.example",
                "odd@unexpected.example",
                "full",
                started_at + 4,
            ),
            SenderEvent(
                "github-sender-1",
                USER,
                "github-m4@example.org",
                "github.com",
                "notifications@github.com",
                "full",
                started_at + 5,
            ),
            SenderEvent(
                "pool-sender-1",
                USER,
                "mond-segel-42@example.org",
                "example.net",
                "booking@example.net",
                "full",
                started_at + 5,
            ),
            SenderEvent(
                "pool-sender-2",
                USER,
                "mond-segel-42@example.org",
                "example.net",
                "booking@example.net",
                "full",
                started_at + 6,
            ),
        ]
    )


@app.post("/__e2e__/reset")
async def reset_e2e_state() -> Response:
    MAILCOW.reset()
    store = app.state.stats_store
    if store is None:
        raise RuntimeError("E2E statistics store is not initialized")
    await asyncio.to_thread(_clear_statistics, store.path)
    await _seed_statistics(store)
    return Response(status_code=204)
