from __future__ import annotations

import asyncio

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import PlainTextResponse

from moolias.alias_workflows import AliasWorkflowStore
from moolias.aliases import is_owned_alias, is_primary_mailbox_alias
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf

BULK_ACTIONS = {"enable", "disable", "sogo-on", "sogo-off"}

router = APIRouter()


def _replacement_lock(request: Request) -> asyncio.Lock:
    lock = getattr(request.app.state, "alias_replacement_lock", None)
    if lock is None:
        lock = asyncio.Lock()
        request.app.state.alias_replacement_lock = lock
    return lock


async def _workflow_store(request: Request) -> AliasWorkflowStore:
    store = getattr(request.app.state, "alias_workflow_store", None)
    if store is not None:
        return store
    store = AliasWorkflowStore(request.app.state.settings.usage_db_path)
    await store.initialize()
    request.app.state.alias_workflow_store = store
    return store


async def _selected_aliases(request: Request, user: str, alias_ids: list[int]):
    selected_ids = list(dict.fromkeys(alias_ids))
    if not selected_ids or len(selected_ids) > 100:
        raise HTTPException(status_code=400, detail="Select between 1 and 100 aliases")

    try:
        aliases = await request.app.state.mailcow.list_aliases()
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    aliases_by_id = {alias.id: alias for alias in aliases}
    selected = []
    for alias_id in selected_ids:
        alias = aliases_by_id.get(alias_id)
        if (
            alias is None
            or not is_owned_alias(alias, user)
            or is_primary_mailbox_alias(alias, user)
            or alias.is_reserved
        ):
            raise HTTPException(
                status_code=403,
                detail="Bulk selection contains an alias that cannot be managed",
            )
        selected.append(alias)
    return selected


async def _disable_aliases(request: Request, user: str, selected) -> None:
    store = await _workflow_store(request)
    async with _replacement_lock(request):
        pending = await store.pending_replacements(user)
        selected_addresses = {alias.address.lower() for alias in selected}
        selected_ids = {alias.id for alias in selected}

        if any(workflow.new_address.lower() in selected_addresses for workflow in pending):
            raise HTTPException(
                status_code=409,
                detail=(
                    "A new alias from an ongoing alias change must be disabled individually"
                ),
            )

        completed_workflows = {
            workflow.id: workflow
            for workflow in pending
            if workflow.old_alias_id in selected_ids
            or (workflow.old_address or "").lower() in selected_addresses
        }

        try:
            await request.app.state.mailcow.set_active_many(
                [alias.id for alias in selected],
                False,
            )
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        for workflow in completed_workflows.values():
            await store.complete_replacement(user, workflow.id)


@router.post("/aliases/bulk", response_class=PlainTextResponse)
async def bulk_aliases(
    request: Request,
    action: str = Form(...),
    alias_ids: list[int] = Form(...),  # noqa: B008
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if action not in BULK_ACTIONS:
        raise HTTPException(status_code=400, detail="Unknown bulk action")

    selected = await _selected_aliases(request, user, alias_ids)
    selected_ids = [alias.id for alias in selected]

    if action == "disable":
        await _disable_aliases(request, user, selected)
        return PlainTextResponse("ok\n")

    try:
        if action == "enable":
            await request.app.state.mailcow.set_active_many(selected_ids, True)
        elif action == "sogo-on":
            await request.app.state.mailcow.set_sogo_visible_many(selected_ids, True)
        else:
            await request.app.state.mailcow.set_sogo_visible_many(selected_ids, False)
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return PlainTextResponse("ok\n")
