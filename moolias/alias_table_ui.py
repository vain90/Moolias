from __future__ import annotations

import asyncio
import sqlite3
import time
from contextlib import asynccontextmanager, suppress

from fastapi import APIRouter, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse

from moolias.alias_delivery_agent import AliasDeliveryAgentClient, alias_delivery_agent_url
from moolias.alias_workflow_coordinator import AliasWorkflowCoordinator
from moolias.alias_workflows import (
    DEACTIVATION_30_DAYS,
    DEACTIVATION_7_DAYS,
    DEACTIVATION_LATER,
    DEACTIVATION_MODES,
    DEACTIVATION_NOW,
    AliasWorkflow,
    AliasWorkflowStore,
)
from moolias.aliases import (
    RESERVED_MARKER,
    USED_RESERVED_MARKER,
    is_owned_alias,
    is_primary_mailbox_alias,
    mailbox_domain,
    named_local_part,
    readable_local_part,
    update_private_comment,
    validate_local_part,
)
from moolias.mailcow import MailcowError
from moolias.security import require_user, validate_csrf
from moolias.ui import (
    PAGE_SIZES,
    STATUS_FILTERS,
    TEMPLATES,
    _language,
    _load_ui_state,
    _pagination_items,
    _safe_return_to,
    _template_context,
)

SORT_MODES = {"attention", "last_used", "usage", "most_used", "status", "purpose"}
SORT_DIRECTIONS = {"asc", "desc"}


@asynccontextmanager
async def _workflow_lifespan(app):
    settings = app.state.settings
    store = AliasWorkflowStore(settings.usage_db_path)
    await store.initialize()

    agent = None
    if len(settings.sender_agent_secret.strip()) >= 32:
        agent = AliasDeliveryAgentClient(
            alias_delivery_agent_url(settings),
            settings.sender_agent_secret,
            verify_tls=settings.mailcow_verify_tls,
        )

    coordinator = AliasWorkflowCoordinator(
        settings,
        app.state.mailcow,
        store,
        agent,
    )
    app.state.alias_workflow_store = store
    app.state.alias_workflow_coordinator = coordinator
    task = asyncio.create_task(
        coordinator.run_forever(),
        name="moolias-alias-workflows",
    )
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        await coordinator.close()


router = APIRouter(lifespan=_workflow_lifespan)


async def _workflow_store(request: Request) -> AliasWorkflowStore:
    store = getattr(request.app.state, "alias_workflow_store", None)
    if store is not None:
        return store
    store = AliasWorkflowStore(request.app.state.settings.usage_db_path)
    await store.initialize()
    request.app.state.alias_workflow_store = store
    return store


async def _workflow_coordinator(request: Request) -> AliasWorkflowCoordinator | None:
    return getattr(request.app.state, "alias_workflow_coordinator", None)


def _workflow_payload(workflow: AliasWorkflow) -> dict[str, object]:
    return {
        "id": workflow.id,
        "kind": workflow.kind,
        "state": workflow.waiting_state,
        "old_address": workflow.old_address,
        "new_address": workflow.new_address,
        "name": workflow.alias_name,
        "description": workflow.alias_description,
        "started_at": workflow.started_at,
        "old_mail_received_at": workflow.old_mail_received_at,
        "new_mail_received_at": workflow.new_mail_received_at,
        "deactivation_mode": workflow.deactivation_mode,
        "scheduled_deactivation_at": workflow.scheduled_deactivation_at,
        "completed": workflow.completed_at is not None,
    }


async def _provision_now(request: Request, workflow: AliasWorkflow) -> None:
    coordinator = await _workflow_coordinator(request)
    if coordinator is not None:
        await coordinator.provision_workflow(workflow)


def _resume_waiting_sync(path: str, mailbox: str, workflow_id: int) -> None:
    with sqlite3.connect(path, timeout=10) as connection:
        connection.execute(
            """
            UPDATE alias_workflows
            SET watcher_active = 1
            WHERE id = ?
              AND mailbox = ? COLLATE NOCASE
              AND completed_at IS NULL
              AND new_mail_received_at IS NULL
            """,
            (int(workflow_id), mailbox.strip().lower()),
        )


async def _submitted_private_description(
    request: Request,
    parsed_value: str | None,
    *,
    fallback: str,
) -> str:
    form = await request.form()
    if "private_description" not in form:
        return fallback
    return (parsed_value or "").strip()


async def _create_unique_alias(
    request: Request,
    user: str,
    factory,
    *,
    public_comment: str,
    private_comment: str,
    sogo_visible: bool,
    attempts: int = 12,
) -> str:
    domain = mailbox_domain(user)
    last_error: Exception | None = None
    for _ in range(attempts):
        address = f"{validate_local_part(factory())}@{domain}"
        try:
            await request.app.state.mailcow.create_alias(
                address,
                user,
                public_comment,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
            return address
        except MailcowError as exc:
            last_error = exc
    raise MailcowError(
        f"Could not create a unique alias after {attempts} attempts: {last_error}"
    )


def _group_pages(groups: list[dict], per_page: int) -> list[list[dict]]:
    pages: list[list[dict]] = []
    current: list[dict] = []
    current_size = 0
    for group in groups:
        group_size = len(group["aliases"])
        if current and current_size + group_size > per_page:
            pages.append(current)
            current = []
            current_size = 0
        current.append(group)
        current_size += group_size
    if current or not pages:
        pages.append(current)
    return pages


@router.get("/aliases", response_class=HTMLResponse)
async def aliases_page(
    request: Request,
    q: str = Query(default="", max_length=160),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25),
    status_filter: str = Query(default="all", alias="status"),
    sort: str = Query(default="attention"),
    direction: str = Query(default="desc"),
):
    state = await _load_ui_state(request)
    user = state["user"]
    if per_page not in PAGE_SIZES:
        per_page = 25
    if status_filter not in STATUS_FILTERS:
        status_filter = "all"
    if sort not in SORT_MODES:
        sort = "attention"
    if sort == "most_used":
        sort = "usage"
    if direction not in SORT_DIRECTIONS:
        direction = "desc"

    assigned_all = list(state["assigned_all"])
    unexpected_aliases = state["unexpected_aliases"]
    no_usage_evidence = state["no_usage_evidence"]
    usage_stats = state["usage_stats"]

    store = await _workflow_store(request)
    pending_workflows = await store.pending_replacements(user)
    aliases_by_address = {alias.address.lower(): alias for alias in assigned_all}
    grouped_addresses: set[str] = set()
    groups: list[dict] = []

    for workflow in pending_workflows:
        members = []
        if workflow.old_address:
            old = aliases_by_address.get(workflow.old_address.lower())
            if old is not None:
                members.append(old)
                grouped_addresses.add(old.address.lower())
        new = aliases_by_address.get(workflow.new_address.lower())
        if new is not None:
            members.append(new)
            grouped_addresses.add(new.address.lower())
        if members:
            groups.append({"workflow": workflow, "aliases": members})

    groups.extend(
        {"workflow": None, "aliases": [alias]}
        for alias in assigned_all
        if alias.address.lower() not in grouped_addresses
    )

    def usage_total(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("received_count") or 0) + int(usage.get("sent_count") or 0)

    def last_used(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("last_used_at") or 0)

    def purpose(alias) -> tuple[str, str]:
        return ((alias.name or "").casefold(), alias.address.lower())

    def status_rank(alias) -> tuple[int, str, str]:
        address = alias.address.lower()
        if address in unexpected_aliases:
            rank = 2
        elif alias.active:
            rank = 1
        else:
            rank = 0
        purpose_key, address_key = purpose(alias)
        return (rank, purpose_key, address_key)

    def member_matches_status(alias) -> bool:
        if status_filter == "active":
            return alias.active
        if status_filter == "disabled":
            return not alias.active
        if status_filter == "unexpected":
            return alias.address.lower() in unexpected_aliases
        if status_filter == "unused":
            return alias.address.lower() in no_usage_evidence
        return True

    search_query = q.strip()
    needle = search_query.lower()
    filtered_groups = []
    for group in groups:
        members = group["aliases"]
        if not any(member_matches_status(alias) for alias in members):
            continue
        if needle and not any(
            needle in f"{alias.address} {alias.name} {alias.private_description}".lower()
            for alias in members
        ):
            continue
        filtered_groups.append(group)

    def group_key(group: dict):
        members = group["aliases"]
        if sort == "purpose":
            return min(purpose(alias) for alias in members)
        if sort == "status":
            return max(status_rank(alias) for alias in members)
        if sort == "usage":
            return (
                max(usage_total(alias) for alias in members),
                max(last_used(alias) for alias in members),
                min(purpose(alias) for alias in members),
            )
        if sort == "last_used":
            return (
                max(last_used(alias) for alias in members),
                max(usage_total(alias) for alias in members),
                min(purpose(alias) for alias in members),
            )
        return (
            max(1 if alias.address.lower() in unexpected_aliases else 0 for alias in members),
            max(last_used(alias) for alias in members),
            max(usage_total(alias) for alias in members),
            min(purpose(alias) for alias in members),
        )

    filtered_groups.sort(key=group_key, reverse=direction == "desc")
    pages = _group_pages(filtered_groups, per_page)
    total_pages = max(1, len(pages))
    page = min(page, total_pages)
    selected_groups = pages[page - 1] if pages else []
    assigned = [alias for group in selected_groups for alias in group["aliases"]]
    filtered_total = sum(len(group["aliases"]) for group in filtered_groups)
    preceding = sum(
        len(group["aliases"])
        for page_groups in pages[: page - 1]
        for group in page_groups
    )

    status_counts = {
        "all": len(assigned_all),
        "active": sum(alias.active for alias in assigned_all),
        "disabled": sum(not alias.active for alias in assigned_all),
        "unexpected": len(unexpected_aliases),
        "unused": len(no_usage_evidence),
    }
    workflow_rows: dict[str, dict[str, object]] = {}
    for workflow in pending_workflows:
        if workflow.old_address:
            workflow_rows[workflow.old_address.lower()] = {
                "id": workflow.id,
                "role": "old",
                "state": workflow.waiting_state,
            }
        workflow_rows[workflow.new_address.lower()] = {
            "id": workflow.id,
            "role": "new",
            "state": workflow.waiting_state,
        }

    state.update(
        {
            "assigned": assigned,
            "filtered_total": filtered_total,
            "search_query": search_query,
            "status_filter": status_filter,
            "status_counts": status_counts,
            "sort_mode": sort,
            "sort_direction": direction,
            "page": page,
            "per_page": per_page,
            "page_sizes": PAGE_SIZES,
            "total_pages": total_pages,
            "pagination_items": _pagination_items(page, total_pages),
            "range_start": preceding + 1 if filtered_total else 0,
            "range_end": preceding + len(assigned),
            "alias_workflow_rows": workflow_rows,
            "pending_replacements": [_workflow_payload(item) for item in pending_workflows],
        }
    )
    return TEMPLATES.TemplateResponse(
        request,
        "dashboard.html",
        _template_context(request, active_nav="aliases", **state),
    )


@router.get("/aliases/workflows")
async def list_alias_workflows(request: Request):
    user = require_user(request)
    store = await _workflow_store(request)
    pending = await store.pending_replacements(user)
    return {"pending": [_workflow_payload(workflow) for workflow in pending]}


@router.get("/aliases/workflows/{workflow_id}")
async def get_alias_workflow(request: Request, workflow_id: int):
    user = require_user(request)
    store = await _workflow_store(request)
    workflow = await store.get(user, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Alias workflow not found")
    return _workflow_payload(workflow)


@router.post("/aliases/workflows/{workflow_id}/stop")
async def stop_alias_workflow(
    request: Request,
    workflow_id: int,
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    store = await _workflow_store(request)
    workflow = await store.stop_waiting(user, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Alias workflow not found")
    return _workflow_payload(workflow)


@router.post("/aliases/workflows/{workflow_id}/resume")
async def resume_alias_workflow(
    request: Request,
    workflow_id: int,
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    store = await _workflow_store(request)
    workflow = await store.get(user, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=404, detail="Alias workflow not found")
    if workflow.completed_at is not None or workflow.new_mail_received_at is not None:
        return _workflow_payload(workflow)
    await asyncio.to_thread(
        _resume_waiting_sync,
        str(store.path),
        user,
        workflow_id,
    )
    resumed = await store.get(user, workflow_id)
    assert resumed is not None
    return _workflow_payload(resumed)


@router.post("/aliases/workflows/{workflow_id}/deactivation")
async def update_replacement_deactivation(
    request: Request,
    workflow_id: int,
    mode: str = Form(...),
    confirm_now: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if mode not in DEACTIVATION_MODES:
        raise HTTPException(status_code=400, detail="Unknown deactivation choice")

    store = await _workflow_store(request)
    workflow = await store.get(user, workflow_id)
    if workflow is None or not workflow.is_replacement:
        raise HTTPException(status_code=404, detail="Replacement workflow not found")
    if workflow.completed_at is not None:
        return _workflow_payload(workflow)
    if mode != DEACTIVATION_LATER and workflow.new_mail_received_at is None:
        raise HTTPException(
            status_code=409,
            detail="Wait until the new address has received its first message",
        )

    if mode == DEACTIVATION_NOW:
        if not confirm_now:
            raise HTTPException(status_code=400, detail="Immediate deactivation must be confirmed")
        if workflow.old_alias_id is None:
            raise HTTPException(status_code=409, detail="Previous alias is unavailable")
        try:
            await request.app.state.mailcow.set_active(workflow.old_alias_id, False)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        completed = await store.complete_replacement(user, workflow_id)
        if completed is None:
            raise HTTPException(status_code=404, detail="Replacement workflow not found")
        return _workflow_payload(completed)

    updated = await store.set_deactivation(user, workflow_id, mode)
    return _workflow_payload(updated)


@router.post("/aliases")
async def create_alias(
    request: Request,
    mode: str = Form(...),
    description: str = Form(...),
    private_description: str = Form(""),
    local_part: str = Form(""),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    name = description.strip()
    private_description = private_description.strip()
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(private_description) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")
    private_comment = update_private_comment("", description=private_description)

    try:
        if mode == "readable":
            address = await _create_unique_alias(
                request,
                user,
                lambda: readable_local_part(_language(request)),
                public_comment=name,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
        elif mode == "named":
            address = await _create_unique_alias(
                request,
                user,
                lambda: named_local_part(name),
                public_comment=name,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
        elif mode == "custom":
            address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
            await request.app.state.mailcow.create_alias(
                address,
                user,
                name,
                private_comment=private_comment,
                sogo_visible=sogo_visible,
            )
        else:
            raise HTTPException(status_code=400, detail="Unknown alias mode")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = int(time.time())
    store = await _workflow_store(request)
    workflow = await store.create_creation(
        mailbox=user,
        new_address=address,
        alias_name=name,
        alias_description=private_description,
        started_at=now,
        bypass_expires_at=now + request.app.state.settings.alias_workflow_bypass_seconds,
    )
    await _provision_now(request, workflow)

    if "application/json" in request.headers.get("accept", "").lower():
        return {
            "kind": "alias_creation",
            "state": "created",
            "address": address,
            "name": name,
            "description": private_description,
            "sogo_visible": sogo_visible,
            "workflow": _workflow_payload(workflow),
        }
    return RedirectResponse("/aliases", status_code=303)


@router.post("/aliases/{alias_id}/metadata")
async def update_metadata(
    request: Request,
    alias_id: int,
    description: str = Form(""),
    private_description: str | None = Form(None),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
    return_to: str = Form("/aliases"),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    alias = await request.app.state.mailcow.get_alias(alias_id)
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(status_code=403, detail="Alias cannot be edited here")

    name = description.strip()
    description_text = await _submitted_private_description(
        request,
        private_description,
        fallback=alias.private_description,
    )
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(description_text) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")

    private_comment = update_private_comment(
        alias.private_comment,
        description=description_text,
    )
    try:
        await request.app.state.mailcow.update_alias_preferences(
            alias_id,
            name,
            sogo_visible,
            private_comment=private_comment,
        )
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return RedirectResponse(_safe_return_to(return_to), status_code=303)


@router.post("/aliases/{alias_id}/description")
async def assign_reserved_alias_compatibility(
    request: Request,
    alias_id: int,
    description: str = Form(...),
    private_description: str | None = Form(None),
    sogo_visible: bool = Form(False),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    alias = await request.app.state.mailcow.get_alias(alias_id)
    if not is_owned_alias(alias, user) or not alias.is_reserved:
        raise HTTPException(status_code=409, detail="Alias is not reserved")

    name = description.strip()
    description_text = await _submitted_private_description(
        request,
        private_description,
        fallback=alias.private_description,
    )
    if not name or len(name) > 160:
        raise HTTPException(status_code=400, detail="Name must be 1-160 characters")
    if len(description_text) > 160:
        raise HTTPException(status_code=400, detail="Description must be at most 160 characters")
    private_comment = update_private_comment(
        alias.private_comment,
        description=description_text,
        remove_markers={RESERVED_MARKER, USED_RESERVED_MARKER},
    )
    await request.app.state.mailcow.assign_reserved_alias(
        alias_id,
        name,
        sogo_visible,
        private_comment=private_comment,
    )
    return RedirectResponse("/aliases", status_code=303)


@router.post("/aliases/{alias_id}/replace")
async def replace_alias(
    request: Request,
    alias_id: int,
    mode: str = Form("named"),
    local_part: str = Form(""),
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    alias = await request.app.state.mailcow.get_alias(alias_id)
    if (
        not is_owned_alias(alias, user)
        or alias.is_reserved
        or is_primary_mailbox_alias(alias, user)
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This alias cannot be replaced",
        )
    if mode not in {"named", "readable", "custom"}:
        raise HTTPException(status_code=400, detail="Unknown replacement mode")

    store = await _workflow_store(request)
    pending = await store.pending_replacements(user)
    existing = next((item for item in pending if item.old_alias_id == alias_id), None)
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "replacement_pending",
                "message": "A replacement is already in progress for this alias",
                "workflow": _workflow_payload(existing),
            },
        )

    replacement_name = alias.name or "alias"
    try:
        if mode == "named":
            new_address = await _create_unique_alias(
                request,
                user,
                lambda: named_local_part(replacement_name),
                public_comment=alias.public_comment,
                private_comment=alias.private_comment,
                sogo_visible=alias.sogo_visible,
            )
        elif mode == "readable":
            new_address = await _create_unique_alias(
                request,
                user,
                lambda: readable_local_part(_language(request)),
                public_comment=alias.public_comment,
                private_comment=alias.private_comment,
                sogo_visible=alias.sogo_visible,
            )
        else:
            new_address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
            await request.app.state.mailcow.create_alias(
                new_address,
                user,
                alias.public_comment,
                private_comment=alias.private_comment,
                sogo_visible=alias.sogo_visible,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except MailcowError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    now = int(time.time())
    try:
        workflow = await store.create_replacement(
            mailbox=user,
            old_alias_id=alias.id,
            old_address=alias.address,
            new_address=new_address,
            alias_name=alias.name,
            alias_description=alias.private_description,
            started_at=now,
            bypass_expires_at=now + request.app.state.settings.alias_workflow_bypass_seconds,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await _provision_now(request, workflow)

    return {
        "kind": "alias_replacement",
        "state": "created",
        "address": new_address,
        "old_address": alias.address,
        "name": alias.name,
        "description": alias.private_description,
        "workflow": _workflow_payload(workflow),
    }
