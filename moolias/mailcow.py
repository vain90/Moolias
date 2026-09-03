from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException, status

from moolias.aliases import (
    RESERVED_MARKER,
    USED_RESERVED_MARKER,
    AliasRecord,
    update_private_comment,
)
from moolias.config import Settings


class MailcowError(RuntimeError):
    pass


class MailcowAccessDenied(HTTPException):
    def __init__(self, access_tag: str) -> None:
        super().__init__(
            status_code=status.HTTP_303_SEE_OTHER,
            detail=(
                "Mailbox is not enabled for Moolias "
                f"(missing mailcow tag '{access_tag}')"
            ),
            headers={"Location": "/?error=access-denied"},
        )


class MailcowClient:
    def __init__(
        self,
        settings: Settings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.settings = settings
        self._client = httpx.AsyncClient(
            base_url=settings.mailcow_backend_url,
            headers={"X-API-Key": settings.mailcow_api_key, "Accept": "application/json"},
            verify=settings.mailcow_verify_tls,
            timeout=15.0,
            transport=transport,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        try:
            response = await self._client.request(method, path, **kwargs)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise MailcowError(f"mailcow API request failed: {exc}") from exc
        try:
            return response.json()
        except ValueError as exc:
            raise MailcowError("mailcow API returned invalid JSON") from exc

    @staticmethod
    def _ensure_success(payload: Any) -> None:
        entries = payload if isinstance(payload, list) else [payload]
        failures = [
            entry
            for entry in entries
            if isinstance(entry, dict) and entry.get("type") != "success"
        ]
        if failures:
            messages = [str(entry.get("msg", "unknown mailcow error")) for entry in failures]
            raise MailcowError("; ".join(messages))

    @staticmethod
    def _tags(payload: dict[str, Any]) -> set[str]:
        tags = payload.get("tags")
        if not isinstance(tags, list):
            return set()
        return {str(tag).strip().casefold() for tag in tags if str(tag).strip()}

    async def get_domain(self, domain: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/api/v1/get/domain/{quote(domain, safe='')}")
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict) or not payload:
            raise MailcowError("mailcow domain does not exist")
        return payload

    async def list_domains(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v1/get/domain/all")
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    async def list_mailboxes(self) -> list[dict[str, Any]]:
        payload = await self._request("GET", "/api/v1/get/mailbox/all")
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    async def get_rspamd_history(self, count: int) -> list[dict[str, Any]]:
        payload = await self._request("GET", f"/api/v1/get/logs/rspamd-history/{count}")
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    async def get_rspamd_history_range(self, start: int, end: int) -> list[dict[str, Any]]:
        if start < 0 or end < start:
            raise ValueError("invalid Rspamd history range")
        payload = await self._request(
            "GET",
            f"/api/v1/get/logs/rspamd-history/{start}-{end}",
        )
        if not isinstance(payload, list):
            return []
        return [item for item in payload if isinstance(item, dict)]

    async def _enforce_access_tag(self, email: str, mailbox: dict[str, Any]) -> None:
        configured_tag = self.settings.access_tag.strip().casefold()
        if not configured_tag:
            return
        if configured_tag in self._tags(mailbox):
            return

        domain = str(mailbox.get("domain") or email.rsplit("@", 1)[-1]).strip().lower()
        domain_details = await self.get_domain(domain)
        if configured_tag in self._tags(domain_details):
            return

        raise MailcowAccessDenied(self.settings.access_tag)

    async def list_aliases(self) -> list[AliasRecord]:
        payload = await self._request("GET", "/api/v1/get/alias/all")
        if not isinstance(payload, list):
            return []
        return [
            AliasRecord.from_mailcow(item)
            for item in payload
            if isinstance(item, dict) and "id" in item
        ]

    async def get_alias(self, alias_id: int) -> AliasRecord:
        payload = await self._request("GET", f"/api/v1/get/alias/{alias_id}")
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict) or "id" not in payload:
            raise MailcowError("Alias does not exist")
        return AliasRecord.from_mailcow(payload)

    async def get_mailbox(self, email: str) -> dict[str, Any]:
        payload = await self._request("GET", f"/api/v1/get/mailbox/{quote(email, safe='@')}")
        if isinstance(payload, list) and payload:
            payload = payload[0]
        if not isinstance(payload, dict) or not payload:
            raise MailcowError("Authenticated mailcow mailbox does not exist")
        await self._enforce_access_tag(email, payload)
        return payload

    async def set_mailbox_tags(self, email: str, tags: list[str]) -> None:
        mailbox = await self.get_mailbox(email)
        current_tags = mailbox.get("tags")
        current = (
            [str(tag).strip() for tag in current_tags if str(tag).strip()]
            if isinstance(current_tags, list)
            else []
        )
        desired = [str(tag).strip() for tag in tags if str(tag).strip()]
        current_folded = {tag.casefold() for tag in current}
        desired_folded = {tag.casefold() for tag in desired}
        removed = [tag for tag in current if tag.casefold() not in desired_folded]
        added = [tag for tag in desired if tag.casefold() not in current_folded]

        if removed:
            await self.delete_mailbox_tags(email, removed)

        if added:
            payload = await self._request(
                "POST",
                "/api/v1/edit/mailbox",
                json={
                    "items": [email],
                    "attr": {"tags": added},
                },
            )
            self._ensure_success(payload)

    async def delete_mailbox_tags(self, email: str, tags: list[str]) -> None:
        if not tags:
            return
        payload = await self._request(
            "POST",
            f"/api/v1/delete/mailbox/tag/{quote(email, safe='@')}",
            json=tags,
        )
        self._ensure_success(payload)

    async def create_alias(
        self,
        address: str,
        target: str,
        public_comment: str = "",
        *,
        private_comment: str = "",
        sogo_visible: bool = False,
    ) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/add/alias",
            json={
                "address": address,
                "goto": target,
                "active": 1,
                "internal": 0,
                "sender_allowed": 1,
                "sogo_visible": 1 if sogo_visible else 0,
                "goto_null": 0,
                "goto_spam": 0,
                "goto_ham": 0,
                "private_comment": private_comment,
                "public_comment": public_comment,
            },
        )
        self._ensure_success(payload)

    async def _safe_sogo_visibility(self, alias_id: int, requested: bool) -> bool:
        if not requested:
            return False
        alias = await self.get_alias(alias_id)
        return alias.sender_allowed is not False

    async def update_alias_preferences(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
        *,
        private_comment: str | None = None,
    ) -> None:
        sogo_visible = await self._safe_sogo_visibility(alias_id, sogo_visible)
        attributes: dict[str, Any] = {
            "public_comment": public_comment,
            "sogo_visible": 1 if sogo_visible else 0,
        }
        if private_comment is not None:
            attributes["private_comment"] = private_comment
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={"items": [str(alias_id)], "attr": attributes},
        )
        self._ensure_success(payload)

    async def assign_reserved_alias(
        self,
        alias_id: int,
        public_comment: str,
        sogo_visible: bool,
        *,
        private_comment: str = "",
    ) -> None:
        sogo_visible = await self._safe_sogo_visibility(alias_id, sogo_visible)
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id)],
                "attr": {
                    "private_comment": private_comment,
                    "public_comment": public_comment,
                    "sogo_visible": 1 if sogo_visible else 0,
                },
            },
        )
        self._ensure_success(payload)

    async def mark_reserved_alias_used(self, alias_id: int) -> None:
        alias = await self.get_alias(alias_id)
        private_comment = update_private_comment(
            alias.private_comment,
            add_markers={USED_RESERVED_MARKER},
            remove_markers={RESERVED_MARKER},
        )
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id)],
                "attr": {"private_comment": private_comment},
            },
        )
        self._ensure_success(payload)

    async def set_active(self, alias_id: int, active: bool) -> None:
        await self.set_active_many([alias_id], active)

    async def set_active_many(self, alias_ids: list[int], active: bool) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id) for alias_id in alias_ids],
                "attr": {"active": 1 if active else 0},
            },
        )
        self._ensure_success(payload)

    async def set_sogo_visible_many(self, alias_ids: list[int], visible: bool) -> None:
        if visible:
            requested_ids = set(alias_ids)
            aliases = await self.list_aliases()
            blocked = [
                alias.address
                for alias in aliases
                if alias.id in requested_ids and alias.sender_allowed is False
            ]
            if blocked:
                raise MailcowError(
                    "SOGo visibility is unavailable for aliases that cannot be used as senders"
                )
        payload = await self._request(
            "POST",
            "/api/v1/edit/alias",
            json={
                "items": [str(alias_id) for alias_id in alias_ids],
                "attr": {"sogo_visible": 1 if visible else 0},
            },
        )
        self._ensure_success(payload)

    async def delete_alias(self, alias_id: int) -> None:
        payload = await self._request(
            "POST",
            "/api/v1/delete/alias",
            data={"items": json.dumps([str(alias_id)])},
        )
        self._ensure_success(payload)
