from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
from collections.abc import Callable, Mapping
from email.utils import parseaddr
from typing import Any

from moolias.alias_delivery_agent import AliasDeliveryAgentClient, AliasDeliveryAgentError
from moolias.alias_workflows import AliasWorkflow, AliasWorkflowStore
from moolias.config import Settings
from moolias.mailcow import MailcowClient, MailcowError
from moolias.stats import StatsStore
from moolias.stats_mode import StatsMode
from moolias.usage import ACCEPTED_ACTIONS, mailbox_stats_state

LOGGER = logging.getLogger(__name__)
HISTORY_PROBE_SIZES = (10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000)


def _event_timestamp(item: Mapping[str, Any]) -> int | None:
    try:
        return int(float(item.get("unix_time")))
    except (TypeError, ValueError):
        return None


def _event_recipients(item: Mapping[str, Any]) -> set[str]:
    value = item.get("rcpt_smtp")
    if isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries = value.split(",")
    else:
        return set()
    return {str(entry).strip().lower() for entry in entries if str(entry).strip()}


def _sender_identity(item: Mapping[str, Any]) -> tuple[str, str] | None:
    raw = item.get("sender_mime") or item.get("sender_smtp")
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    _, address = parseaddr(str(raw or ""))
    address = address.strip().lower()
    if "@" not in address:
        return None
    local_part, domain = address.rsplit("@", 1)
    domain = domain.strip().strip(".").lower()
    if not local_part or not domain:
        return None
    return address, domain


def accepted_delivery_metadata(
    history: list[Mapping[str, Any]],
    *,
    recipients: set[str],
    earliest_at: int,
) -> list[tuple[str, int]]:
    deliveries: set[tuple[str, int]] = set()
    for item in history:
        action = str(item.get("action") or "").strip().lower()
        if action not in ACCEPTED_ACTIONS:
            continue
        event_at = _event_timestamp(item)
        if event_at is None or event_at < earliest_at:
            continue
        for recipient in _event_recipients(item) & recipients:
            deliveries.add((recipient, event_at))
    return sorted(deliveries, key=lambda item: item[1])


def accepted_delivery_senders(
    history: list[Mapping[str, Any]],
    *,
    recipients: set[str],
    earliest_at: int,
) -> list[tuple[str, int, str, str]]:
    deliveries: set[tuple[str, int, str, str]] = set()
    for item in history:
        action = str(item.get("action") or "").strip().lower()
        if action not in ACCEPTED_ACTIONS:
            continue
        event_at = _event_timestamp(item)
        if event_at is None or event_at < earliest_at:
            continue
        sender = _sender_identity(item)
        if sender is None:
            continue
        sender_address, sender_domain = sender
        for recipient in _event_recipients(item) & recipients:
            deliveries.add((recipient, event_at, sender_address, sender_domain))
    return sorted(deliveries, key=lambda item: item[1])


class AliasWorkflowCoordinator:
    def __init__(
        self,
        settings: Settings,
        mailcow: MailcowClient,
        store: AliasWorkflowStore,
        agent: AliasDeliveryAgentClient | None,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.mailcow = mailcow
        self.store = store
        self.agent = agent
        self.clock = clock
        self.stats_store = StatsStore(settings.usage_db_path) if settings.usage_stats else None

    async def close(self) -> None:
        if self.agent is not None:
            await self.agent.close()

    async def run_forever(self) -> None:
        while True:
            try:
                await self.reconcile_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Alias workflow reconciliation failed")
            await asyncio.sleep(self.settings.alias_workflow_poll_seconds)

    async def provision_workflow(self, workflow: AliasWorkflow) -> bool:
        if workflow.bypass_cleared_at is not None:
            return True
        if workflow.bypass_expires_at <= int(self.clock()):
            return True
        if self.agent is None:
            return False
        try:
            await self.agent.set_bypass(
                workflow.bypass_recipients,
                workflow.bypass_expires_at,
            )
        except AliasDeliveryAgentError:
            LOGGER.warning(
                "Could not provision first-mail delivery bypass for workflow %s",
                workflow.id,
            )
            return False
        await self.store.mark_bypass_provisioned(workflow.id, now=int(self.clock()))
        return True

    async def clear_workflow_bypass(self, workflow: AliasWorkflow) -> bool:
        if self.agent is None:
            return False
        try:
            await self.agent.clear_bypass(workflow.bypass_recipients)
        except AliasDeliveryAgentError:
            LOGGER.warning(
                "Could not clear first-mail delivery bypass for workflow %s",
                workflow.id,
            )
            return False
        await self.store.mark_bypass_cleared(workflow.id, now=int(self.clock()))
        return True

    async def reconcile_once(self) -> None:
        now = int(self.clock())
        if self.agent is not None:
            for workflow in await self.store.bypass_provisioning_due(now=now):
                await self.provision_workflow(workflow)

        monitoring_cutoff = now - self.settings.alias_replacement_monitoring_max_days * 86400
        await self.store.stop_replacement_monitoring_before(
            before=monitoring_cutoff,
            now=now,
        )

        watchers = await self.store.active_watchers()
        if watchers:
            await self._scan_delivery_history(watchers)

        if self.agent is not None:
            for workflow in await self.store.bypass_clear_due():
                await self.clear_workflow_bypass(workflow)

        for workflow in await self.store.due_deactivations(now=now):
            if workflow.old_alias_id is None:
                continue
            try:
                await self.mailcow.set_active(workflow.old_alias_id, False)
            except MailcowError:
                LOGGER.warning(
                    "Could not run scheduled alias deactivation for workflow %s",
                    workflow.id,
                )
                continue
            await self.store.complete_replacement(
                workflow.mailbox,
                workflow.id,
                now=now,
            )

        await self.store.cleanup(before=now - 7 * 86400)

    def _set_sender_expected_if_unset(
        self,
        mailbox: str,
        alias: str,
        sender_key: str,
    ) -> None:
        if self.stats_store is None:
            return
        with sqlite3.connect(self.stats_store.path, timeout=10) as connection:
            connection.execute("PRAGMA busy_timeout = 5000")
            connection.execute(
                """
                INSERT OR IGNORE INTO sender_expectations (
                    mailbox,
                    alias,
                    sender_key,
                    expected
                ) VALUES (?, ?, ?, 1)
                """,
                (mailbox.lower(), alias.lower(), sender_key.lower()),
            )

    async def _learn_first_mail_senders(
        self,
        watchers: list[AliasWorkflow],
        sender_deliveries: list[tuple[str, int, str, str]],
    ) -> None:
        if self.stats_store is None or not sender_deliveries:
            return

        mode_by_mailbox: dict[str, StatsMode | None] = {}
        for workflow in watchers:
            mailbox = workflow.mailbox.lower()
            if mailbox not in mode_by_mailbox:
                try:
                    state = await mailbox_stats_state(self.settings, self.mailcow, mailbox)
                except MailcowError:
                    LOGGER.warning(
                        "Could not resolve sender-detail mode for alias workflow %s",
                        workflow.id,
                    )
                    mode_by_mailbox[mailbox] = None
                else:
                    mode_by_mailbox[mailbox] = (
                        state.effective
                        if not state.conflict
                        and state.effective in {StatsMode.DOMAIN, StatsMode.FULL}
                        else None
                    )

            mode = mode_by_mailbox[mailbox]
            if mode is None:
                continue

            pending_recipients: list[str] = []
            if workflow.old_address and workflow.old_mail_received_at is None:
                pending_recipients.append(workflow.old_address.lower())
            if workflow.new_mail_received_at is None:
                pending_recipients.append(workflow.new_address.lower())

            for recipient in pending_recipients:
                delivery = next(
                    (
                        item
                        for item in sender_deliveries
                        if item[0] == recipient and workflow.started_at <= item[1]
                    ),
                    None,
                )
                if delivery is None:
                    continue
                _, _, sender_address, sender_domain = delivery
                sender_key = sender_address if mode is StatsMode.FULL else sender_domain
                try:
                    await asyncio.to_thread(
                        self._set_sender_expected_if_unset,
                        workflow.mailbox,
                        recipient,
                        sender_key,
                    )
                except (OSError, sqlite3.Error):
                    LOGGER.warning(
                        "Could not learn first-mail sender for alias workflow %s",
                        workflow.id,
                    )

    async def _scan_delivery_history(self, watchers: list[AliasWorkflow]) -> None:
        targets = {
            address
            for workflow in watchers
            for address in workflow.bypass_recipients
        }
        earliest_at = min(workflow.started_at for workflow in watchers)
        history = await self._fetch_history_covering(earliest_at)
        deliveries = accepted_delivery_metadata(
            history,
            recipients=targets,
            earliest_at=earliest_at,
        )
        if not deliveries:
            return
        sender_deliveries = accepted_delivery_senders(
            history,
            recipients=targets,
            earliest_at=earliest_at,
        )
        await self._learn_first_mail_senders(watchers, sender_deliveries)
        changed = await self.store.record_deliveries(deliveries)
        if self.agent is not None:
            for workflow in changed:
                if workflow.bypass_clear_requested_at is not None:
                    await self.clear_workflow_bypass(workflow)

    async def _fetch_history_covering(self, earliest_at: int) -> list[dict[str, Any]]:
        maximum = self.settings.alias_workflow_history_count
        sizes = [size for size in HISTORY_PROBE_SIZES if size <= maximum]
        if not sizes or sizes[-1] != maximum:
            sizes.append(maximum)
        history: list[dict[str, Any]] = []
        for count in sizes:
            raw_history = await self.mailcow.get_rspamd_history(count)
            history = [
                {
                    "action": item.get("action"),
                    "unix_time": item.get("unix_time"),
                    "rcpt_smtp": item.get("rcpt_smtp"),
                    "sender_mime": item.get("sender_mime"),
                    "sender_smtp": item.get("sender_smtp"),
                }
                for item in raw_history
            ]
            if len(history) < count:
                break
            timestamps = [
                timestamp
                for item in history
                if (timestamp := _event_timestamp(item)) is not None
            ]
            if timestamps and min(timestamps) <= earliest_at:
                break
        return history
