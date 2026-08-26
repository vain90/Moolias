from __future__ import annotations

import json
import secrets
import time
from typing import Any

import httpx

from moolias.sender_protocol import (
    NONCE_HEADER,
    PROTOCOL_VERSION,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    request_signature,
)


class AliasDeliveryAgentError(RuntimeError):
    pass


class AliasDeliveryAgentClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        verify_tls: bool = True,
        timeout: float = 5.0,
    ) -> None:
        self.secret = secret
        self.client = httpx.AsyncClient(
            base_url=f"{base_url.rstrip('/')}/",
            verify=verify_tls,
            timeout=timeout,
            trust_env=False,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def probe(self) -> None:
        try:
            response = await self.client.get("healthz")
        except httpx.HTTPError as exc:
            raise AliasDeliveryAgentError(str(exc)) from exc
        if response.is_error:
            raise AliasDeliveryAgentError(
                f"Mailcow Agent health check returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise AliasDeliveryAgentError("Mailcow Agent returned invalid health data") from exc
        capabilities = payload.get("capabilities") or []
        if (
            payload.get("status") != "ok"
            or payload.get("protocol") != PROTOCOL_VERSION
            or "first_mail_delivery_bypass" not in capabilities
        ):
            raise AliasDeliveryAgentError("Mailcow Agent does not support alias delivery bypass")

    async def set_bypass(self, recipients: tuple[str, ...], expires_at: int) -> None:
        await self._signed_post(
            "/v1/delivery-bypass",
            {
                "recipients": list(recipients),
                "enabled": True,
                "expires_at": int(expires_at),
            },
        )

    async def clear_bypass(self, recipients: tuple[str, ...]) -> None:
        await self._signed_post(
            "/v1/delivery-bypass",
            {
                "recipients": list(recipients),
                "enabled": False,
                "expires_at": None,
            },
        )

    async def _signed_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        timestamp = int(time.time())
        nonce = secrets.token_urlsafe(24)
        signature = request_signature(
            self.secret,
            "POST",
            path,
            timestamp,
            nonce,
            body,
        )
        try:
            response = await self.client.post(
                path.lstrip("/"),
                content=body,
                headers={
                    "Content-Type": "application/json",
                    TIMESTAMP_HEADER: str(timestamp),
                    NONCE_HEADER: nonce,
                    SIGNATURE_HEADER: signature,
                },
            )
        except httpx.HTTPError as exc:
            raise AliasDeliveryAgentError(str(exc)) from exc
        if response.is_error:
            raise AliasDeliveryAgentError(
                f"Mailcow Agent returned HTTP {response.status_code}"
            )
        try:
            parsed = response.json()
        except ValueError as exc:
            raise AliasDeliveryAgentError("Mailcow Agent returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise AliasDeliveryAgentError("Mailcow Agent returned invalid data")
        return parsed


def alias_delivery_agent_url(settings: Any) -> str:
    configured = str(settings.sender_agent_url or "").strip()
    if configured:
        return configured.rstrip("/")
    return f"{settings.mailcow_url.rstrip('/')}/moolias-agent"
