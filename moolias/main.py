from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from moolias import __version__
from moolias.access import AccessRevalidationMiddleware
from moolias.aliases import (
    RESERVED_COMMENT,
    is_mailbox_catch_all,
    is_owned_alias,
    is_primary_mailbox_alias,
    mailbox_domain,
    named_local_part,
    readable_local_part,
    validate_local_part,
)
from moolias.auth import OAuthError, authorization_url, exchange_code, validate_oauth_state
from moolias.config import Settings, get_settings
from moolias.i18n import (
    LANGUAGE_COOKIE,
    SUPPORTED_LANGUAGES,
    detect_language,
    translations,
)
from moolias.mailcow import MailcowAccessDenied, MailcowClient, MailcowError
from moolias.review_settings import AliasReviewSettingsStore
from moolias.review_settings import router as review_settings_router
from moolias.security import ensure_csrf_token, require_user, validate_csrf
from moolias.senders import sender_match_token
from moolias.stats import StatsStore
from moolias.stats_mode import (
    StatsMode,
    StatsModeSource,
    is_stats_mode_downgrade,
    replace_mailbox_stats_tags,
    resolve_stats_mode,
    selected_effective_mode,
)
from moolias.usage import UsageCollector, mailbox_stats_state

PACKAGE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(PACKAGE_DIR / "templates"))
PAGE_SIZES = (10, 25, 50, 100)
STATUS_FILTERS = ("all", "active", "disabled", "unexpected")
BULK_ACTIONS = {"enable", "disable", "sogo-on", "sogo-off"}
STATS_MODE_SELECTIONS = {"inherit", "off", "basic", "domain", "full"}
SENDER_DECISIONS = {"expected", "unexpected", "clear"}


def pagination_items(current_page: int, total_pages: int) -> list[int | None]:
    if total_pages <= 7:
        return list(range(1, total_pages + 1))

    visible = {1, total_pages}
    visible.update(
        page
        for page in range(current_page - 2, current_page + 3)
        if 1 <= page <= total_pages
    )

    items: list[int | None] = []
    previous = 0
    for page in sorted(visible):
        if previous and page - previous > 1:
            items.append(None)
        items.append(page)
        previous = page
    return items


def safe_return_to(value: str | None, fallback: str = "/aliases") -> str:
    if not value:
        return fallback
    parsed = urlsplit(value)
    if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
        return fallback
    if value.startswith("//"):
        return fallback
    return value


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        mailcow = MailcowClient(settings)
        app.state.mailcow = mailcow
        app.state.stats_store = None
        collector_task: asyncio.Task[None] | None = None
        try:
            if settings.usage_stats:
                store = StatsStore(settings.usage_db_path)
                await store.initialize()
                app.state.stats_store = store
                collector = UsageCollector(settings, mailcow, store)
                collector_task = asyncio.create_task(
                    collector.run_forever(),
                    name="moolias-usage-collector",
                )
            yield
        finally:
            if collector_task is not None:
                collector_task.cancel()
                with suppress(asyncio.CancelledError):
                    await collector_task
            await mailcow.close()

    app = FastAPI(title="Moolias", version=__version__, lifespan=lifespan)
    app.state.settings = settings
    app.include_router(review_settings_router)
    app.add_middleware(AccessRevalidationMiddleware)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        session_cookie="moolias_session",
        same_site="lax",
        https_only=settings.cookie_secure,
        max_age=60 * 60 * 12,
    )
    if settings.trusted_host_list != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
    app.mount("/static", StaticFiles(directory=str(PACKAGE_DIR / "static")), name="static")

    def ui_language(request: Request) -> str:
        return detect_language(
            request.cookies.get(LANGUAGE_COOKIE),
            request.headers.get("accept-language"),
        )

    def template_context(request: Request, **values):
        language = ui_language(request)
        return_to = request.url.path
        if request.url.query:
            return_to = f"{return_to}?{request.url.query}"
        return {
            "language": language,
            "t": translations(language),
            "return_to": return_to,
            "version": __version__,
            **values,
        }

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
            "form-action 'self'"
        )
        response.headers["Content-Language"] = ui_language(request)
        return response

    def client(request: Request) -> MailcowClient:
        return request.app.state.mailcow

    async def owned_alias(request: Request, alias_id: int):
        user = require_user(request)
        alias = await client(request).get_alias(alias_id)
        if not is_owned_alias(alias, user):
            raise HTTPException(status_code=403, detail="Alias is not owned by this mailbox")
        return user, alias

    async def create_unique_alias(
        request: Request,
        user: str,
        factory,
        public_comment: str = "",
        private_comment: str = "",
        sogo_visible: bool = False,
        attempts: int = 12,
    ) -> str:
        domain = mailbox_domain(user)
        last_error: Exception | None = None
        for _ in range(attempts):
            address = f"{validate_local_part(factory())}@{domain}"
            try:
                await client(request).create_alias(
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

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> str:
        return "ok\n"

    @app.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        if request.session.get("user_email"):
            return RedirectResponse("/overview", status_code=303)
        return TEMPLATES.TemplateResponse(
            request,
            "index.html",
            template_context(request),
        )

    @app.get("/language/{language}")
    async def set_language(
        request: Request,
        language: str,
        next_url: str = Query(default="/", alias="next"),
    ):
        if language not in SUPPORTED_LANGUAGES:
            raise HTTPException(status_code=404, detail="Unsupported language")
        target = safe_return_to(next_url, fallback="/")
        response = RedirectResponse(target, status_code=303)
        response.set_cookie(
            LANGUAGE_COOKIE,
            language,
            max_age=365 * 24 * 60 * 60,
            secure=settings.cookie_secure,
            httponly=True,
            samesite="lax",
            path="/",
        )
        return response

    @app.get("/login")
    async def login(request: Request):
        return RedirectResponse(authorization_url(request, settings), status_code=302)

    @app.get("/oauth/callback")
    async def oauth_callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
    ):
        validate_oauth_state(request, state)
        if not code:
            raise HTTPException(status_code=400, detail="Missing OAuth code")
        try:
            profile = await exchange_code(settings, code)
            email = str(profile.get("email") or profile.get("username") or "").strip().lower()
            if not email:
                raise OAuthError("mailcow profile does not contain a mailbox address")
            mailbox = await client(request).get_mailbox(email)
            mailbox_username = str(mailbox.get("username") or email).lower()
            if mailbox_username != email:
                raise OAuthError("mailcow profile and API mailbox do not match")
        except MailcowAccessDenied:
            request.session.clear()
            return RedirectResponse("/?error=access-denied", status_code=303)
        except (OAuthError, MailcowError) as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        request.session.clear()
        request.session["user_email"] = email
        ensure_csrf_token(request)
        return RedirectResponse("/overview", status_code=303)

    @app.post("/logout")
    async def logout(request: Request, csrf_token: str = Form(...)):
        validate_csrf(request, csrf_token)
        request.session.clear()
        return RedirectResponse("/", status_code=303)

    @app.get("/aliases", response_class=HTMLResponse)
    async def aliases_dashboard(
        request: Request,
        q: str = Query(default="", max_length=160),
        page: int = Query(default=1, ge=1),
        per_page: int = Query(default=25),
        status_filter: str = Query(default="all", alias="status"),
    ):
        user = require_user(request)
        domain = mailbox_domain(user)
        if per_page not in PAGE_SIZES:
            per_page = 25
        if status_filter not in STATUS_FILTERS:
            status_filter = "all"

        try:
            all_aliases = await client(request).list_aliases()
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        primary_alias = next(
            (alias for alias in all_aliases if is_primary_mailbox_alias(alias, user)),
            None,
        )
        catch_all = next(
            (alias for alias in all_aliases if is_mailbox_catch_all(alias, user)),
            None,
        )
        owned = [
            alias
            for alias in all_aliases
            if is_owned_alias(alias, user)
            and (primary_alias is None or alias.id != primary_alias.id)
        ]
        reserved = sorted(
            (alias for alias in owned if alias.is_reserved),
            key=lambda item: item.address,
        )
        assigned_all = sorted(
            (alias for alias in owned if not alias.is_reserved),
            key=lambda item: (item.description.lower(), item.address),
        )

        stats_store = request.app.state.stats_store
        stats_available = settings.usage_stats and stats_store is not None
        stats_state = None
        stats_error = False
        stats_mode_selection = "inherit"
        stats_confirmation_mode: str | None = None
        usage_stats_visible = False
        usage_stats: dict[str, dict[str, int | None]] = {}
        sender_stats: dict[
            str,
            list[dict[str, str | int | bool | None]],
        ] = {}
        unexpected_aliases: set[str] = set()

        if stats_available:
            try:
                stats_state = await mailbox_stats_state(settings, client(request), user)
                usage_stats_visible = stats_state.enabled
                if (
                    stats_state.conflict
                    and stats_state.conflict_source is StatsModeSource.MAILBOX
                ):
                    stats_mode_selection = "conflict"
                elif stats_state.mailbox_override is not None:
                    stats_mode_selection = stats_state.mailbox_override.value

                stored_mode = await stats_store.sender_mode(user)
                stats_confirmation_mode = stored_mode or stats_state.effective.value
                if not stats_state.conflict:
                    await stats_store.sync_sender_modes({user: stats_state.effective.value})
            except (MailcowAccessDenied, MailcowError):
                stats_error = True
                stats_state = None
                usage_stats_visible = False

            if (
                usage_stats_visible
                and stats_state is not None
                and stats_state.sender_detail_enabled
            ):
                sender_aliases = [*assigned_all, *reserved]
                sender_addresses = [alias.address for alias in sender_aliases]
                stored_senders = await stats_store.sender_usage(user, sender_addresses)
                aliases_by_address = {
                    alias.address.lower(): alias for alias in sender_aliases
                }
                for alias_address, entries in stored_senders.items():
                    alias_record = aliases_by_address.get(alias_address)
                    if alias_record is None:
                        continue
                    rows: list[dict[str, str | int | bool | None]] = []
                    for entry in entries:
                        match_token = sender_match_token(
                            alias_record.address,
                            alias_record.description,
                            entry.sender_domain,
                        )
                        automatic_expected = match_token is not None
                        if entry.manual_expected is None:
                            expected = automatic_expected
                            review_source = (
                                "automatic" if automatic_expected else "unreviewed"
                            )
                        elif entry.manual_expected:
                            expected = True
                            review_source = "manual"
                        else:
                            expected = False
                            review_source = "manual-unexpected"

                        rows.append(
                            {
                                "sender_key": entry.sender_key,
                                "label": entry.sender_address or entry.sender_domain,
                                "domain": entry.sender_domain,
                                "received_count": entry.received_count,
                                "last_received_at": entry.last_received_at,
                                "expected": expected,
                                "review_source": review_source,
                                "manual_expected": entry.manual_expected,
                                "match_token": match_token,
                            }
                        )

                    rows.sort(
                        key=lambda row: (
                            bool(row["expected"]),
                            -int(row["last_received_at"] or 0),
                            str(row["label"]),
                        )
                    )
                    sender_stats[alias_address] = rows

                ignored_aliases = await AliasReviewSettingsStore(
                    stats_store.path
                ).ignored_aliases(user)
                assigned_addresses = {
                    alias.address.lower() for alias in assigned_all if alias.active
                }
                unexpected_aliases = {
                    alias_address
                    for alias_address, rows in sender_stats.items()
                    if alias_address in assigned_addresses
                    and alias_address not in ignored_aliases
                    and any(not bool(row["expected"]) for row in rows)
                }

        status_counts = {
            "all": len(assigned_all),
            "active": sum(alias.active for alias in assigned_all),
            "disabled": sum(not alias.active for alias in assigned_all),
            "unexpected": len(unexpected_aliases),
        }

        if status_filter == "active":
            assigned_filtered = [alias for alias in assigned_all if alias.active]
        elif status_filter == "disabled":
            assigned_filtered = [alias for alias in assigned_all if not alias.active]
        elif status_filter == "unexpected":
            assigned_filtered = [
                alias
                for alias in assigned_all
                if alias.address.lower() in unexpected_aliases
            ]
        else:
            assigned_filtered = assigned_all

        search_query = q.strip()
        if search_query:
            needle = search_query.lower()
            assigned_filtered = [
                alias
                for alias in assigned_filtered
                if needle in f"{alias.address} {alias.public_comment}".lower()
            ]

        filtered_total = len(assigned_filtered)
        total_pages = max(1, (filtered_total + per_page - 1) // per_page)
        page = min(page, total_pages)
        offset = (page - 1) * per_page
        assigned = assigned_filtered[offset : offset + per_page]
        range_start = offset + 1 if filtered_total else 0
        range_end = min(offset + per_page, filtered_total)

        if usage_stats_visible and stats_state is not None:
            displayed_aliases = [*assigned, *reserved]
            addresses = [alias.address for alias in displayed_aliases]
            stored_usage = await stats_store.alias_usage(user, addresses)
            for alias in displayed_aliases:
                usage = stored_usage.get(alias.address.lower())
                received_count = usage.received_count if usage is not None else 0
                sent_count = usage.sent_count if usage is not None else 0
                timestamps = (
                    []
                    if usage is None
                    else [
                        value
                        for value in (usage.last_received_at, usage.last_sent_at)
                        if value is not None
                    ]
                )
                usage_stats[alias.address.lower()] = {
                    "received_count": received_count,
                    "sent_count": sent_count,
                    "last_used_at": max(timestamps) if timestamps else None,
                }

        return TEMPLATES.TemplateResponse(
            request,
            "dashboard.html",
            template_context(
                request,
                user=user,
                domain=domain,
                catch_all=catch_all,
                assigned=assigned,
                assigned_total=len(assigned_all),
                filtered_total=filtered_total,
                reserved=reserved,
                csrf_token=ensure_csrf_token(request),
                search_query=search_query,
                status_filter=status_filter,
                status_counts=status_counts,
                page=page,
                per_page=per_page,
                page_sizes=PAGE_SIZES,
                total_pages=total_pages,
                pagination_items=pagination_items(page, total_pages),
                range_start=range_start,
                range_end=range_end,
                stats_available=stats_available,
                stats_error=stats_error,
                stats_state=stats_state,
                stats_mode_selection=stats_mode_selection,
                stats_confirmation_mode=stats_confirmation_mode,
                usage_stats_visible=usage_stats_visible,
                usage_stats=usage_stats,
                sender_stats=sender_stats,
            ),
        )

    @app.post("/aliases/stats-mode")
    async def update_stats_mode(
        request: Request,
        mode: str = Form(...),
        csrf_token: str = Form(...),
        return_to: str = Form("/aliases"),
        confirm_downgrade: bool = Form(False),
    ):
        validate_csrf(request, csrf_token)
        user = require_user(request)
        stats_store = request.app.state.stats_store
        if not settings.usage_stats or stats_store is None:
            raise HTTPException(status_code=409, detail="Usage statistics are disabled")
        if mode not in STATS_MODE_SELECTIONS:
            raise HTTPException(status_code=400, detail="Unknown statistics mode")

        try:
            mailbox = await client(request).get_mailbox(user)
            domain_name = str(
                mailbox.get("domain") or user.rsplit("@", 1)[-1]
            ).strip().lower()
            domain_details = await client(request).get_domain(domain_name)
            current_state = resolve_stats_mode(
                mailbox.get("tags"),
                domain_details.get("tags"),
                settings.usage_tag,
            )
            target_mode = selected_effective_mode(mode, current_state.domain_default)
            stored_mode = await stats_store.sender_mode(user)
            confirmation_mode = (
                StatsMode(stored_mode) if stored_mode is not None else current_state.effective
            )
            if (
                is_stats_mode_downgrade(confirmation_mode, target_mode)
                and not confirm_downgrade
            ):
                raise HTTPException(
                    status_code=409,
                    detail="Statistics downgrade requires confirmation",
                )

            tags = replace_mailbox_stats_tags(
                mailbox.get("tags"),
                settings.usage_tag,
                mode,
            )
            await client(request).set_mailbox_tags(user, tags)
            state = await mailbox_stats_state(settings, client(request), user)
            await stats_store.sync_sender_modes({user: state.effective.value})
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return RedirectResponse(safe_return_to(return_to), status_code=303)

    @app.post("/aliases/{alias_id}/sender-expectation")
    async def update_sender_expectation(
        request: Request,
        alias_id: int,
        sender_key: str = Form(...),
        decision: str = Form(...),
        csrf_token: str = Form(...),
        return_to: str = Form("/aliases"),
    ):
        validate_csrf(request, csrf_token)
        user, alias = await owned_alias(request, alias_id)
        stats_store = request.app.state.stats_store
        if not settings.usage_stats or stats_store is None:
            raise HTTPException(status_code=409, detail="Usage statistics are disabled")
        if alias.is_reserved or is_primary_mailbox_alias(alias, user):
            raise HTTPException(status_code=409, detail="Sender review is unavailable here")
        if decision not in SENDER_DECISIONS:
            raise HTTPException(status_code=400, detail="Unknown sender review decision")

        sender_key = sender_key.strip().lower()
        if not sender_key or len(sender_key) > 320:
            raise HTTPException(status_code=400, detail="Invalid sender key")

        try:
            state = await mailbox_stats_state(settings, client(request), user)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if not state.sender_detail_enabled:
            raise HTTPException(
                status_code=409,
                detail="Sender statistics are not enabled for this mailbox",
            )

        stored = await stats_store.sender_usage(user, [alias.address])
        sender_entries = stored.get(alias.address.lower(), [])
        if not any(entry.sender_key == sender_key for entry in sender_entries):
            raise HTTPException(status_code=404, detail="Sender statistic does not exist")

        expected = {
            "expected": True,
            "unexpected": False,
            "clear": None,
        }[decision]
        await stats_store.set_sender_expectation(
            user,
            alias.address,
            sender_key,
            expected,
        )
        return RedirectResponse(safe_return_to(return_to), status_code=303)

    @app.post("/aliases")
    async def create_alias(
        request: Request,
        mode: str = Form(...),
        description: str = Form(...),
        local_part: str = Form(""),
        sogo_visible: bool = Form(False),
        csrf_token: str = Form(...),
    ):
        validate_csrf(request, csrf_token)
        user = require_user(request)
        description = description.strip()
        if not description or len(description) > 160:
            raise HTTPException(
                status_code=400,
                detail="Purpose must be 1-160 characters",
            )
        try:
            if mode == "readable":
                await create_unique_alias(
                    request,
                    user,
                    lambda: readable_local_part(ui_language(request)),
                    public_comment=description,
                    sogo_visible=sogo_visible,
                )
            elif mode == "named":
                await create_unique_alias(
                    request,
                    user,
                    lambda: named_local_part(description),
                    public_comment=description,
                    sogo_visible=sogo_visible,
                )
            elif mode == "custom":
                address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
                await client(request).create_alias(
                    address,
                    user,
                    description,
                    sogo_visible=sogo_visible,
                )
            else:
                raise HTTPException(status_code=400, detail="Unknown alias mode")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases", status_code=303)

    @app.post("/aliases/pool")
    async def create_pool(
        request: Request,
        count: int = Form(...),
        csrf_token: str = Form(...),
    ):
        validate_csrf(request, csrf_token)
        user = require_user(request)
        if count not in {1, 5, 10}:
            raise HTTPException(status_code=400, detail="Pool size must be 1, 5 or 10")
        try:
            for _ in range(count):
                await create_unique_alias(
                    request,
                    user,
                    lambda: readable_local_part(ui_language(request)),
                    private_comment=RESERVED_COMMENT,
                    sogo_visible=False,
                )
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases#pool", status_code=303)

    @app.get("/aliases/pool.txt", response_class=PlainTextResponse)
    async def export_pool(request: Request):
        user = require_user(request)
        aliases = await client(request).list_aliases()
        reserved_aliases = [
            alias
            for alias in aliases
            if is_owned_alias(alias, user) and alias.is_reserved and alias.active
        ]
        used_addresses = {
            alias.address.lower() for alias in reserved_aliases if alias.is_reserved_used
        }

        stats_store = request.app.state.stats_store
        if stats_store is not None and reserved_aliases:
            stored_usage = await stats_store.alias_usage(
                user,
                [alias.address for alias in reserved_aliases],
            )
            used_addresses.update(
                address.lower()
                for address, usage in stored_usage.items()
                if usage.received_count > 0 or usage.sent_count > 0
            )

        available = sorted(
            alias.address
            for alias in reserved_aliases
            if alias.address.lower() not in used_addresses
        )
        return PlainTextResponse("\n".join(available) + ("\n" if available else ""))

    @app.post("/aliases/bulk", response_class=PlainTextResponse)
    async def bulk_aliases(
        request: Request,
        action: str = Form(...),
        alias_ids: list[int] = Form(...),
        csrf_token: str = Form(...),
    ):
        validate_csrf(request, csrf_token)
        user = require_user(request)
        if action not in BULK_ACTIONS:
            raise HTTPException(status_code=400, detail="Unknown bulk action")

        selected_ids = list(dict.fromkeys(alias_ids))
        if not selected_ids or len(selected_ids) > 100:
            raise HTTPException(status_code=400, detail="Select between 1 and 100 aliases")

        try:
            aliases = await client(request).list_aliases()
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

        selected_ids = [alias.id for alias in selected]
        try:
            if action == "enable":
                await client(request).set_active_many(selected_ids, True)
            elif action == "disable":
                await client(request).set_active_many(selected_ids, False)
            elif action == "sogo-on":
                await client(request).set_sogo_visible_many(selected_ids, True)
            else:
                await client(request).set_sogo_visible_many(selected_ids, False)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        return PlainTextResponse("ok\n")

    @app.post("/aliases/{alias_id}/replace")
    async def replace_alias(
        request: Request,
        alias_id: int,
        mode: str = Form("named"),
        local_part: str = Form(""),
        csrf_token: str = Form(...),
    ):
        validate_csrf(request, csrf_token)
        user, alias = await owned_alias(request, alias_id)
        if alias.is_reserved or is_primary_mailbox_alias(alias, user):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="This alias cannot be replaced",
            )
        if mode not in {"named", "readable", "custom"}:
            raise HTTPException(status_code=400, detail="Unknown replacement mode")

        replacement_name = alias.description.strip() or "alias"
        try:
            if mode == "named":
                new_address = await create_unique_alias(
                    request,
                    user,
                    lambda: named_local_part(replacement_name),
                    public_comment=alias.public_comment,
                    sogo_visible=alias.sogo_visible,
                )
            elif mode == "readable":
                new_address = await create_unique_alias(
                    request,
                    user,
                    lambda: readable_local_part(ui_language(request)),
                    public_comment=alias.public_comment,
                    sogo_visible=alias.sogo_visible,
                )
            else:
                new_address = f"{validate_local_part(local_part)}@{mailbox_domain(user)}"
                await client(request).create_alias(
                    new_address,
                    user,
                    alias.public_comment,
                    sogo_visible=alias.sogo_visible,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        try:
            await client(request).set_active(alias_id, False)
        except MailcowError as exc:
            raise HTTPException(
                status_code=502,
                detail={
                    "code": "partial_replacement",
                    "message": (
                        "The replacement alias was created, but the old alias could not be disabled"
                    ),
                    "address": new_address,
                },
            ) from exc

        return {
            "address": new_address,
            "old_address": alias.address,
        }

    @app.post("/aliases/{alias_id}/description")
    async def assign_reserved_alias(
        request: Request,
        alias_id: int,
        description: str = Form(...),
        sogo_visible: bool = Form(False),
        csrf_token: str = Form(...),
    ):
        validate_csrf(request, csrf_token)
        _, alias = await owned_alias(request, alias_id)
        if not alias.is_reserved:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only unused offline aliases can be assigned",
            )
        description = description.strip()
        if not description or len(description) > 160:
            raise HTTPException(
                status_code=400,
                detail="Purpose must be 1-160 characters",
            )
        try:
            await client(request).assign_reserved_alias(
                alias_id,
                description,
                sogo_visible,
            )
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases", status_code=303)

    @app.post("/aliases/{alias_id}/metadata")
    async def update_metadata(
        request: Request,
        alias_id: int,
        description: str = Form(""),
        sogo_visible: bool = Form(False),
        csrf_token: str = Form(...),
        return_to: str = Form("/aliases"),
    ):
        validate_csrf(request, csrf_token)
        _, alias = await owned_alias(request, alias_id)
        if alias.is_reserved:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Assign the offline alias before editing it",
            )
        description = description.strip()
        if len(description) > 160:
            raise HTTPException(
                status_code=400,
                detail="Purpose must be at most 160 characters",
            )
        try:
            await client(request).update_alias_preferences(
                alias_id,
                description,
                sogo_visible,
            )
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(safe_return_to(return_to), status_code=303)

    @app.post("/aliases/{alias_id}/toggle")
    async def toggle_alias(
        request: Request,
        alias_id: int,
        csrf_token: str = Form(...),
        return_to: str = Form("/aliases"),
    ):
        validate_csrf(request, csrf_token)
        _, alias = await owned_alias(request, alias_id)
        try:
            await client(request).set_active(alias_id, not alias.active)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse(safe_return_to(return_to), status_code=303)

    @app.post("/aliases/{alias_id}/delete-reserved")
    async def delete_reserved_alias(
        request: Request,
        alias_id: int,
        csrf_token: str = Form(...),
    ):
        validate_csrf(request, csrf_token)
        user, alias = await owned_alias(request, alias_id)
        if not alias.is_reserved:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Only unused offline aliases can be deleted",
            )
        if alias.is_reserved_used:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Used offline aliases must be assigned before they can be deleted",
            )

        stats_store = request.app.state.stats_store
        if stats_store is not None:
            stored_usage = await stats_store.alias_usage(user, [alias.address])
            usage = stored_usage.get(alias.address.lower())
            if usage is not None and (usage.received_count > 0 or usage.sent_count > 0):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Used offline aliases must be assigned before they can be deleted",
                )

        try:
            await client(request).delete_alias(alias_id)
        except MailcowError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return RedirectResponse("/aliases#pool", status_code=303)

    return app


app = create_app()
