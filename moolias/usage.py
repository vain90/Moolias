from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import time
from dataclasses import replace
from email.utils import parseaddr
from typing import Any

from moolias.aliases import AliasRecord, is_owned_alias, is_primary_mailbox_alias
from moolias.collector_health import (
    LOW_HEADROOM_PERCENT,
    CollectorHealth,
    CollectorHealthStore,
    assess_collector_health,
)
from moolias.config import Settings
from moolias.dedup import DedupStore, dedup_cleanup_due, dedup_prune_cutoff
from moolias.history_probe import (
    HISTORY_HEAD_PROBE_SIZE,
    HISTORY_PROBE_COVERAGE_STATE,
    HistoryProbeStore,
    UnchangedHistory,
    history_probe_fingerprints,
)
from moolias.mailcow import MailcowClient
from moolias.stats import SenderEvent, StatsStore, UsageEvent
from moolias.stats_mode import (
    StatsMode,
    StatsModeState,
    normalise_tags,
    resolve_stats_mode,
)
from moolias.usage_evidence import UsageEvidenceEvent, UsageEvidenceStore

LOGGER = logging.getLogger(__name__)
HISTORY_PROBE_SIZES = (10, 25, 50, 100, 250, 500)

# These Rspamd actions still represent accepted mail. Reject/soft reject/greylist
# entries are deliberately excluded because the message was not accepted.
ACCEPTED_ACTIONS = frozenset(
    {
        "clean",
        "no action",
        "add header",
        "rewrite subject",
        "probable spam",
    }
)


def _normalise_address(value: Any) -> str:
    return str(value or "").strip().lower()


def _normalise_recipients(value: Any) -> set[str]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries = value.split(",")
    else:
        return set()
    return {str(entry).strip().lower() for entry in entries if str(entry).strip()}


def _event_timestamp(item: dict[str, Any]) -> int | None:
    value = item.get("unix_time")
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _event_key(kind: str, item: dict[str, Any], alias: str, event_at: int) -> str:
    # Only the SHA-256 digest is persisted. When a message ID is available it is
    # preferred over scan time so repeated Rspamd scans of the same message do not
    # inflate the counter. Raw message IDs and subjects never enter SQLite.
    message_id = str(item.get("message-id") or item.get("message_id") or "").strip()
    if message_id:
        fingerprint = {
            "kind": kind,
            "alias": alias.lower(),
            "message_id": message_id,
        }
    else:
        fingerprint = {
            "kind": kind,
            "alias": alias.lower(),
            "event_at": event_at,
            "queue_id": str(item.get("qid") or item.get("queue_id") or ""),
            "sender_smtp": str(item.get("sender_smtp") or ""),
            "sender_mime": str(item.get("sender_mime") or ""),
            "subject": str(item.get("subject") or ""),
            "user": str(item.get("user") or ""),
        }
    payload = json.dumps(fingerprint, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _sender_identity(item: dict[str, Any]) -> tuple[str, str] | None:
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


async def mailbox_stats_state(
    settings: Settings,
    mailcow: MailcowClient,
    email: str,
) -> StatsModeState:
    if not settings.usage_stats:
        return resolve_stats_mode([], [], settings.usage_tag)

    mailbox = await mailcow.get_mailbox(email)
    domain = str(mailbox.get("domain") or email.rsplit("@", 1)[-1]).strip().lower()
    domain_details = await mailcow.get_domain(domain)
    return resolve_stats_mode(
        mailbox.get("tags"),
        domain_details.get("tags"),
        settings.usage_tag,
    )


async def mailbox_usage_enabled(
    settings: Settings,
    mailcow: MailcowClient,
    email: str,
) -> bool:
    return (await mailbox_stats_state(settings, mailcow, email)).enabled


class UsageCollector:
    def __init__(self, settings: Settings, mailcow: MailcowClient, store: StatsStore) -> None:
        self.settings = settings
        self.mailcow = mailcow
        self.store = store
        self.health_store = CollectorHealthStore(store.path)
        self.history_probe_store = HistoryProbeStore(store.path)
        self.dedup_store = DedupStore(store.path)
        self.evidence_store = UsageEvidenceStore(store.path)
        self._reported_conflicts: set[str] = set()
        self._last_history: list[dict[str, Any]] | None = None
        self._last_health_warning_signature: tuple[str | None, bool] | None = None

    def _resolve_inventory(
        self,
        domains: list[dict[str, Any]],
        mailboxes: list[dict[str, Any]],
    ) -> dict[str, StatsModeState]:
        domain_payloads: dict[str, dict[str, Any]] = {}
        for domain_payload in domains:
            domain = str(
                domain_payload.get("domain") or domain_payload.get("domain_name") or ""
            ).strip().lower()
            if domain:
                domain_payloads[domain] = domain_payload

        access_tag = self.settings.access_tag.casefold()
        access_domains = {
            domain
            for domain, payload in domain_payloads.items()
            if access_tag and access_tag in normalise_tags(payload.get("tags"))
        }

        states: dict[str, StatsModeState] = {}
        for mailbox in mailboxes:
            username = str(mailbox.get("username") or "").strip().lower()
            if not username or "@" not in username:
                continue
            domain = str(mailbox.get("domain") or username.rsplit("@", 1)[1]).strip().lower()
            mailbox_tags = normalise_tags(mailbox.get("tags"))
            access_allowed = (
                not access_tag or access_tag in mailbox_tags or domain in access_domains
            )
            if not access_allowed:
                continue

            domain_payload = domain_payloads.get(domain, {})
            states[username] = resolve_stats_mode(
                mailbox.get("tags"),
                domain_payload.get("tags"),
                self.settings.usage_tag,
            )
        return states

    async def mailbox_states(self) -> dict[str, StatsModeState]:
        domains, mailboxes = await asyncio.gather(
            self.mailcow.list_domains(),
            self.mailcow.list_mailboxes(),
        )
        states = self._resolve_inventory(domains, mailboxes)
        self._log_new_conflicts(states)
        return states

    def _log_new_conflicts(self, states: dict[str, StatsModeState]) -> None:
        conflicts = {mailbox for mailbox, state in states.items() if state.conflict}
        for mailbox in sorted(conflicts - self._reported_conflicts):
            state = states[mailbox]
            LOGGER.warning(
                "Conflicting Moolias statistics tags for %s on %s level; statistics disabled",
                mailbox,
                state.conflict_source.value if state.conflict_source is not None else "unknown",
            )
        self._reported_conflicts = conflicts

    async def eligible_mailboxes(self) -> set[str]:
        return {
            mailbox
            for mailbox, state in (await self.mailbox_states()).items()
            if state.enabled and not state.conflict
        }

    async def _mark_reserved_aliases_used(self, alias_ids: set[int]) -> None:
        for alias_id in sorted(alias_ids):
            current = await self.mailcow.get_alias(alias_id)
            if current.is_reserved and not current.is_reserved_used:
                await self.mailcow.mark_reserved_alias_used(alias_id)

    async def _migrate_stored_reserved_usage(
        self,
        aliases: list[AliasRecord],
        states: dict[str, StatsModeState],
    ) -> None:
        candidates: dict[str, list[AliasRecord]] = {}
        for alias in aliases:
            target = alias.goto.strip().lower()
            if (
                target in states
                and alias.is_reserved
                and not alias.is_reserved_used
                and is_owned_alias(alias, target)
            ):
                candidates.setdefault(target, []).append(alias)

        used_alias_ids: set[int] = set()
        for mailbox, reserved_aliases in candidates.items():
            stored = await self.store.alias_usage(
                mailbox,
                [alias.address for alias in reserved_aliases],
            )
            for alias in reserved_aliases:
                usage = stored.get(alias.address.lower())
                if usage is not None and (usage.received_count > 0 or usage.sent_count > 0):
                    used_alias_ids.add(alias.id)

        await self._mark_reserved_aliases_used(used_alias_ids)

    def _history_request_sizes(self) -> list[int]:
        maximum = self.settings.usage_history_count
        sizes = [size for size in HISTORY_PROBE_SIZES if size < maximum]
        sizes.append(maximum)
        return sizes

    @staticmethod
    def _history_probe_index(count: int) -> int:
        required_overlap = max(
            1,
            math.ceil(count * LOW_HEADROOM_PERCENT / 100.0),
        )
        return count - required_overlap

    @staticmethod
    def _history_has_target_headroom(
        history: list[dict[str, Any]],
        boundary: int,
    ) -> bool:
        timestamps = [
            timestamp
            for item in history
            if (timestamp := _event_timestamp(item)) is not None
        ]
        if not timestamps:
            return False

        oldest = min(timestamps)
        newest = max(timestamps)
        if newest < boundary:
            return True
        if not (oldest <= boundary <= newest):
            return False

        overlap_count = sum(timestamp < boundary for timestamp in timestamps)
        return (overlap_count / len(history)) * 100.0 >= LOW_HEADROOM_PERCENT

    async def _adaptive_rspamd_history(self, tracking_started_at: int) -> list[dict[str, Any]]:
        previous_health = await self.health_store.read()
        previous_view = assess_collector_health(
            previous_health,
            poll_interval_seconds=self.settings.usage_poll_seconds,
            stale_polls=self.settings.usage_stale_polls,
        )
        stored_probe = await self.history_probe_store.read()
        probe_safe = (
            previous_view.state == "healthy"
            and previous_health.coverage_state in {"healthy", HISTORY_PROBE_COVERAGE_STATE}
            and previous_health.watermark is not None
            and stored_probe is not None
        )

        if probe_safe:
            probe = await self.mailcow.get_rspamd_history(HISTORY_HEAD_PROBE_SIZE)
            current_probe = history_probe_fingerprints(probe)
            if current_probe is not None and current_probe == stored_probe:
                LOGGER.debug(
                    "Checked %d Rspamd history head entries; history is unchanged",
                    HISTORY_HEAD_PROBE_SIZE,
                )
                return UnchangedHistory()

            # Once the head changed, discard the old comparison state before entering
            # the authoritative adaptive path. A failed slow path can then never reuse it.
            await self.history_probe_store.invalidate()

        range_reader = getattr(self.mailcow, "get_rspamd_history_range", None)
        if range_reader is None:
            return await self.mailcow.get_rspamd_history(self.settings.usage_history_count)

        boundary = previous_health.watermark or tracking_started_at
        maximum = self.settings.usage_history_count

        for count in self._history_request_sizes():
            if count == maximum:
                history = await self.mailcow.get_rspamd_history(count)
                LOGGER.debug("Loaded %d Rspamd history entries at configured maximum", len(history))
                return history

            probe_index = self._history_probe_index(count)
            probe = await range_reader(probe_index, probe_index)
            probe_timestamp = _event_timestamp(probe[0]) if probe else None
            if probe_timestamp is not None and probe_timestamp >= boundary:
                continue

            history = await self.mailcow.get_rspamd_history(count)
            if len(history) < count or self._history_has_target_headroom(history, boundary):
                LOGGER.debug(
                    "Loaded %d Rspamd history entries after adaptive probe for %d",
                    len(history),
                    count,
                )
                return history

        return await self.mailcow.get_rspamd_history(maximum)

    async def collect_once(self) -> int:
        self._last_history = None
        tracking_started_at = await self.store.tracking_started_at()
        states = await self.mailbox_states()
        if not states:
            return 0

        aliases = await self.mailcow.list_aliases()
        await self._migrate_stored_reserved_usage(aliases, states)

        mode_starts = await self.store.sync_sender_modes(
            {
                mailbox: state.effective.value
                for mailbox, state in states.items()
                if not state.conflict
            }
        )
        disabled = {
            mailbox
            for mailbox, state in states.items()
            if not state.enabled and not state.conflict
        }
        await self.evidence_store.clear_mailboxes(disabled)

        eligible = {
            mailbox
            for mailbox, state in states.items()
            if state.enabled and not state.conflict
        }
        if not eligible:
            return 0

        pending_backfills = await self.evidence_store.pending_backfills(
            eligible,
            history_limit=self.settings.usage_history_count,
        )
        if pending_backfills:
            history = await self.mailcow.get_rspamd_history(self.settings.usage_history_count)
            LOGGER.info(
                "Loading full Rspamd history for alias usage backfill of %d mailbox(es)",
                len(pending_backfills),
            )
        else:
            history = await self._adaptive_rspamd_history(tracking_started_at)
        self._last_history = history

        alias_targets: dict[str, str] = {}
        alias_records: dict[str, AliasRecord] = {}
        for alias in aliases:
            target = alias.goto.strip().lower()
            address = alias.address.strip().lower()
            if target not in eligible or not address:
                continue
            if alias.is_catch_all or is_primary_mailbox_alias(alias, target):
                continue
            if is_owned_alias(alias, target):
                alias_targets[address] = target
                alias_records[address] = alias

        received_events: list[UsageEvent] = []
        sent_events: list[UsageEvent] = []
        sender_events: list[SenderEvent] = []
        backfill_evidence_events: list[UsageEvidenceEvent] = []
        live_evidence_events: list[UsageEvidenceEvent] = []
        used_reserved_alias_ids: set[int] = set()

        for item in history:
            action = str(item.get("action") or "").strip().lower()
            if action not in ACCEPTED_ACTIONS:
                continue

            event_at = _event_timestamp(item)
            if event_at is None:
                continue

            recipients = _normalise_recipients(item.get("rcpt_smtp"))
            sender_identity = _sender_identity(item)
            for alias in recipients.intersection(alias_targets):
                mailbox = alias_targets[alias]
                alias_record = alias_records[alias]
                if mailbox in pending_backfills:
                    backfill_evidence_events.append(
                        UsageEvidenceEvent(mailbox=mailbox, alias=alias, event_at=event_at)
                    )
                    if alias_record.is_reserved and not alias_record.is_reserved_used:
                        used_reserved_alias_ids.add(alias_record.id)

                mode_start = mode_starts.get(mailbox, event_at + 1)
                if event_at < tracking_started_at or event_at < mode_start:
                    continue

                received_events.append(
                    UsageEvent(
                        event_key=_event_key("received", item, alias, event_at),
                        mailbox=mailbox,
                        alias=alias,
                        event_at=event_at,
                    )
                )
                live_evidence_events.append(
                    UsageEvidenceEvent(mailbox=mailbox, alias=alias, event_at=event_at)
                )
                if alias_record.is_reserved and not alias_record.is_reserved_used:
                    used_reserved_alias_ids.add(alias_record.id)

                mode = states[mailbox].effective
                if (
                    mode in {StatsMode.DOMAIN, StatsMode.FULL}
                    and sender_identity is not None
                ):
                    sender_address, sender_domain = sender_identity
                    sender_events.append(
                        SenderEvent(
                            event_key=_event_key("sender-detail", item, alias, event_at),
                            mailbox=mailbox,
                            alias=alias,
                            sender_domain=sender_domain,
                            sender_address=(
                                sender_address if mode is StatsMode.FULL else None
                            ),
                            mode=mode.value,
                            event_at=event_at,
                        )
                    )

            authenticated_user = _normalise_address(item.get("user"))
            if authenticated_user not in eligible:
                continue

            # Prefer the visible MIME From address. Fall back to the SMTP envelope
            # sender because some clients or mail paths may rewrite one but not the other.
            sender_mime = _normalise_address(item.get("sender_mime"))
            sender_smtp = _normalise_address(item.get("sender_smtp"))
            sent_alias = ""
            if alias_targets.get(sender_mime) == authenticated_user:
                sent_alias = sender_mime
            elif alias_targets.get(sender_smtp) == authenticated_user:
                sent_alias = sender_smtp

            if sent_alias:
                alias_record = alias_records[sent_alias]
                if authenticated_user in pending_backfills:
                    backfill_evidence_events.append(
                        UsageEvidenceEvent(
                            mailbox=authenticated_user,
                            alias=sent_alias,
                            event_at=event_at,
                        )
                    )
                    if alias_record.is_reserved and not alias_record.is_reserved_used:
                        used_reserved_alias_ids.add(alias_record.id)

                if event_at < tracking_started_at or event_at < mode_starts.get(
                    authenticated_user,
                    event_at + 1,
                ):
                    continue

                sent_events.append(
                    UsageEvent(
                        event_key=_event_key("sent", item, sent_alias, event_at),
                        mailbox=authenticated_user,
                        alias=sent_alias,
                        event_at=event_at,
                    )
                )
                live_evidence_events.append(
                    UsageEvidenceEvent(
                        mailbox=authenticated_user,
                        alias=sent_alias,
                        event_at=event_at,
                    )
                )
                if alias_record.is_reserved and not alias_record.is_reserved_used:
                    used_reserved_alias_ids.add(alias_record.id)

        await self.evidence_store.record_events(
            backfill_evidence_events,
            source="backfill",
        )
        await self.evidence_store.record_events(
            live_evidence_events,
            source="live",
        )
        if pending_backfills:
            timestamps = [
                timestamp
                for item in history
                if (timestamp := _event_timestamp(item)) is not None
            ]
            await self.evidence_store.complete_backfills(
                pending_backfills,
                oldest_history_at=min(timestamps) if timestamps else None,
                newest_history_at=max(timestamps) if timestamps else None,
                history_count=len(history),
                history_limit=self.settings.usage_history_count,
            )
            LOGGER.info(
                "Completed alias usage backfill for %d mailbox(es); %d evidence event(s) found",
                len(pending_backfills),
                len(backfill_evidence_events),
            )

        received = await self.store.record_received(received_events)
        sent = await self.store.record_sent(sent_events)
        senders = await self.store.record_senders(sender_events)
        await self._mark_reserved_aliases_used(used_reserved_alias_ids)
        if received or sent or senders:
            LOGGER.info(
                "Recorded %d received, %d sent and %d sender-detail Moolias event(s)",
                received,
                sent,
                senders,
            )
        return received + sent + senders

    async def _prune_deduplication(self, health: CollectorHealth, *, now: int) -> None:
        cutoff = dedup_prune_cutoff(
            previous_watermark=health.previous_watermark,
            coverage_state=health.coverage_state,
            poll_interval_seconds=self.settings.usage_poll_seconds,
            stale_polls=self.settings.usage_stale_polls,
        )
        if cutoff is None:
            return

        last_pruned_at = await self.dedup_store.last_pruned_at()
        if not dedup_cleanup_due(last_pruned_at=last_pruned_at, now=now):
            return

        result = await self.dedup_store.prune(cutoff, pruned_at=now)
        if result.total:
            LOGGER.info(
                "Pruned %d Moolias statistics deduplication hash(es) at floor %d "
                "(%d usage, %d sender-detail)",
                result.total,
                result.floor_at,
                result.processed_events,
                result.sender_processed_events,
            )
        else:
            LOGGER.debug(
                "Moolias statistics deduplication floor is %d; no old hashes to prune",
                result.floor_at,
            )

    def _log_health_warning(self, health: CollectorHealth) -> None:
        signature = (health.coverage_state, health.history_full)
        if signature == self._last_health_warning_signature:
            return
        self._last_health_warning_signature = signature

        if health.coverage_state == "gap":
            LOGGER.warning(
                "Moolias Rspamd history may have a gap: previous watermark %s is not "
                "safely covered by the current window %s..%s",
                health.previous_watermark,
                health.oldest_event_at,
                health.newest_event_at,
            )
        elif health.coverage_state == "low":
            LOGGER.warning(
                "Moolias Rspamd history headroom is low: %.1f%% (%d of %d entries older "
                "than the previous watermark)",
                health.headroom_percent or 0.0,
                health.overlap_count or 0,
                health.history_count or 0,
            )
        elif health.history_full:
            LOGGER.warning(
                "Moolias Rspamd history needed the configured maximum of %d entries; this "
                "is a warning signal, not proof that data was missed",
                health.history_limit or self.settings.usage_history_count,
            )

    async def collect_with_health(self) -> int:
        started_at = int(time.time())
        started_monotonic = time.monotonic()
        await self.health_store.record_attempt(
            attempted_at=started_at,
            poll_interval_seconds=self.settings.usage_poll_seconds,
            history_limit=self.settings.usage_history_count,
        )
        try:
            recorded = await self.collect_once()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            duration_ms = max(0, round((time.monotonic() - started_monotonic) * 1000))
            await self.health_store.record_failure(duration_ms=duration_ms, error=exc)
            raise

        duration_ms = max(0, round((time.monotonic() - started_monotonic) * 1000))
        finished_at = int(time.time())
        try:
            if isinstance(self._last_history, UnchangedHistory):
                await self.history_probe_store.record_unchanged_success(
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                )
                health = await self.health_store.read()
            else:
                health = await self.health_store.record_success(
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    history=self._last_history,
                )
                await self.history_probe_store.record_full_history(self._last_history)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self.health_store.record_failure(duration_ms=duration_ms, error=exc)
            raise

        safety_health = (
            replace(health, coverage_state="healthy")
            if health.coverage_state == HISTORY_PROBE_COVERAGE_STATE
            else health
        )
        try:
            await self._prune_deduplication(safety_health, now=finished_at)
        except asyncio.CancelledError:
            raise
        except Exception:
            LOGGER.exception("Moolias statistics deduplication cleanup failed")
        self._log_health_warning(safety_health)
        return recorded

    async def run_forever(self) -> None:
        while True:
            try:
                await self.collect_with_health()
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Moolias usage statistics collection failed")
            await asyncio.sleep(self.settings.usage_poll_seconds)