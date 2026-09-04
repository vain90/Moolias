from __future__ import annotations

import time

from fastapi import APIRouter, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from moolias.alias_table_ui import _provision_now, _workflow_store
from moolias.alias_wait import AliasWaitService
from moolias.alias_workflows import AliasWorkflow
from moolias.aliases import is_owned_alias, is_primary_mailbox_alias
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf
from moolias.ui import _safe_return_to

router = APIRouter()


def _wants_json(request: Request) -> bool:
    return "application/json" in request.headers.get("accept", "").lower()


def _wait_payload(request: Request, workflow: AliasWorkflow) -> dict[str, object]:
    return {
        "workflow_id": workflow.id,
        "address": workflow.new_address,
        "state": workflow.waiting_state,
        "watcher_active": workflow.watcher_active,
        "new_mail_received_at": workflow.new_mail_received_at,
        "expires_at": workflow.bypass_expires_at,
        "poll_seconds": request.app.state.settings.alias_workflow_poll_seconds,
    }


async def _clear_now(request: Request, workflow: AliasWorkflow) -> None:
    coordinator = getattr(request.app.state, "alias_workflow_coordinator", None)
    if coordinator is not None:
        await coordinator.clear_workflow_bypass(workflow)


@router.get("/aliases/wait-status")
async def alias_wait_status(request: Request):
    user = require_user(request)
    store = await _workflow_store(request)
    waits = await AliasWaitService(store).active_for_mailbox(
        user,
        now=int(time.time()),
    )
    return {
        "active": [
            {
                "address": wait.address,
                "workflow_id": wait.workflow_id,
                "expires_at": wait.expires_at,
            }
            for wait in waits
        ],
        "poll_seconds": request.app.state.settings.alias_workflow_poll_seconds,
    }


@router.post("/aliases/{alias_id}/wait-for-mail")
async def wait_for_alias_mail(
    request: Request,
    alias_id: int,
    csrf_token: str = Form(...),
    return_to: str = Form("/aliases"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)

    try:
        alias = await request.app.state.mailcow.get_alias(alias_id)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    if not is_owned_alias(alias, user) or is_primary_mailbox_alias(alias, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Alias cannot use the temporary delivery wait here",
        )
    if not alias.active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Disabled aliases cannot wait for mail",
        )

    now = int(time.time())
    store = await _workflow_store(request)
    try:
        workflow = await AliasWaitService(store).start(
            mailbox=user,
            alias_id=alias.id,
            address=alias.address,
            alias_name=alias.name,
            alias_description=alias.private_description,
            started_at=now,
            bypass_expires_at=(
                now + request.app.state.settings.alias_workflow_bypass_seconds
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await _provision_now(request, workflow)
    if _wants_json(request):
        return _wait_payload(request, workflow)
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.post("/aliases/manual-waits/{workflow_id}/stop")
async def stop_alias_wait(
    request: Request,
    workflow_id: int,
    csrf_token: str = Form(...),
    return_to: str = Form("/aliases"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    store = await _workflow_store(request)
    workflow = await AliasWaitService(store).stop(
        user,
        workflow_id,
        now=int(time.time()),
    )
    if workflow is None:
        raise HTTPException(status_code=404, detail="Alias wait not found")

    await _clear_now(request, workflow)
    if _wants_json(request):
        return _wait_payload(request, workflow)
    return RedirectResponse(_safe_return_to(return_to), status_code=303)
