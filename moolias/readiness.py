from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from moolias.alias_delivery_agent import mailcow_agent_url
from moolias.sender_protection import MailcowAgentClient

router = APIRouter()
READINESS_TIMEOUT_SECONDS = 3.0
READINESS_PROBE_MAILBOX = "readiness@moolias.invalid"


async def _probe_mailcow(mailcow: Any) -> None:
    await mailcow.list_domains()


async def _probe_mailcow_agent(settings: Any) -> None:
    async with MailcowAgentClient(
        mailcow_agent_url(settings),
        settings.mailcow_agent_secret,
        verify_tls=settings.mailcow_verify_tls,
        timeout=2.0,
    ) as agent:
        await agent.probe()
        state = await agent.status(READINESS_PROBE_MAILBOX)
        if state.mailbox.casefold() != READINESS_PROBE_MAILBOX:
            raise RuntimeError("Mailcow Agent returned the wrong readiness mailbox")


async def readiness_checks(settings: Any, mailcow: Any) -> dict[str, bool]:
    async def bounded(probe) -> bool:
        try:
            await asyncio.wait_for(probe, timeout=READINESS_TIMEOUT_SECONDS)
        except Exception:
            return False
        return True

    mailcow_ready, agent_ready = await asyncio.gather(
        bounded(_probe_mailcow(mailcow)),
        bounded(_probe_mailcow_agent(settings)),
    )
    return {
        "mailcow": mailcow_ready,
        "mailcow_agent": agent_ready,
    }


@router.get("/readyz", response_class=PlainTextResponse, include_in_schema=False)
async def readyz(request: Request) -> PlainTextResponse:
    checks = await readiness_checks(
        request.app.state.settings,
        request.app.state.mailcow,
    )
    if all(checks.values()):
        return PlainTextResponse("ready\n")
    return PlainTextResponse("not ready\n", status_code=503)
