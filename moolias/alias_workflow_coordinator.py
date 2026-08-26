from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable, Mapping
from typing import Any

from moolias.alias_delivery_agent import AliasDeliveryAgentClient, AliasDeliveryAgentError
from moolias.alias_workflows import AliasWorkflow, AliasWorkflowStore
from moolias.config import Settings
from moolias.mailcow import MailcowClient, MailcowError
from moolias.usage import ACCEPTED_ACTIONS

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
