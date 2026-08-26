from __future__ import annotations

import json

import httpx

from moolias.mailcow_agent import AgentStateStore, create_agent_app
from moolias.sender_protocol import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    request_signature,
)

SECRET = "b" * 64


def _headers(path: str, body: bytes, *, timestamp: int, nonce: str) -> dict[str, str]:
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


def test_delivery_bypass_is_exact_persistent_and_expires(tmp_path):
    now = [1000.0]
    state_dir = tmp_path / "state"
    bypass_map = tmp_path / "rspamd" / "moolias_firstmail_recipients.map"
    store = AgentStateStore(
        state_dir,
        policy_path=tmp_path / "postfix" / "blocked_sender_login.pcre",
        bypass_map_path=bypass_map,
        clock=lambda: now[0],
    )
    store.ensure_files()

    result = store.set_delivery_bypass(
        ["New+tag@Example.org"],
        enabled=True,
        expires_at=1010,
    )
    assert result["recipients"] == ["new+tag@example.org"]
    lines = bypass_map.read_text(encoding="utf-8").splitlines()
    assert "new+tag@example.org" in lines
    assert "example.org" not in lines

    restarted = AgentStateStore(
        state_dir,
        policy_path=tmp_path / "postfix" / "blocked_sender_login.pcre",
        bypass_map_path=bypass_map,
        clock=lambda: now[0],
    )
    restarted.ensure_files()
    assert restarted.delivery_bypass_status() == {"new+tag@example.org": 1010}

    now[0] = 1010.0
    assert restarted.expire_delivery_bypass() == ["new+tag@example.org"]
    assert restarted.delivery_bypass_status() == {}
    assert "new+tag@example.org" not in bypass_map.read_text(encoding="utf-8")


def test_delivery_bypass_can_cover_replacement_pair_and_clear_early(tmp_path):
    store = AgentStateStore(
        tmp_path / "state",
        policy_path=tmp_path / "postfix" / "blocked_sender_login.pcre",
        bypass_map_path=tmp_path / "rspamd" / "moolias_firstmail_recipients.map",
        clock=lambda: 1000.0,
    )
    store.ensure_files()
    store.set_delivery_bypass(
        ["old@example.org", "new@example.org"],
        enabled=True,
        expires_at=1600,
    )
    assert store.delivery_bypass_status() == {
        "new@example.org": 1600,
        "old@example.org": 1600,
    }

    store.set_delivery_bypass(
        ["old@example.org", "new@example.org"],
        enabled=False,
        expires_at=None,
    )
    assert store.delivery_bypass_status() == {}


async def test_delivery_bypass_endpoint_is_signed_and_rejects_broad_input(tmp_path):
    now = [2000.0]
    app = create_agent_app(
        secret=SECRET,
        state_dir=tmp_path / "state",
        policy_path=tmp_path / "postfix" / "blocked_sender_login.pcre",
        bypass_map_path=tmp_path / "rspamd" / "moolias_firstmail_recipients.map",
        clock=lambda: now[0],
    )
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://agent") as client:
        path = "/v1/delivery-bypass"
        payload = {
            "recipients": ["new@example.org"],
            "enabled": True,
            "expires_at": 2100,
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        response = await client.post(
            path,
            content=body,
            headers=_headers(
                path,
                body,
                timestamp=2000,
                nonce="delivery-bypass-abcdef",
            ),
        )
        assert response.status_code == 200
        assert response.json()["enabled"] is True

        broad_payload = {
            "recipients": ["*@example.org"],
            "enabled": True,
            "expires_at": 2100,
        }
        broad_body = json.dumps(
            broad_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        broad = await client.post(
            path,
            content=broad_body,
            headers=_headers(
                path,
                broad_body,
                timestamp=2000,
                nonce="delivery-broad-abcdefgh",
            ),
        )
        assert broad.status_code == 400
