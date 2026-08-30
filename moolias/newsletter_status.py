from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from moolias.newsletter_store import Newsletter

NEWSLETTER_STATUS_FILTERS = frozenset(
    {"all", "unsubscribable", "no_link", "unsubscribed", "resumed"}
)


def normalise_newsletter_status_filter(value: Any) -> str:
    status = str(value or "all").strip().casefold()
    if status == "active":
        return "unsubscribable"
    return status if status in NEWSLETTER_STATUS_FILTERS else "all"


def newsletter_status(newsletter: Newsletter) -> str:
    if newsletter.resumed_after_unsubscribe:
        return "resumed"
    if newsletter.is_unsubscribed:
        return "unsubscribed"
    if newsletter.direct_unsubscribe_available:
        return "unsubscribable"
    return "no_link"


def newsletter_status_counts(newsletters: Iterable[Newsletter]) -> dict[str, int]:
    counts = {
        "all": 0,
        "unsubscribable": 0,
        "no_link": 0,
        "unsubscribed": 0,
        "resumed": 0,
    }
    for newsletter in newsletters:
        counts["all"] += 1
        counts[newsletter_status(newsletter)] += 1
    return counts
