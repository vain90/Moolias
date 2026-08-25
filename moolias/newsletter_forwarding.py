from __future__ import annotations

from collections.abc import Iterable

from moolias.aliases import AliasRecord, is_owned_alias


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
) -> list[AliasRecord]:
    """Return active direct Mailcow forwards that are not normal owned aliases.

    These addresses are offered as an explicit Newsletter Management opt-in only.
    Shared aliases, catch-alls and forwarding chains are intentionally excluded.
    """

    mailbox_key = mailbox.strip().casefold()
    if "@" not in mailbox_key:
        return []

    forwarded: list[AliasRecord] = []
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

        forwarded.append(alias)

    return sorted(forwarded, key=lambda alias: (alias.name.casefold(), alias.address.casefold()))
