from __future__ import annotations

from collections import Counter
from email.utils import parseaddr
from typing import Any

from moolias.aliases import AliasRecord
from moolias.stats_mode import StatsMode

_ACCEPTED_ACTIONS = frozenset(
    {
        "clean",
        "no action",
        "add header",
        "rewrite subject",
        "probable spam",
    }
)


def _address(value: Any) -> str:
    raw = value[0] if isinstance(value, list) and value else value
    _, parsed = parseaddr(str(raw or ""))
    return parsed.strip().lower()


def _recipients(value: Any) -> set[str]:
    if isinstance(value, list):
        entries = value
    elif isinstance(value, str):
        entries = value.split(",")
    else:
        return set()

    result: set[str] = set()
    for entry in entries:
        _, address = parseaddr(str(entry or ""))
        address = address.strip().lower()
        if "@" in address:
            result.add(address)
    return result


async def top_outgoing_destinations(
    settings,
    mailcow,
    mailbox: str,
    aliases: list[AliasRecord],
    mode: StatsMode,
    *,
    limit: int = 8,
) -> list[dict[str, int | str]]:
    """Return the most common current Rspamd destinations for mail sent via aliases."""
    if mode not in {StatsMode.DOMAIN, StatsMode.FULL}:
        return []

    owned = {alias.address.strip().lower() for alias in aliases if alias.address.strip()}
    if not owned:
        return []

    history = await mailcow.get_rspamd_history(settings.usage_history_count)
    counts: Counter[str] = Counter()
    last_seen: dict[str, int] = {}
    mailbox = mailbox.strip().lower()

    for item in history:
        if str(item.get("action") or "").strip().lower() not in _ACCEPTED_ACTIONS:
            continue
        if str(item.get("user") or "").strip().lower() != mailbox:
            continue

        sender = _address(item.get("sender_mime")) or _address(item.get("sender_smtp"))
        if sender not in owned:
            continue

        try:
            event_at = int(float(item.get("unix_time")))
        except (TypeError, ValueError):
            event_at = 0

        for recipient in _recipients(item.get("rcpt_smtp")):
            domain = recipient.rsplit("@", 1)[1]
            key = recipient if mode is StatsMode.FULL else domain
            counts[key] += 1
            last_seen[key] = max(last_seen.get(key, 0), event_at)

    return [
        {"label": label, "count": count, "last_seen_at": last_seen.get(label, 0)}
        for label, count in sorted(
            counts.items(),
            key=lambda item: (item[1], last_seen.get(item[0], 0), item[0]),
            reverse=True,
        )[:limit]
    ]
