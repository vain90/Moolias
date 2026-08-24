from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import secrets
import socket
import ssl
import time
from email.utils import parseaddr
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from moolias import __version__
from moolias.aliases import is_owned_alias
from moolias.newsletter_store import NewsletterObservation, NewsletterStore
from moolias.security import require_user, validate_csrf
from moolias.sender_protocol import (
    NONCE_HEADER,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    request_signature,
)
from moolias.ui import _load_ui_state, _template_context

LOGGER = logging.getLogger(__name__)
router = APIRouter()
TEMPLATES = Jinja2Templates(directory=str(Path(__file__).resolve().parent / "templates"))
CLEAN_ACTIONS = frozenset({"clean", "no action", "accept"})
AUTH_SYMBOLS = frozenset({"R_DKIM_ALLOW", "DMARC_POLICY_ALLOW"})
NEWSLETTER_SYMBOLS = frozenset({"MAILLIST", "HAS_LIST_UNSUB"})
MAX_UNSUBSCRIBE_URL_LENGTH = 8192
MAX_RESPONSE_HEADER_BYTES = 65536
MAX_HEADER_LOOKUPS_PER_SCAN = 50


class NewsletterAgentError(RuntimeError):
    pass


class NewsletterAgentMessageNotFound(NewsletterAgentError):
    pass


class NewsletterAgentClient:
    def __init__(
        self,
        base_url: str,
        secret: str,
        *,
        verify_tls: bool = True,
        timeout: float = 10.0,
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

    async def __aenter__(self) -> NewsletterAgentClient:
        return self

    async def __aexit__(self, *_args: object) -> None:
        await self.close()

    async def fetch_headers(self, mailbox: str, message_id: str) -> dict[str, Any]:
        path = "/v1/headers"
        body = json.dumps(
            {"mailbox": mailbox, "message_id": message_id},
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
            raise NewsletterAgentError("Newsletter agent is unavailable") from exc
        if response.status_code == 404:
            raise NewsletterAgentMessageNotFound("Message was not found")
        if response.status_code == 401:
            raise NewsletterAgentError("Newsletter agent authentication failed")
        if response.is_error:
            raise NewsletterAgentError(
                f"Newsletter agent returned HTTP {response.status_code}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise NewsletterAgentError("Newsletter agent returned invalid JSON") from exc
        if not isinstance(payload, dict):
            raise NewsletterAgentError("Newsletter agent returned invalid data")
        return payload


def _agent_url(settings: Any) -> str:
    configured = settings.newsletter_agent_url.strip()
    if configured:
        return configured.rstrip("/")
    return f"{settings.mailcow_url.rstrip('/')}/moolias-newsletter-agent"


def _normalise_symbol(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    for marker in ("(", "[", "{"):
        text = text.split(marker, 1)[0]
    return text.strip().upper()


def _symbols(item: dict[str, Any]) -> set[str]:
    value = item.get("symbols")
    if isinstance(value, dict):
        entries = value.keys()
    elif isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries = value.replace(",", " ").split()
    else:
        return set()
    return {symbol for entry in entries if (symbol := _normalise_symbol(entry))}


def _recipients(value: Any) -> set[str]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries = value.split(",")
    else:
        return set()
    return {str(entry).strip().casefold() for entry in entries if str(entry).strip()}


def _sender(item: dict[str, Any]) -> tuple[str, str]:
    raw = item.get("sender_mime") or item.get("sender_smtp") or ""
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    name, address = parseaddr(str(raw))
    return name.strip(), address.strip().casefold()


def _message_id(item: dict[str, Any]) -> str:
    return str(item.get("message-id") or item.get("message_id") or "").strip().strip("<>")


def _event_at(item: dict[str, Any]) -> int | None:
    try:
        return int(float(item.get("unix_time")))
    except (TypeError, ValueError):
        return None


def _normalise_list_id(value: str) -> str | None:
    value = value.strip()
    if not value:
        return None
    if "<" in value and ">" in value:
        value = value.split("<", 1)[1].split(">", 1)[0]
    value = value.strip().casefold()
    return value or None


def _unsubscribe_targets(value: str) -> tuple[str | None, str | None]:
    https_url: str | None = None
    mailto: str | None = None
    candidates: list[str] = []
    start = 0
    while True:
        left = value.find("<", start)
        if left < 0:
            break
        right = value.find(">", left + 1)
        if right < 0:
            break
        candidates.append(value[left + 1 : right].strip())
        start = right + 1
    if not candidates:
        candidates = [part.strip() for part in value.split(",") if part.strip()]

    for candidate in candidates:
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() == "https" and parsed.hostname and https_url is None:
            if len(candidate) <= MAX_UNSUBSCRIBE_URL_LENGTH and not any(
                char in candidate for char in "\x00\r\n"
            ):
                https_url = candidate
        elif parsed.scheme.casefold() == "mailto" and mailto is None:
            mailto = candidate
    return https_url, mailto


def _dkim_covers_one_click(signature: str) -> bool:
    signature = signature.replace("\r", " ").replace("\n", " ")
    lower = signature.casefold()
    position = 0
    while True:
        marker = lower.find("h=", position)
        if marker < 0:
            return False
        if marker > 0 and lower[marker - 1] not in "; \t":
            position = marker + 2
            continue
        end = lower.find(";", marker + 2)
        header_list = lower[marker + 2 : end if end >= 0 else len(lower)]
        signed = {part.strip() for part in header_list.split(":") if part.strip()}
        if {"list-unsubscribe", "list-unsubscribe-post"}.issubset(signed):
            return True
        if end < 0:
            return False
        position = end + 1


def _history_candidate(item: dict[str, Any]) -> bool:
    symbols = _symbols(item)
    action = str(item.get("action") or "").strip().casefold()
    return (
        bool(symbols & NEWSLETTER_SYMBOLS)
        and action in CLEAN_ACTIONS
        and bool(symbols & AUTH_SYMBOLS)
        and bool(_message_id(item))
        and _event_at(item) is not None
    )


class NewsletterCollector:
    def __init__(self, settings: Any, mailcow: Any, store: NewsletterStore) -> None:
        self.settings = settings
        self.mailcow = mailcow
        self.store = store
        self._tracked_mailboxes: set[str] = set()
        self._lock = asyncio.Lock()
        self.last_error: str | None = None
        self.last_success_at: int | None = None

    def track(self, mailbox: str) -> None:
        self._tracked_mailboxes.add(mailbox.casefold())

    async def run_forever(self) -> None:
        while True:
            for mailbox in sorted(self._tracked_mailboxes):
                try:
                    await self.scan_mailbox(mailbox)
                except Exception:
                    LOGGER.exception("Newsletter scan failed for %s", mailbox)
            await asyncio.sleep(self.settings.newsletter_poll_seconds)

    async def scan_mailbox(self, mailbox: str) -> None:
        mailbox = mailbox.casefold()
        self.track(mailbox)
        async with self._lock:
            aliases, history = await asyncio.gather(
                self.mailcow.list_aliases(),
                self.mailcow.get_rspamd_history(self.settings.newsletter_history_count),
            )
            owned_addresses = {mailbox}
            for alias in aliases:
                if is_owned_alias(alias, mailbox):
                    owned_addresses.add(alias.address.casefold())

            candidates: list[tuple[dict[str, Any], str]] = []
            for item in history:
                if not _history_candidate(item):
                    continue
                matching = sorted(_recipients(item.get("rcpt_smtp")) & owned_addresses)
                for recipient_alias in matching:
                    candidates.append((item, recipient_alias))
            candidates.sort(
                key=lambda candidate: _event_at(candidate[0]) or 0,
                reverse=True,
            )

            agent_error: str | None = None
            agent_available = True
            header_lookups = 0
            async with NewsletterAgentClient(
                _agent_url(self.settings),
                self.settings.newsletter_agent_secret,
                verify_tls=self.settings.mailcow_verify_tls,
            ) as agent:
                for item, recipient_alias in candidates:
                    can_lookup = (
                        agent_available
                        and header_lookups < MAX_HEADER_LOOKUPS_PER_SCAN
                    )
                    try:
                        lookup_performed = await self._record_candidate(
                            agent if can_lookup else None,
                            mailbox,
                            recipient_alias,
                            item,
                        )
                    except NewsletterAgentError as exc:
                        agent_error = str(exc)
                        agent_available = False
                        continue
                    if lookup_performed:
                        header_lookups += 1

            self.last_error = agent_error
            self.last_success_at = int(time.time())

    async def _record_candidate(
        self,
        agent: NewsletterAgentClient | None,
        mailbox: str,
        recipient_alias: str,
        item: dict[str, Any],
    ) -> bool:
        message_id = _message_id(item)
        event_at = _event_at(item)
        if not message_id or event_at is None:
            return False

        history_name, history_address = _sender(item)
        if not history_address or "@" not in history_address:
            return False

        # The Rspamd sender identity is available even when the original message has
        # already been deleted, so it is the stable grouping key for incremental scans.
        identity_key = f"sender:{history_address}"
        base_observation = NewsletterObservation(
            mailbox=mailbox,
            recipient_alias=recipient_alias,
            identity_key=identity_key,
            sender_name=history_name,
            sender_address=history_address,
            list_id=None,
            message_id=message_id,
            event_at=event_at,
        )
        await self.store.record(base_observation)

        if agent is None or await self.store.headers_checked(base_observation):
            return False

        try:
            headers = await agent.fetch_headers(mailbox, message_id)
        except NewsletterAgentMessageNotFound:
            await self.store.mark_headers_checked(base_observation)
            return True

        header_name, header_address = parseaddr(str(headers.get("from") or ""))
        sender_name = header_name.strip() or history_name
        sender_address = header_address.strip().casefold() or history_address
        if "@" not in sender_address:
            sender_address = history_address

        list_id = _normalise_list_id(str(headers.get("list_id") or ""))
        unsubscribe_url, mailto = _unsubscribe_targets(
            str(headers.get("list_unsubscribe") or "")
        )
        declared_one_click = (
            str(headers.get("list_unsubscribe_post") or "").strip().casefold()
            == "list-unsubscribe=one-click"
        )
        symbols = _symbols(item)
        one_click = bool(
            unsubscribe_url
            and declared_one_click
            and "R_DKIM_ALLOW" in symbols
            and _dkim_covers_one_click(str(headers.get("dkim_signature") or ""))
        )

        await self.store.record(
            NewsletterObservation(
                mailbox=mailbox,
                recipient_alias=recipient_alias,
                identity_key=identity_key,
                sender_name=sender_name,
                sender_address=sender_address,
                list_id=list_id,
                message_id=message_id,
                event_at=event_at,
                unsubscribe_url=unsubscribe_url,
                unsubscribe_mailto=mailto,
                one_click=one_click,
            )
        )
        await self.store.mark_headers_checked(base_observation)
        return True


_runtime_lock = asyncio.Lock()


async def _runtime(request: Request) -> tuple[NewsletterStore, NewsletterCollector]:
    app = request.app
    store = getattr(app.state, "newsletter_store", None)
    collector = getattr(app.state, "newsletter_collector", None)
    if store is not None and collector is not None:
        return store, collector

    async with _runtime_lock:
        store = getattr(app.state, "newsletter_store", None)
        collector = getattr(app.state, "newsletter_collector", None)
        if store is None:
            store = NewsletterStore(app.state.settings.newsletter_db_path)
            await store.initialize()
            app.state.newsletter_store = store
        if collector is None:
            collector = NewsletterCollector(app.state.settings, app.state.mailcow, store)
            app.state.newsletter_collector = collector
            app.state.newsletter_collector_task = asyncio.create_task(
                collector.run_forever(),
                name="moolias-newsletter-collector",
            )
    return store, collector


def _public_https_target(url: str) -> tuple[str, str, list[str]]:
    if len(url) > MAX_UNSUBSCRIBE_URL_LENGTH or any(char in url for char in "\x00\r\n"):
        raise ValueError("Invalid unsubscribe URL")
    parsed = urlsplit(url)
    if parsed.scheme.casefold() != "https" or not parsed.hostname:
        raise ValueError("Only HTTPS unsubscribe URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("Unsubscribe URL must not contain credentials")
    try:
        port = parsed.port or 443
    except ValueError as exc:
        raise ValueError("Invalid unsubscribe port") from exc
    if port != 443:
        raise ValueError("Only HTTPS port 443 is allowed")

    hostname = parsed.hostname.encode("idna").decode("ascii")
    target_path = quote(
        parsed.path or "/",
        safe="/%:@-._~!$&'()*+,;=",
    )
    if parsed.query:
        target_path += "?" + quote(parsed.query, safe="=&;%:@/?+,-._~!$'()*")

    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses:
        raise ValueError("Unsubscribe host did not resolve")

    parsed_addresses = [ipaddress.ip_address(address) for address in addresses]
    if any(not address.is_global for address in parsed_addresses):
        raise ValueError("Unsubscribe host resolves to a non-public address")
    return hostname, target_path, addresses


async def _one_click_post(url: str) -> int:
    hostname, target_path, addresses = await asyncio.to_thread(_public_https_target, url)
    body = b"List-Unsubscribe=One-Click"
    request_bytes = (
        f"POST {target_path} HTTP/1.1\r\n"
        f"Host: {hostname}\r\n"
        f"User-Agent: Moolias/{__version__}\r\n"
        "Content-Type: application/x-www-form-urlencoded\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii") + body
    context = ssl.create_default_context()
    last_error: Exception | None = None

    for address in addresses:
        writer = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    address,
                    443,
                    ssl=context,
                    server_hostname=hostname,
                ),
                timeout=7,
            )
            writer.write(request_bytes)
            await writer.drain()
            status_line = await asyncio.wait_for(reader.readline(), timeout=7)
            if len(status_line) > 4096:
                raise OSError("Unsubscribe response status is too large")
            parts = status_line.decode("iso-8859-1", errors="replace").strip().split()
            if len(parts) < 2 or not parts[0].startswith("HTTP/"):
                raise OSError("Invalid unsubscribe response")
            status_code = int(parts[1])

            header_bytes = len(status_line)
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=7)
                header_bytes += len(line)
                if header_bytes > MAX_RESPONSE_HEADER_BYTES:
                    raise OSError("Unsubscribe response headers are too large")
                if line in {b"\r\n", b"\n", b""}:
                    break
            if 200 <= status_code < 300:
                return status_code
            raise OSError(f"Unsubscribe endpoint returned HTTP {status_code}")
        except (OSError, TimeoutError, ssl.SSLError, ValueError) as exc:
            last_error = exc
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except OSError:
                    pass

    raise OSError(str(last_error or "Unsubscribe request failed"))


@router.get("/newsletters", response_class=HTMLResponse)
async def newsletters_page(request: Request):
    user = require_user(request)
    state = await _load_ui_state(request)
    settings = request.app.state.settings
    newsletters = []
    collector_error: str | None = None
    collector_last_success: int | None = None

    if settings.newsletter_management:
        store, collector = await _runtime(request)
        collector.track(user)
        try:
            await collector.scan_mailbox(user)
        except Exception as exc:
            LOGGER.warning("Immediate newsletter scan failed for %s: %s", user, exc)
        newsletters = await store.list_for_mailbox(user)
        collector_error = collector.last_error
        collector_last_success = collector.last_success_at

    return TEMPLATES.TemplateResponse(
        request,
        "newsletters.html",
        _template_context(
            request,
            active_nav="newsletters",
            newsletter_enabled=settings.newsletter_management,
            newsletters=newsletters,
            newsletter_collector_error=collector_error,
            newsletter_collector_last_success=collector_last_success,
            **state,
        ),
    )


@router.post("/newsletters/refresh")
async def refresh_newsletters(request: Request, csrf_token: str = Form(...)):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if not request.app.state.settings.newsletter_management:
        raise HTTPException(status_code=409, detail="Newsletter management is disabled")
    _, collector = await _runtime(request)
    await collector.scan_mailbox(user)
    return RedirectResponse("/newsletters", status_code=303)


@router.post("/newsletters/{newsletter_id}/unsubscribe")
async def unsubscribe_newsletter(
    request: Request,
    newsletter_id: int,
    csrf_token: str = Form(...),
):
    validate_csrf(request, csrf_token)
    user = require_user(request)
    if not request.app.state.settings.newsletter_management:
        raise HTTPException(status_code=409, detail="Newsletter management is disabled")
    store, _ = await _runtime(request)
    newsletter = await store.get(newsletter_id, user)
    if newsletter is None:
        raise HTTPException(status_code=404, detail="Newsletter does not exist")

    one_click_links = [link for link in newsletter.links if link.one_click]
    if not one_click_links:
        raise HTTPException(
            status_code=409,
            detail="This newsletter does not provide verified one-click unsubscribe",
        )

    for link in one_click_links:
        try:
            await _one_click_post(link.url)
        except (OSError, ValueError):
            continue
        await store.mark_unsubscribed(newsletter_id, user)
        return RedirectResponse("/newsletters?unsubscribed=1", status_code=303)

    return RedirectResponse("/newsletters?unsubscribe_error=1", status_code=303)