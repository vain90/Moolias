from __future__ import annotations

import asyncio
import json
import os
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from moolias import __version__
from moolias.mailcow_agent import AgentAuthenticator, AgentConfigurationError
from moolias.sender_protocol import (
    NONCE_HEADER,
    PROTOCOL_VERSION,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
)

DEFAULT_DOVEADM_HOST = "dovecot-mailcow:12345"
MAX_DOVEADM_OUTPUT = 512 * 1024
_MESSAGE_ID_RE = re.compile(r"^[^\x00\r\n]{1,998}$")
_MAILBOX_RE = re.compile(r"^[^\s@]+@[^\s@]+$")


class NewsletterHeaderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mailbox: str = Field(min_length=3, max_length=320)
    message_id: str = Field(min_length=1, max_length=998)


class DoveadmError(RuntimeError):
    pass


def _normalise_mailbox(value: str) -> str:
    mailbox = value.strip().casefold()
    if not _MAILBOX_RE.fullmatch(mailbox):
        raise ValueError("Invalid mailbox")
    return mailbox


def _normalise_message_id(value: str) -> str:
    message_id = value.strip()
    if message_id.startswith("<") and message_id.endswith(">"):
        message_id = message_id[1:-1].strip()
    if not _MESSAGE_ID_RE.fullmatch(message_id):
        raise ValueError("Invalid message ID")
    return message_id


class DoveadmNewsletterReader:
    FIELDS = (
        "hdr.from",
        "hdr.to",
        "hdr.delivered-to",
        "hdr.list-id",
        "hdr.list-unsubscribe",
        "hdr.list-unsubscribe-post",
        "hdr.dkim-signature",
        "hdr.authentication-results",
    )

    def __init__(
        self,
        password: str,
        host: str = DEFAULT_DOVEADM_HOST,
        *,
        timeout: float = 10.0,
    ) -> None:
        if not password:
            raise AgentConfigurationError("MOOLIAS_DOVEADM_PASSWORD is required")
        if not host or any(character.isspace() for character in host):
            raise AgentConfigurationError("MOOLIAS_DOVEADM_HOST is invalid")
        self.password = password
        self.host = host
        self.timeout = timeout

    async def fetch_headers(self, mailbox: str, message_id: str) -> dict[str, Any] | None:
        mailbox = _normalise_mailbox(mailbox)
        message_id = _normalise_message_id(message_id)
        command = (
            "doveadm",
            "-o",
            f"doveadm_password={self.password}",
            "-f",
            "json",
            "fetch",
            "-S",
            self.host,
            "-u",
            mailbox,
            " ".join(self.FIELDS),
            "mailbox",
            "*",
            "HEADER",
            "Message-ID",
            message_id,
        )
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=self.timeout)
        except TimeoutError as exc:
            if "process" in locals() and process.returncode is None:
                process.kill()
                await process.wait()
            raise DoveadmError("Dovecot header lookup timed out") from exc
        except OSError as exc:
            raise DoveadmError("doveadm could not be executed") from exc

        if len(stdout) > MAX_DOVEADM_OUTPUT:
            raise DoveadmError("Dovecot returned too much data")
        if process.returncode != 0:
            detail = stderr.decode("utf-8", errors="replace").strip()
            if len(detail) > 300:
                detail = detail[:300] + "…"
            raise DoveadmError(detail or "Dovecot header lookup failed")
        if not stdout.strip():
            return None

        try:
            payload = json.loads(stdout)
        except ValueError as exc:
            raise DoveadmError("Dovecot returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise DoveadmError("Dovecot returned an unexpected response")

        records = [item for item in payload if isinstance(item, dict)]
        if not records:
            return None

        # A message can exist in multiple folders. The header content is identical for
        # our purpose, so prefer the first record containing List-Unsubscribe.
        selected = next(
            (item for item in records if str(item.get("hdr.list-unsubscribe") or "").strip()),
            records[0],
        )
        return {
            "matches": len(records),
            "from": str(selected.get("hdr.from") or "").strip(),
            "to": str(selected.get("hdr.to") or "").strip(),
            "delivered_to": str(selected.get("hdr.delivered-to") or "").strip(),
            "list_id": str(selected.get("hdr.list-id") or "").strip(),
            "list_unsubscribe": str(selected.get("hdr.list-unsubscribe") or "").strip(),
            "list_unsubscribe_post": str(
                selected.get("hdr.list-unsubscribe-post") or ""
            ).strip(),
            "dkim_signature": str(selected.get("hdr.dkim-signature") or "").strip(),
            "authentication_results": str(
                selected.get("hdr.authentication-results") or ""
            ).strip(),
        }


def create_newsletter_agent_app(
    *,
    secret: str | None = None,
    doveadm_password: str | None = None,
    doveadm_host: str | None = None,
) -> FastAPI:
    resolved_secret = secret if secret is not None else os.environ.get(
        "MOOLIAS_NEWSLETTER_AGENT_SECRET",
        "",
    )
    resolved_password = (
        doveadm_password
        if doveadm_password is not None
        else os.environ.get("MOOLIAS_DOVEADM_PASSWORD", "")
    )
    resolved_host = doveadm_host or os.environ.get("MOOLIAS_DOVEADM_HOST", DEFAULT_DOVEADM_HOST)

    authenticator = AgentAuthenticator(resolved_secret)
    reader = DoveadmNewsletterReader(resolved_password, resolved_host)

    app = FastAPI(
        title="Moolias Newsletter Agent",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.authenticator = authenticator
    app.state.reader = reader

    @app.get("/healthz")
    async def healthz():
        return {
            "status": "ok",
            "protocol": PROTOCOL_VERSION,
            "version": __version__,
            "service": "newsletter-agent",
        }

    @app.post("/v1/headers")
    async def headers(request: Request):
        body = await request.body()
        authenticator.verify(
            method=request.method,
            path=request.url.path,
            body=body,
            timestamp_value=request.headers.get(TIMESTAMP_HEADER),
            nonce=request.headers.get(NONCE_HEADER),
            signature=request.headers.get(SIGNATURE_HEADER),
        )
        try:
            payload = NewsletterHeaderRequest.model_validate_json(body)
            mailbox = _normalise_mailbox(payload.mailbox)
            message_id = _normalise_message_id(payload.message_id)
        except (ValidationError, ValueError) as exc:
            raise HTTPException(
                status_code=400,
                detail="Invalid newsletter header request",
            ) from exc

        try:
            result = await reader.fetch_headers(mailbox, message_id)
        except DoveadmError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if result is None:
            raise HTTPException(status_code=404, detail="Message was not found")
        return result

    return app
