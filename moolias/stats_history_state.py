from __future__ import annotations

import time
from collections import Counter

from moolias.mailcow import MailcowError
from moolias.senders import sender_match_token
from moolias.stats import SenderUsage
from moolias.stats_history import StatsHistoryStore, perform_pending_backfill
from moolias.stats_mode import StatsMode


def _merge_sender_entries(entries: list[SenderUsage]) -> list[SenderUsage]:
    merged: dict[str, SenderUsage] = {}
    for entry in entries:
        key = entry.sender_key.lower()
        current = merged.get(key)
        if current is None:
            merged[key] = entry
            continue
        timestamps = [
            value
            for value in (current.last_received_at, entry.last_received_at)
            if value is not None
        ]
        manual_expected = (
            entry.manual_expected
            if entry.manual_expected is not None
            else current.manual_expected
        )
        merged[key] = SenderUsage(
            sender_key=key,
            sender_domain=entry.sender_domain or current.sender_domain,
            sender_address=entry.sender_address or current.sender_address,
            received_count=current.received_count + entry.received_count,
            last_received_at=max(timestamps) if timestamps else None,
            manual_expected=manual_expected,
        )
    return list(merged.values())


def _domain_entries(entries: list[SenderUsage]) -> list[SenderUsage]:
    grouped: dict[str, SenderUsage] = {}
    for entry in entries:
        domain = entry.sender_domain.lower()
        if not domain:
            continue
        current = grouped.get(domain)
        timestamps = [
            value
            for value in (
                current.last_received_at if current is not None else None,
                entry.last_received_at,
            )
            if value is not None
        ]
        manual_expected = entry.manual_expected
        if current is not None and manual_expected is None:
            manual_expected = current.manual_expected
        grouped[domain] = SenderUsage(
            sender_key=domain,
            sender_domain=domain,
            sender_address=None,
            received_count=(current.received_count if current is not None else 0)
            + entry.received_count,
            last_received_at=max(timestamps) if timestamps else None,
            manual_expected=manual_expected,
        )
    return list(grouped.values())


def _sender_rows(alias_record, entries: list[SenderUsage]) -> list[dict]:
    rows: list[dict] = []
    for entry in entries:
        match_token = sender_match_token(
            alias_record.address,
            alias_record.description,
            entry.sender_domain,
        )
        automatic_expected = match_token is not None
        if entry.manual_expected is None:
            expected = automatic_expected
            review_source = "automatic" if automatic_expected else "unreviewed"
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
                "automatic_expected": automatic_expected,
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
    return rows


async def enrich_ui_state_with_history(request, state: dict) -> dict:
    settings = request.app.state.settings
    stats_store = getattr(request.app.state, "stats_store", None)
    stats_state = state.get("stats_state")
    if (
        not settings.usage_stats
        or stats_store is None
        or not state.get("usage_stats_visible")
        or stats_state is None
        or stats_state.conflict
    ):
        state.setdefault("statistics_coverage", {})
        state.setdefault("statistics_history_pending", False)
        state.setdefault("statistics_history_error", False)
        return state

    user = str(state["user"]).lower()
    history_store = StatsHistoryStore(stats_store.path)
    coverage = await history_store.coverage(user)
    if not coverage:
        await history_store.sync_mode(
            user,
            stats_state.effective,
            started_at=await stats_store.tracking_started_at(),
        )

    history_error = False
    pending = await history_store.pending_request(user)
    if pending is not None:
        try:
            await perform_pending_backfill(
                settings,
                request.app.state.mailcow,
                stats_store,
                user,
                [*state.get("assigned_all", []), *state.get("reserved", [])],
            )
        except MailcowError:
            history_error = True

    coverage = await history_store.coverage(user)
    pending = await history_store.pending_request(user)
    addresses = [
        alias.address
        for alias in [*state.get("assigned_all", []), *state.get("reserved", [])]
    ]

    historical_usage = await history_store.alias_usage(user, addresses)
    usage_stats = state.get("usage_stats", {})
    for alias in [*state.get("assigned_all", []), *state.get("reserved", [])]:
        key = alias.address.lower()
        current = usage_stats.setdefault(
            key,
            {"received_count": 0, "sent_count": 0, "last_used_at": None},
        )
        historical = historical_usage.get(key)
        if historical is None:
            continue
        current["received_count"] = int(current.get("received_count") or 0) + int(
            historical.received_count
        )
        current["sent_count"] = int(current.get("sent_count") or 0) + int(
            historical.sent_count
        )
        timestamps = [
            int(value)
            for value in (
                current.get("last_used_at"),
                historical.last_received_at,
                historical.last_sent_at,
            )
            if value is not None
        ]
        current["last_used_at"] = max(timestamps) if timestamps else None

    live_senders = await stats_store.sender_usage(user, addresses) if addresses else {}
    historical_domain = (
        await history_store.sender_usage(user, addresses, level=StatsMode.DOMAIN)
        if stats_state.effective in {StatsMode.DOMAIN, StatsMode.FULL}
        else {}
    )
    historical_full = (
        await history_store.sender_usage(user, addresses, level=StatsMode.FULL)
        if stats_state.effective is StatsMode.FULL
        else {}
    )

    aliases_by_address = {
        alias.address.lower(): alias
        for alias in [*state.get("assigned_all", []), *state.get("reserved", [])]
    }
    sender_stats: dict[str, list[dict]] = {}
    domain_stats: dict[str, list[SenderUsage]] = {}
    for alias_address, alias_record in aliases_by_address.items():
        live = list(live_senders.get(alias_address, []))
        domain_entries = _domain_entries(
            [*live, *historical_domain.get(alias_address, [])]
        )
        if domain_entries:
            domain_stats[alias_address] = domain_entries

        if stats_state.effective is StatsMode.FULL:
            exact_live = [entry for entry in live if entry.sender_address is not None]
            review_entries = _merge_sender_entries(
                [*exact_live, *historical_full.get(alias_address, [])]
            )
        elif stats_state.effective is StatsMode.DOMAIN:
            review_entries = domain_entries
        else:
            review_entries = []

        if review_entries:
            sender_stats[alias_address] = _sender_rows(alias_record, review_entries)

    state["sender_stats"] = sender_stats
    ignored_aliases = set(state.get("ignored_aliases", set()))
    assigned_addresses = {
        alias.address.lower()
        for alias in state.get("assigned_all", [])
        if alias.active
    }
    unexpected_aliases = {
        alias_address
        for alias_address, rows in sender_stats.items()
        if alias_address in assigned_addresses
        and alias_address not in ignored_aliases
        and any(not bool(row["expected"]) for row in rows)
    }
    state["unexpected_aliases"] = unexpected_aliases

    source_counts: Counter[str] = Counter()
    for entries in domain_stats.values():
        for entry in entries:
            source_counts[entry.sender_domain] += int(entry.received_count)
    state["top_sources"] = source_counts.most_common(8)

    def usage_total(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("received_count") or 0) + int(usage.get("sent_count") or 0)

    def last_used(alias) -> int:
        usage = usage_stats.get(alias.address.lower(), {})
        return int(usage.get("last_used_at") or 0)

    assigned_all = list(state.get("assigned_all", []))
    reserved = list(state.get("reserved", []))
    state["recent_aliases"] = sorted(
        assigned_all,
        key=lambda alias: (last_used(alias), usage_total(alias), alias.address.lower()),
        reverse=True,
    )[:5]
    state["top_aliases"] = sorted(
        assigned_all,
        key=lambda alias: (usage_total(alias), last_used(alias), alias.address.lower()),
        reverse=True,
    )[:8]

    no_usage_evidence = set(state.get("no_usage_evidence", set()))
    no_usage_evidence = {
        address
        for address in no_usage_evidence
        if int(usage_stats.get(address, {}).get("received_count") or 0)
        + int(usage_stats.get(address, {}).get("sent_count") or 0)
        == 0
    }
    state["no_usage_evidence"] = no_usage_evidence

    used_reserved = [
        alias
        for alias in reserved
        if alias.is_reserved_used
        or alias.address.lower() in state.get("usage_evidence", {})
        or usage_total(alias) > 0
    ]
    state["used_reserved"] = used_reserved

    cutoff = int(time.time()) - 90 * 24 * 60 * 60
    unused_90 = [
        alias
        for alias in assigned_all
        if last_used(alias) > 0 and last_used(alias) < cutoff
    ]

    total_received = sum(
        int(item.get("received_count") or 0) for item in usage_stats.values()
    )
    total_sent = sum(int(item.get("sent_count") or 0) for item in usage_stats.values())
    recognized_senders = 0
    unrecognized_senders = 0
    recognized_messages = 0
    unrecognized_messages = 0
    for rows in sender_stats.values():
        for row in rows:
            received = int(row.get("received_count") or 0)
            if bool(row.get("automatic_expected")):
                recognized_senders += 1
                recognized_messages += received
            else:
                unrecognized_senders += 1
                unrecognized_messages += received

    known_sender_total = recognized_senders + unrecognized_senders
    recognition_rate = (
        round(recognized_senders * 100 / known_sender_total)
        if known_sender_total
        else None
    )
    state["stats_summary"].update(
        {
            "received": total_received,
            "sent": total_sent,
            "recognized_senders": recognized_senders,
            "unrecognized_senders": unrecognized_senders,
            "recognized_messages": recognized_messages,
            "unrecognized_messages": unrecognized_messages,
            "recognition_rate": recognition_rate,
            "known_used": len(assigned_all) - len(no_usage_evidence),
            "no_usage_evidence": len(no_usage_evidence),
            "never_used": len(no_usage_evidence),
            "last_activity": max(
                (
                    int(item.get("last_used_at") or 0)
                    for item in usage_stats.values()
                ),
                default=0,
            ),
        }
    )

    collector_count = int(state.get("action_required", {}).get("collector") or 0)
    action_required = state.get("action_required", {})
    action_required.update(
        {
            "used_pool": len(used_reserved),
            "unexpected": len(unexpected_aliases),
            "unused_90": len(unused_90),
            "base_count": (
                len(used_reserved)
                + len(unexpected_aliases)
                + len(unused_90)
                + collector_count
            ),
        }
    )
    state["action_required"] = action_required
    state["statistics_coverage"] = {
        level.value: item.start_at for level, item in coverage.items()
    }
    state["statistics_history_pending"] = pending is not None
    state["statistics_history_error"] = history_error
    return state
