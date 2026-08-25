from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from moolias.aliases import AliasRecord, is_owned_alias


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


def _active(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    return str(value or "").strip().casefold() in {"1", "true", "yes", "on"}


def _normalised_tags(value: object) -> set[str]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return set()
    return {str(tag).strip().casefold() for tag in value if str(tag).strip()}


def _link_ids(tags: object, base_tag: str, role: str) -> set[str]:
    base = base_tag.strip().casefold()
    if not base:
        raise ValueError("Newsletter tag must not be empty")
    if role not in {"source", "target"}:
        raise ValueError("Unknown newsletter link role")

    prefix = f"{base}-link-"
    suffix = f"-{role}"
    result: set[str] = set()
    for tag in _normalised_tags(tags):
        if not tag.startswith(prefix) or not tag.endswith(suffix):
            continue
        link_id = tag[len(prefix) : -len(suffix)]
        if not link_id or len(link_id) > 64:
            continue
        if not link_id[0].isalnum():
            continue
        if any(character not in "abcdefghijklmnopqrstuvwxyz0123456789._-" for character in link_id):
            continue
        result.add(link_id)
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


def linked_mailcow_mailboxes(
    mailboxes: Iterable[dict[str, Any]],
    mailbox: str,
    base_tag: str,
) -> list[ForwardedNewsletterAddress]:
    """Return active source mailboxes explicitly linked to the target by Mailcow tags.

    A link named ``private`` uses ``<base>-link-private-target`` on the target
    mailbox and ``<base>-link-private-source`` on one or more source mailboxes.
    The tags express ownership for Newsletter Management only; Moolias does not
    infer or modify the actual Mailcow/Sieve routing between the mailboxes.
    """

    mailbox_key = mailbox.strip().casefold()
    if "@" not in mailbox_key:
        return []

    records = [item for item in mailboxes if isinstance(item, dict)]
    target = next(
        (
            item
            for item in records
            if str(item.get("username") or "").strip().casefold() == mailbox_key
        ),
        None,
    )
    if target is None:
        return []

    target_links = _link_ids(target.get("tags"), base_tag, "target")
    if not target_links:
        return []

    result: dict[str, ForwardedNewsletterAddress] = {}
    for item in records:
        address = str(item.get("username") or "").strip().casefold()
        if not address or address == mailbox_key or "@" not in address:
            continue
        if not _active(item.get("active")):
            continue
        source_links = _link_ids(item.get("tags"), base_tag, "source")
        if not (target_links & source_links):
            continue
        result[address] = ForwardedNewsletterAddress(
            address=address,
            name=str(item.get("name") or "").strip(),
            source="linked_mailbox",
        )

    return sorted(result.values(), key=lambda item: (item.name.casefold(), item.address))


def mailcow_forwarded_newsletter_addresses(
    aliases: Iterable[AliasRecord],
    mailboxes: Iterable[dict[str, Any]],
    mailbox: str,
    base_tag: str,
) -> list[ForwardedNewsletterAddress]:
    """Combine direct alias forwards with explicitly tag-linked source mailboxes."""

    forwarded = {
        item.address.casefold(): item
        for item in direct_mailcow_forwards_to_mailbox(aliases, mailbox)
    }
    for item in linked_mailcow_mailboxes(mailboxes, mailbox, base_tag):
        forwarded.setdefault(item.address.casefold(), item)
    return sorted(forwarded.values(), key=lambda item: (item.name.casefold(), item.address))
