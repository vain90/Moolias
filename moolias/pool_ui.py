from __future__ import annotations

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from moolias.aliases import (
    RESERVED_COMMENT,
    is_owned_alias,
    mailbox_domain,
    readable_local_part,
    validate_local_part,
)
from moolias.i18n import LANGUAGE_COOKIE, detect_language
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf

router = APIRouter()


def _language(request: Request) -> str:
    return detect_language(
        request.cookies.get(LANGUAGE_COOKIE),
        request.headers.get("accept-language"),
    )


async def _owned_alias(request: Request, alias_id: int):
    user = require_user(request)
    try:
        alias = await request.app.state.mailcow.get_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if not is_owned_alias(alias, user):
        raise HTTPException(status_code=403, detail="Alias is not owned by the current mailbox")
    return user, alias


async def _create_unique_reserved(request: Request, user: str, attempts: int = 12) -> None:
    domain = mailbox_domain(user)
    last_error: Exception | None = None
    for _ in range(attempts):
        address = f"{validate_local_part(readable_local_part(_language(request)))}@{domain}"
        try:
            await request.app.state.mailcow.create_alias(
                address,
                user,
                "",
                private_comment=RESERVED_COMMENT,
                sogo_visible=False,
            )
            return
        except MailcowError as exc:
            last_error = exc
    raise MailcowError(
        f"Could not create a unique offline alias after {attempts} attempts: {last_error}"
    )


@router.post("/offline-pool/create")
async def create_offline_pool_aliases(
    request: Request,
    count: int = Form(...),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if count not in {1, 5, 10, 20}:
        raise HTTPException(status_code=400, detail="Pool size must be 1, 5, 10 or 20")
    try:
        for _ in range(count):
            await _create_unique_reserved(request, user)
    except (MailcowError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/offline-pool", status_code=303)


@router.post("/offline-pool/{alias_id}/assign")
async def assign_offline_pool_alias(
    request: Request,
    alias_id: int,
    description: str = Form(...),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    _, alias = await _owned_alias(request, alias_id)
    if not alias.is_reserved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only offline aliases can be assigned",
        )
    description = description.strip()
    if not description or len(description) > 160:
        raise HTTPException(status_code=400, detail="Purpose must be 1-160 characters")
    try:
        await request.app.state.mailcow.assign_reserved_alias(
            alias_id,
            description,
            sogo_visible,
        )
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/offline-pool", status_code=303)


@router.post("/offline-pool/{alias_id}/delete")
async def delete_offline_pool_alias(
    request: Request,
    alias_id: int,
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user, alias = await _owned_alias(request, alias_id)
    if not alias.is_reserved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only offline aliases can be deleted",
        )
    if alias.is_reserved_used:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Used offline aliases must be assigned before they can be deleted",
        )

    stats_store = getattr(request.app.state, "stats_store", None)
    if stats_store is not None:
        stored_usage = await stats_store.alias_usage(user, [alias.address])
        usage = stored_usage.get(alias.address.lower())
        if usage is not None and (usage.received_count > 0 or usage.sent_count > 0):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Used offline aliases must be assigned before they can be deleted",
            )

    try:
        await request.app.state.mailcow.delete_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse("/offline-pool", status_code=303)
