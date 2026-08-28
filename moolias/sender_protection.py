from __future__ import annotations

import asyncio
import json
import math
import secrets
import time
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, ValidationError

from moolias.alias_delivery_agent import mailcow_agent_url
from moolias.mailcow import MailcowAccessDenied, MailcowError
from moolias.security import require_user, validate_csrf
from moolias.sender_protocol import (
    NONCE_HEADER,
    PROTOCOL_VERSION,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    AgentProtectionState,
    request_signature,
)

router = APIRouter()


class SenderProtectionError(RuntimeError):
    pass


class MailcowAgentUnavailable(SenderProtectionError):
    pass


class MailcowAgentNotInstalled(SenderProtectionError):
    pass


class MailcowAgentAuthenticationError(SenderProtectionError):
    pass


class SenderProtectionExternalPolicy(SenderProtectionError):
    pass


class SenderProtectionCooldown(SenderProtectionError):
    def __init__(self, retry_after: int) -> None:
        super().__init__(f"Sender protection can be changed again in {retry_after} seconds")
        self.retry_after = max(1, retry_after)


class ProtectionChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    blocked: bool


class _LocalCooldown:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._lock = asyncio.Lock()
        self._changed_at: dict[str, float] = {}
        self._clock = clock

    async def remaining(self, mailbox: str, seconds: int) -> int:
        async with self._lock:
            changed_at = self._changed_at.get(mailbox)
            if changed_at is None:
                return 0
            return max(0, math.ceil(seconds - (self._clock() - changed_at)))

    async def mark(self, mailbox: str) -> None:
        async with self._lock:
            self._changed_at[mailbox] = self._clock()


_local_cooldown = _LocalCooldown()


class MailcowAgentClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        verify_tls: bool = True,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = f"{base_url.rstrip('/')}/"
        self.secret = secret
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            verify=verify_tls,
            timeout=timeout,
            trust_env=False,
            headers={"Accept": "application/json"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def __aenter__(self) -> MailcowAgentClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def probe(self) -> None:
        try:
            response = await self.client.get("healthz")
        except httpx.HTTPError as exc:
            raise MailcowAgentUnavailable(str(exc)) from exc
        if response.status_code == 404:
            raise MailcowAgentNotInstalled("Moolias Mailcow Agent was not found")
        if response.is_error:
            raise MailcowAgentUnavailable(
                f"Moolias Mailcow Agent health check returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise MailcowAgentUnavailable(
                "Moolias Mailcow Agent returned invalid health data"
            ) from exc
        if payload.get("status") != "ok" or payload.get("protocol") != PROTOCOL_VERSION:
            raise MailcowAgentUnavailable("Moolias Mailcow Agent protocol is incompatible")

    async def status(self, mailbox: str) -> AgentProtectionState:
        payload = await self._signed_post("/v1/status", {"mailbox": mailbox})
        return AgentProtectionState(
            mailbox=str(payload["mailbox"]),
            blocked=bool(payload["blocked"]),
            retry_after=max(0, int(payload.get("retry_after", 0))),
            managed=bool(payload.get("managed", True)),
        )

    async def set_blocked(self, mailbox: str, blocked: bool) -> tuple[AgentProtectionState, bool]:
        payload = await self._signed_post(
            "/v1/protection",
            {"mailbox": mailbox, "blocked": blocked},
        )
        return (
            AgentProtectionState(
                mailbox=str(payload["mailbox"]),
                blocked=bool(payload["blocked"]),
                retry_after=max(0, int(payload.get("retry_after", 0))),
                managed=bool(payload.get("managed", True)),
            ),
            bool(payload.get("changed", False)),
        )

    async def _signed_post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
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
            raise MailcowAgentUnavailable(str(exc)) from exc

        if response.status_code == 401:
            raise MailcowAgentAuthenticationError("Moolias Mailcow Agent authentication failed")
        if response.status_code == 404:
            raise MailcowAgentNotInstalled("Moolias Mailcow Agent endpoint was not found")
        if response.status_code == 409:
            raise SenderProtectionExternalPolicy(
                "Sender protection is managed by an existing Postfix rule"
            )
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After", "1")
            try:
                seconds = int(retry_after)
            except ValueError:
                seconds = 1
            raise SenderProtectionCooldown(seconds)
        if response.is_error:
            raise MailcowAgentUnavailable(
                f"Moolias Mailcow Agent returned HTTP {response.status_code}"
            )

        try:
            parsed = response.json()
        except ValueError as exc:
            raise MailcowAgentUnavailable("Moolias Mailcow Agent returned invalid JSON") from exc
        if not isinstance(parsed, dict):
            raise MailcowAgentUnavailable("Moolias Mailcow Agent returned invalid data")
        return parsed


def _error_reason(exc: SenderProtectionError) -> str:
    if isinstance(exc, MailcowAgentNotInstalled):
        return "not-installed"
    if isinstance(exc, MailcowAgentAuthenticationError):
        return "authentication"
    return "unreachable"


@router.get("/aliases/sender-protection")
async def get_sender_protection(request: Request):
    user = require_user(request)
    settings = request.app.state.settings
    if not settings.sender_protection:
        return {"enabled": False}

    async with MailcowAgentClient(
        mailcow_agent_url(settings),
        settings.mailcow_agent_secret,
        verify_tls=settings.mailcow_verify_tls,
    ) as agent:
        try:
            await agent.probe()
            state = await agent.status(user)
        except SenderProtectionError as exc:
            return {
                "enabled": True,
                "available": False,
                "reason": _error_reason(exc),
            }

    return {
        "enabled": True,
        "available": True,
        "blocked": state.blocked,
        "managed": state.managed,
        "retry_after": state.retry_after,
    }


@router.post("/aliases/sender-protection")
async def update_sender_protection(request: Request):
    validate_csrf(request, request.headers.get("x-csrf-token"))
    user = require_user(request)
    settings = request.app.state.settings
    if not settings.sender_protection:
        raise HTTPException(status_code=409, detail="Sender protection is disabled")

    try:
        payload = ProtectionChange.model_validate(await request.json())
    except (ValidationError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid sender protection request") from exc

    try:
        mailbox = await request.app.state.mailcow.get_mailbox(user)
    except MailcowAccessDenied:
        raise
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail="Mailbox verification failed") from exc

    mailbox_username = str(mailbox.get("username") or "").strip().casefold()
    if mailbox_username != user:
        raise HTTPException(status_code=403, detail="Mailbox identity mismatch")

    remaining = await _local_cooldown.remaining(
        user,
        settings.sender_protection_cooldown_seconds,
    )
    if remaining:
        raise HTTPException(
            status_code=429,
            detail="Sender protection cooldown is active",
            headers={"Retry-After": str(remaining)},
        )

    async with MailcowAgentClient(
        mailcow_agent_url(settings),
        settings.mailcow_agent_secret,
        verify_tls=settings.mailcow_verify_tls,
    ) as agent:
        try:
            await agent.probe()
            state, changed = await agent.set_blocked(user, payload.blocked)
        except SenderProtectionCooldown as exc:
            raise HTTPException(
                status_code=429,
                detail="Sender protection cooldown is active",
                headers={"Retry-After": str(exc.retry_after)},
            ) from exc
        except SenderProtectionExternalPolicy as exc:
            raise HTTPException(
                status_code=409,
                detail="Sender protection is managed by an existing Mailcow rule",
            ) from exc
        except MailcowAgentAuthenticationError as exc:
            raise HTTPException(
                status_code=502,
                detail="Mailcow Agent authentication failed",
            ) from exc
        except MailcowAgentNotInstalled as exc:
            raise HTTPException(status_code=503, detail="Mailcow Agent is not installed") from exc
        except MailcowAgentUnavailable as exc:
            raise HTTPException(status_code=503, detail="Mailcow Agent is unavailable") from exc

    if state.mailbox.casefold() != user:
        raise HTTPException(status_code=502, detail="Mailcow Agent returned the wrong mailbox")
    if changed:
        await _local_cooldown.mark(user)

    return {
        "blocked": state.blocked,
        "managed": state.managed,
        "retry_after": max(
            state.retry_after,
            settings.sender_protection_cooldown_seconds if changed else 0,
        ),
    }
