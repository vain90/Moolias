from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from moolias.stats_mode import normalise_tags


class NewsletterMode(StrEnum):
    OFF = "off"
    ON = "on"


class NewsletterModeSource(StrEnum):
    NONE = "none"
    DOMAIN = "domain"
    MAILBOX = "mailbox"


@dataclass(frozen=True, slots=True)
class NewsletterModeState:
    effective: NewsletterMode
    source: NewsletterModeSource
    mailbox_override: NewsletterMode | None
    domain_default: NewsletterMode | None
    conflict: bool = False
    conflict_source: NewsletterModeSource | None = None

    @property
    def enabled(self) -> bool:
        return self.effective is NewsletterMode.ON


def newsletter_mode_tags(base_tag: str) -> dict[NewsletterMode, str]:
    base = base_tag.strip().casefold()
    if not base:
        raise ValueError("Newsletter base tag must not be empty")
    return {
        NewsletterMode.OFF: f"{base}-off",
        NewsletterMode.ON: base,
    }


def selected_effective_mode(
    selection: str,
    domain_default: NewsletterMode | None,
) -> NewsletterMode:
    if selection == "inherit":
        return domain_default or NewsletterMode.OFF
    try:
        return NewsletterMode(selection)
    except ValueError as exc:
        raise ValueError(f"Unknown newsletter mode: {selection}") from exc


def _explicit_mode(tags: Any, base_tag: str) -> tuple[NewsletterMode | None, bool]:
    configured = normalise_tags(tags)
    matches = [
        mode
        for mode, tag in newsletter_mode_tags(base_tag).items()
        if tag in configured
    ]
    if len(matches) == 1:
        return matches[0], False
    if len(matches) > 1:
        return None, True
    return None, False


def resolve_newsletter_mode(
    mailbox_tags: Any,
    domain_tags: Any,
    base_tag: str,
) -> NewsletterModeState:
    mailbox_mode, mailbox_conflict = _explicit_mode(mailbox_tags, base_tag)
    domain_mode, domain_conflict = _explicit_mode(domain_tags, base_tag)

    if mailbox_conflict:
        return NewsletterModeState(
            effective=NewsletterMode.OFF,
            source=NewsletterModeSource.MAILBOX,
            mailbox_override=None,
            domain_default=domain_mode,
            conflict=True,
            conflict_source=NewsletterModeSource.MAILBOX,
        )
    if mailbox_mode is not None:
        return NewsletterModeState(
            effective=mailbox_mode,
            source=NewsletterModeSource.MAILBOX,
            mailbox_override=mailbox_mode,
            domain_default=domain_mode,
        )
    if domain_conflict:
        return NewsletterModeState(
            effective=NewsletterMode.OFF,
            source=NewsletterModeSource.DOMAIN,
            mailbox_override=None,
            domain_default=None,
            conflict=True,
            conflict_source=NewsletterModeSource.DOMAIN,
        )
    if domain_mode is not None:
        return NewsletterModeState(
            effective=domain_mode,
            source=NewsletterModeSource.DOMAIN,
            mailbox_override=None,
            domain_default=domain_mode,
        )
    return NewsletterModeState(
        effective=NewsletterMode.OFF,
        source=NewsletterModeSource.NONE,
        mailbox_override=None,
        domain_default=None,
    )


def replace_mailbox_newsletter_tags(
    existing_tags: Iterable[str] | str | None,
    base_tag: str,
    selection: str,
) -> list[str]:
    if isinstance(existing_tags, str):
        original = [tag.strip() for tag in existing_tags.split(",") if tag.strip()]
    else:
        original = [
            str(tag).strip()
            for tag in (existing_tags or [])
            if str(tag).strip()
        ]

    family = set(newsletter_mode_tags(base_tag).values())
    preserved = [tag for tag in original if tag.casefold() not in family]

    if selection == "inherit":
        return preserved

    mode = selected_effective_mode(selection, None)
    preserved.append(newsletter_mode_tags(base_tag)[mode])
    return preserved
