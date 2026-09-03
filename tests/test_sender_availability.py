from __future__ import annotations

from pathlib import Path

from moolias.aliases import AliasRecord
from moolias.mailcow import MailcowAccessDenied
from moolias.sender_availability import (
    reconcile_sender_visibility,
    sender_available,
    sender_visibility_inconsistent,
)


def alias_record(
    alias_id: int,
    address: str,
    *,
    goto: str = "hidden@example.org",
    sender_allowed: bool | None,
    sogo_visible: bool,
) -> AliasRecord:
    return AliasRecord(
        id=alias_id,
        address=address,
        goto=goto,
        domain="example.org",
        active=True,
        private_comment="",
        public_comment=address.split("@", 1)[0],
        sogo_visible=sogo_visible,
        sender_allowed=sender_allowed,
    )


class FakeMailcow:
    def __init__(
        self,
        aliases: list[AliasRecord],
        denied_mailboxes: set[str] | None = None,
    ) -> None:
        self.aliases = aliases
        self.denied_mailboxes = denied_mailboxes or set()
        self.mailbox_checks: list[str] = []
        self.sogo_calls: list[tuple[list[int], bool]] = []

    async def list_aliases(self) -> list[AliasRecord]:
        return self.aliases

    async def get_mailbox(self, mailbox: str):
        self.mailbox_checks.append(mailbox)
        if mailbox in self.denied_mailboxes:
            raise MailcowAccessDenied("moolias-access")
        return {"username": mailbox, "domain": mailbox.rsplit("@", 1)[-1]}

    async def set_sogo_visible_many(self, alias_ids: list[int], visible: bool) -> None:
        self.sogo_calls.append((list(alias_ids), visible))


def test_sender_availability_uses_three_state_semantics() -> None:
    assert sender_available(
        alias_record(1, "yes@example.org", sender_allowed=True, sogo_visible=True)
    )
    assert sender_available(
        alias_record(2, "unknown@example.org", sender_allowed=None, sogo_visible=True)
    )
    assert not sender_available(
        alias_record(3, "no@example.org", sender_allowed=False, sogo_visible=False)
    )
    assert sender_visibility_inconsistent(
        alias_record(4, "bad@example.org", sender_allowed=False, sogo_visible=True)
    )


async def test_reconcile_withdraws_only_explicit_inconsistent_owned_aliases() -> None:
    aliases = [
        alias_record(1, "bad@example.org", sender_allowed=False, sogo_visible=True),
        alias_record(2, "already-hidden@example.org", sender_allowed=False, sogo_visible=False),
        alias_record(3, "allowed@example.org", sender_allowed=True, sogo_visible=True),
        alias_record(4, "unknown@example.org", sender_allowed=None, sogo_visible=True),
        alias_record(
            5,
            "shared@example.org",
            goto="hidden@example.org,other@example.org",
            sender_allowed=False,
            sogo_visible=True,
        ),
        alias_record(
            6,
            "denied@example.org",
            goto="denied-mailbox@example.org",
            sender_allowed=False,
            sogo_visible=True,
        ),
        alias_record(
            7,
            "primary@example.org",
            goto="primary@example.org",
            sender_allowed=False,
            sogo_visible=True,
        ),
    ]
    client = FakeMailcow(aliases, {"denied-mailbox@example.org"})

    mismatches = await reconcile_sender_visibility(client)

    assert [(item.alias_id, item.address, item.mailbox) for item in mismatches] == [
        (1, "bad@example.org", "hidden@example.org")
    ]
    assert client.sogo_calls == [([1], False)]
    assert client.mailbox_checks == ["hidden@example.org", "denied-mailbox@example.org"]


async def test_reconcile_never_reenables_sogo_when_sender_permission_returns() -> None:
    client = FakeMailcow(
        [
            alias_record(
                1,
                "sendable-again@example.org",
                sender_allowed=True,
                sogo_visible=False,
            )
        ]
    )

    mismatches = await reconcile_sender_visibility(client)

    assert mismatches == ()
    assert client.sogo_calls == []


def test_alias_ui_disables_sogo_for_explicitly_non_sendable_aliases() -> None:
    dashboard = Path("moolias/templates/dashboard.html").read_text(encoding="utf-8")
    offline_pool = Path("moolias/templates/offline_pool.html").read_text(encoding="utf-8")

    assert "alias.sender_allowed is sameas false" in dashboard
    assert "Als Absender nicht verfügbar" in dashboard
    assert "Unavailable as a sender" in dashboard
    assert "alias.sender_allowed is sameas false %}disabled" in dashboard

    assert "alias.sender_allowed is sameas false %}disabled" in offline_pool
    assert "Als Absender nicht verfügbar" in offline_pool
    assert "Unavailable as a sender" in offline_pool


def test_periodic_sender_visibility_housekeeping_is_registered() -> None:
    review_settings = Path("moolias/review_settings.py").read_text(encoding="utf-8")
    sender_module = Path("moolias/sender_availability.py").read_text(encoding="utf-8")

    assert "router.include_router(sender_availability_router)" in review_settings
    assert "SENDER_VISIBILITY_HOUSEKEEPING_SECONDS = 900" in sender_module
    assert "moolias-sender-visibility-housekeeping" in sender_module
