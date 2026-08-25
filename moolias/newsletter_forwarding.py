from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from moolias.aliases import AliasRecord, is_owned_alias
from moolias.mailcow import MailcowError


@dataclass(frozen=True, slots=True)
class ForwardedNewsletterAddress:
    address: str
    name: str = ""
    source: str = "alias"


def forwarded_newsletter_tag(base_tag: str) -> str:
    base = base_tag.strip().casefold()
    if not base:
        raise ValueError("Newsletter tag must not be empty")
    return f"{base}-forwarded"


def forwarded_newsletters_enabled(tags: object, base_tag: str) -> bool:
    expected = forwarded_newsletter_tag(base_tag)
    if not isinstance(tags, (list, tuple, set, frozenset)):
        return False
    return any(str(tag).strip().casefold() == expected for tag in tags)


def replace_forwarded_newsletter_tag(
    tags: object,
    base_tag: str,
    enabled: bool,
) -> list[str]:
    marker = forwarded_newsletter_tag(base_tag)
    existing: Iterable[object] = (
        tags if isinstance(tags, (list, tuple, set, frozenset)) else ()
    )

    result = [
        str(tag).strip()
        for tag in existing
        if str(tag).strip() and str(tag).strip().casefold() != marker
    ]
    if enabled:
        result.append(marker)
    return result


def direct_mailcow_forwards_to_mailbox(
    aliases: Iterable[AliasRecord],
    mailbox: str,
) -> list[ForwardedNewsletterAddress]:
    """Return active direct Mailcow alias forwards to the mailbox."""

    mailbox_key = mailbox.strip().casefold()
    if "@" not in mailbox_key:
        return []

    forwarded: list[ForwardedNewsletterAddress] = []
    for alias in aliases:
        address = alias.address.strip().casefold()
        if (
            not alias.active
            or alias.is_catch_all
            or address.startswith("@")
            or "@" not in address
            or address == mailbox_key
            or is_owned_alias(alias, mailbox_key)
        ):
            continue

        targets = [
            target.strip().casefold()
            for target in alias.goto.split(",")
            if target.strip()
        ]
        if len(targets) != 1 or targets[0] != mailbox_key:
            continue

        forwarded.append(
            ForwardedNewsletterAddress(
                address=address,
                name=alias.name.strip(),
                source="alias",
            )
        )

    return sorted(forwarded, key=lambda item: (item.name.casefold(), item.address))


def _active(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _simple_sieve_redirect_target(script: object) -> str | None:
    """Return the target of a deliberately simple unconditional Sieve redirect.

    The parser is intentionally conservative. Conditional rules, multiple actions that
    can deliver elsewhere, variables and multiple redirects are not treated as proof of
    a full mailbox forward.
    """

    text = str(script or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text.strip() or "/*" in text or "*/" in text:
        return None

    lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "#" in stripped:
            return None
        lines.append(stripped)

    compact = " ".join(lines)
    match = re.fullmatch(
        r'redirect\s+"([^"\r\n]+)"\s*;'
        r"\s*(?:discard\s*;\s*)?"
        r"(?:stop\s*;\s*)?",
        compact,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    target = match.group(1).strip().casefold()
    return target if "@" in target else None


def sieve_mailcow_forwards_to_mailbox(
    mailboxes: Iterable[dict[str, Any]],
    filters: Iterable[dict[str, Any]],
    mailbox: str,
) -> list[ForwardedNewsletterAddress]:
    """Return active Mailcow mailbox prefilters that fully redirect to mailbox."""

    mailbox_key = mailbox.strip().casefold()
    if "@" not in mailbox_key:
        return []

    source_mailboxes: dict[str, dict[str, Any]] = {}
    for item in mailboxes:
        address = str(item.get("username") or "").strip().casefold()
        if address and address != mailbox_key and _active(item.get("active")):
            source_mailboxes[address] = item

    forwarded: dict[str, ForwardedNewsletterAddress] = {}
    for item in filters:
        source = str(item.get("username") or "").strip().casefold()
        if source not in source_mailboxes:
            continue
        if str(item.get("filter_type") or "").strip().casefold() != "prefilter":
            continue
        if not _active(item.get("active")):
            continue
        if _simple_sieve_redirect_target(item.get("script_data")) != mailbox_key:
            continue

        mailbox_details = source_mailboxes[source]
        forwarded[source] = ForwardedNewsletterAddress(
            address=source,
            name=str(mailbox_details.get("name") or "").strip(),
            source="sieve",
        )

    return sorted(forwarded.values(), key=lambda item: (item.name.casefold(), item.address))


async def discover_mailcow_forwards_to_mailbox(
    mailcow: Any,
    mailbox: str,
    *,
    aliases: Iterable[AliasRecord] | None = None,
) -> list[ForwardedNewsletterAddress]:
    """Discover only forwarding relationships that are explicitly configured in Mailcow."""

    alias_records = list(aliases) if aliases is not None else await mailcow.list_aliases()
    forwarded = {
        item.address.casefold(): item
        for item in direct_mailcow_forwards_to_mailbox(alias_records, mailbox)
    }

    list_filters = getattr(mailcow, "list_filters", None)
    list_mailboxes = getattr(mailcow, "list_mailboxes", None)
    if not callable(list_filters) or not callable(list_mailboxes):
        return sorted(forwarded.values(), key=lambda item: (item.name.casefold(), item.address))

    try:
        mailboxes, filters = await asyncio.gather(list_mailboxes(), list_filters())
    except MailcowError:
        # Older Mailcow versions may not expose filter listing through the API. Direct
        # alias forwards remain usable instead of making Newsletter Management fail.
        return sorted(forwarded.values(), key=lambda item: (item.name.casefold(), item.address))

    for item in sieve_mailcow_forwards_to_mailbox(mailboxes, filters, mailbox):
        forwarded.setdefault(item.address.casefold(), item)

    return sorted(forwarded.values(), key=lambda item: (item.name.casefold(), item.address))
