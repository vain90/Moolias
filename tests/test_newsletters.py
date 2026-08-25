from __future__ import annotations

import socket

import pytest

from moolias.newsletter_store import Newsletter, NewsletterLink
from moolias.newsletters import (
    _decode_header_text,
    _dkim_covers_one_click,
    _history_candidate,
    _newsletter_sort_key,
    _normalise_newsletter_status_filter,
    _public_https_target,
    _symbols,
    _unsubscribe_targets,
)


def _newsletter(
    newsletter_id: int,
    *,
    last_seen_at: int,
    unsubscribed_at: int | None = None,
    has_link: bool = False,
) -> Newsletter:
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
    ) if has_link else ()
    return Newsletter(
        id=newsletter_id,
        mailbox="owner@example.org",
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


def test_newsletter_status_filter_defaults_to_active():
    assert _normalise_newsletter_status_filter(None) == "active"
    assert _normalise_newsletter_status_filter("") == "active"
    assert _normalise_newsletter_status_filter("invalid") == "active"
    assert _normalise_newsletter_status_filter("all") == "all"
    assert _normalise_newsletter_status_filter("unsubscribed") == "unsubscribed"


def test_newsletter_sort_prioritizes_actionable_active_rows_and_keeps_unsubscribed_last():
    resumed = _newsletter(
        1,
        last_seen_at=200,
        unsubscribed_at=150,
        has_link=True,
    )
    actionable = _newsletter(2, last_seen_at=400, has_link=True)
    no_link = _newsletter(3, last_seen_at=500)
    unsubscribed = _newsletter(
        4,
        last_seen_at=600,
        unsubscribed_at=700,
        has_link=True,
    )

    ordered = sorted(
        [unsubscribed, no_link, actionable, resumed],
        key=_newsletter_sort_key,
    )

    assert [item.id for item in ordered] == [1, 2, 3, 4]


def test_newsletter_sort_uses_last_seen_within_same_priority():
    older = _newsletter(1, last_seen_at=100, has_link=True)
    newer = _newsletter(2, last_seen_at=200, has_link=True)

    ordered = sorted([older, newer], key=_newsletter_sort_key)

    assert [item.id for item in ordered] == [2, 1]


def test_encoded_sender_name_is_decoded_for_display():
    assert (
        _decode_header_text("=?UTF-8?Q?HUK24_AG_-_Digital=2E_Einfach=2E_G=C3=BCnstiger=2E?=")
        == "HUK24 AG - Digital. Einfach. Günstiger."
    )


def test_unsubscribe_targets_prefers_https_and_keeps_mailto():
    https_url, mailto = _unsubscribe_targets(
        "<https://example.org/unsubscribe?token=abc>, <mailto:leave@example.org>"
    )
    assert https_url == "https://example.org/unsubscribe?token=abc"
    assert mailto == "mailto:leave@example.org"


def test_unsubscribe_targets_rejects_non_https_web_link():
    https_url, mailto = _unsubscribe_targets(
        "<http://example.org/unsubscribe>, <mailto:leave@example.org>"
    )
    assert https_url is None
    assert mailto == "mailto:leave@example.org"


def test_dkim_signature_must_cover_both_one_click_headers():
    signature = (
        "v=1; a=rsa-sha256; d=example.org; "
        "h=from:to:subject:list-unsubscribe:list-unsubscribe-post; bh=abc; b=def"
    )
    assert _dkim_covers_one_click(signature) is True
    assert _dkim_covers_one_click(
        "v=1; d=example.org; h=from:to:subject:list-unsubscribe; b=def"
    ) is False


def test_rspamd_string_symbols_are_normalised_to_symbol_names():
    item = {
        "symbols": (
            "R_DKIM_ALLOW(-0.20)[example.org:s=mail], "
            "MAILLIST(-0.18)[generic], HAS_LIST_UNSUB(-0.01)[]"
        )
    }
    assert _symbols(item) == {"R_DKIM_ALLOW", "MAILLIST", "HAS_LIST_UNSUB"}


def test_history_candidate_accepts_authenticated_maillist_symbol():
    item = {
        "action": "no action",
        "message-id": "abc@example.org",
        "unix_time": 1_780_000_000,
        "symbols": "R_DKIM_ALLOW(-0.20)[example.org:s=mail], MAILLIST(-0.18)[generic]",
    }
    assert _history_candidate(item) is True


def test_history_candidate_accepts_authenticated_body_unsubscribe_symbol():
    item = {
        "action": "no action",
        "message-id": "sonos@example.org",
        "unix_time": 1_780_000_000,
        "symbols": (
            "R_DKIM_ALLOW(-0.20)[con.example.org:s=mail], "
            "MOOLIAS_BODY_UNSUB(0.00)[abbestellen]"
        ),
    }
    assert _history_candidate(item) is True


def test_history_candidate_requires_clean_authenticated_newsletter_signal():
    item = {
        "action": "no action",
        "message-id": "abc@example.org",
        "unix_time": 1_780_000_000,
        "symbols": {
            "HAS_LIST_UNSUB": {},
            "R_DKIM_ALLOW": {},
        },
    }
    assert _history_candidate(item) is True

    item["action"] = "add header"
    assert _history_candidate(item) is False

    item["action"] = "no action"
    item["symbols"] = {"HAS_LIST_UNSUB": {}}
    assert _history_candidate(item) is False


def test_public_https_target_rejects_private_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))
        ],
    )
    with pytest.raises(ValueError, match="non-public"):
        _public_https_target("https://newsletter.example/unsubscribe")


def test_public_https_target_pins_public_resolution(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
        ],
    )
    hostname, target, addresses = _public_https_target(
        "https://newsletter.example/unsubscribe?token=a%2Fb"
    )
    assert hostname == "newsletter.example"
    assert target == "/unsubscribe?token=a%2Fb"
    assert addresses == ["93.184.216.34"]


def test_public_https_target_rejects_nonstandard_port(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args, **_kwargs: [])
    with pytest.raises(ValueError, match="port 443"):
        _public_https_target("https://newsletter.example:8443/unsubscribe")
