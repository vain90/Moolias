from __future__ import annotations

import json
import time
from unittest.mock import AsyncMock

import httpx

from moolias.newsletter_agent import (
    _extract_body_unsubscribe_url,
    _normalise_mailbox,
    _normalise_message_id,
    create_newsletter_agent_app,
)
from moolias.sender_protocol import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    request_signature,
)

SECRET = "n" * 64
DOVEADM_PASSWORD = "d" * 64


def _signed_headers(path: str, body: bytes, nonce: str) -> dict[str, str]:
    timestamp = int(time.time())
    return {
        "Content-Type": "application/json",
        TIMESTAMP_HEADER: str(timestamp),
        NONCE_HEADER: nonce,
        SIGNATURE_HEADER: request_signature(
            SECRET,
            "POST",
            path,
            timestamp,
            nonce,
            body,
        ),
    }


def test_newsletter_agent_normalises_mailbox_and_message_id():
    assert _normalise_mailbox(" User@Example.org ") == "user@example.org"
    assert _normalise_message_id(" <abc.123@example.org> ") == "abc.123@example.org"


def test_newsletter_agent_rejects_message_id_header_injection():
    try:
        _normalise_message_id("abc@example.org\nHEADER From evil@example.org")
    except ValueError:
        pass
    else:
        raise AssertionError("message ID containing a newline must be rejected")


def test_body_unsubscribe_parser_finds_plain_text_footer_link():
    raw = (
        "From: Sonos <news@example.org>\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Angebot und Produktinformationen.\n\n"
        "Abbestellen (\n"
        "https://link.example.org/unsubscribe/personal-token\n"
        ")\n"
    )
    assert (
        _extract_body_unsubscribe_url(raw)
        == "https://link.example.org/unsubscribe/personal-token"
    )


def test_body_unsubscribe_parser_prefers_link_with_unsubscribe_anchor_text():
    raw = (
        "From: Example <news@example.org>\n"
        "Content-Type: text/html; charset=utf-8\n"
        "\n"
        '<a href="https://example.org/shop">Shop</a>'
        '<a href="https://example.org/u/token">Newsletter abbestellen</a>'
    )
    assert _extract_body_unsubscribe_url(raw) == "https://example.org/u/token"


def test_body_unsubscribe_parser_does_not_return_unrelated_links():
    raw = (
        "From: Example <news@example.org>\n"
        "Content-Type: text/plain; charset=utf-8\n"
        "\n"
        "Mehr erfahren: https://example.org/product\n"
    )
    assert _extract_body_unsubscribe_url(raw) is None


async def test_newsletter_agent_requires_signature_and_returns_only_selected_headers():
    app = create_newsletter_agent_app(
        secret=SECRET,
        doveadm_password=DOVEADM_PASSWORD,
    )
    app.state.reader.fetch_headers = AsyncMock(
        return_value={
            "matches": 1,
            "from": "Example <news@example.org>",
            "to": "alias@example.net",
            "delivered_to": "",
            "list_id": "",
            "list_unsubscribe": "<https://example.org/unsubscribe/token>",
            "list_unsubscribe_post": "List-Unsubscribe=One-Click",
            "dkim_signature": "v=1; h=from:list-unsubscribe:list-unsubscribe-post; b=x",
            "authentication_results": "dkim=pass",
            "body_unsubscribe_url": "",
        }
    )
    transport = httpx.ASGITransport(app=app)

    payload = {
        "mailbox": "user@example.org",
        "message_id": "message@example.org",
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        unsigned = await client.post("/v1/headers", content=body)
        assert unsigned.status_code == 401

        signed = await client.post(
            "/v1/headers",
            content=body,
            headers=_signed_headers(
                "/v1/headers",
                body,
                "newsletter-agent-test-nonce-001",
            ),
        )

    assert signed.status_code == 200
    assert signed.json()["list_unsubscribe"].startswith("<https://example.org/")
    app.state.reader.fetch_headers.assert_awaited_once_with(
        "user@example.org",
        "message@example.org",
        include_body_unsubscribe=False,
    )


async def test_newsletter_agent_allows_explicit_body_unsubscribe_lookup():
    app = create_newsletter_agent_app(
        secret=SECRET,
        doveadm_password=DOVEADM_PASSWORD,
    )
    app.state.reader.fetch_headers = AsyncMock(
        return_value={
            "matches": 1,
            "from": "Sonos <no-reply@example.org>",
            "to": "alias@example.net",
            "delivered_to": "",
            "list_id": "",
            "list_unsubscribe": "",
            "list_unsubscribe_post": "",
            "dkim_signature": "",
            "authentication_results": "dkim=pass",
            "body_unsubscribe_url": "https://example.org/unsubscribe/token",
        }
    )
    transport = httpx.ASGITransport(app=app)

    payload = {
        "mailbox": "user@example.org",
        "message_id": "message@example.org",
        "include_body_unsubscribe": True,
    }
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        response = await client.post(
            "/v1/headers",
            content=body,
            headers=_signed_headers(
                "/v1/headers",
                body,
                "newsletter-agent-test-nonce-body-001",
            ),
        )

    assert response.status_code == 200
    assert response.json()["body_unsubscribe_url"].startswith("https://")
    app.state.reader.fetch_headers.assert_awaited_once_with(
        "user@example.org",
        "message@example.org",
        include_body_unsubscribe=True,
    )


async def test_newsletter_agent_returns_not_found_without_exposing_mailbox_data():
    app = create_newsletter_agent_app(
        secret=SECRET,
        doveadm_password=DOVEADM_PASSWORD,
    )
    app.state.reader.fetch_headers = AsyncMock(return_value=None)
    transport = httpx.ASGITransport(app=app)

    body = b'{"mailbox":"user@example.org","message_id":"missing@example.org"}'
    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        response = await client.post(
            "/v1/headers",
            content=body,
            headers=_signed_headers(
                "/v1/headers",
                body,
                "newsletter-agent-test-nonce-002",
            ),
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "Message was not found"}
