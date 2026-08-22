from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ServiceIcon:
    key: str
    label: str
    glyph: str
    tone: str
    keywords: tuple[str, ...] = ()
    has_logo: bool = False


_GENERIC = ServiceIcon("generic", "Allgemein", "?", "neutral")

# Only enable a real logo when a local asset is bundled with Moolias. Brands that
# Simple Icons marks as forbidden or whose usage is still unclear intentionally
# keep the neutral monogram fallback.
SERVICE_ICONS: tuple[ServiceIcon, ...] = (
    ServiceIcon("amazon", "Amazon", "A", "orange", ("amazon", "aws")),
    ServiceIcon("apple", "Apple", "A", "dark", ("apple", "icloud", "appstore"), True),
    ServiceIcon("booking", "Booking.com", "B", "blue", ("booking", "bookingcom"), True),
    ServiceIcon("discord", "Discord", "D", "violet", ("discord",), True),
    ServiceIcon("dropbox", "Dropbox", "D", "blue", ("dropbox",), True),
    ServiceIcon("ebay", "eBay", "e", "multi", ("ebay",), True),
    ServiceIcon("facebook", "Facebook", "f", "blue", ("facebook", "meta"), True),
    ServiceIcon("github", "GitHub", "G", "dark", ("github",), True),
    ServiceIcon("gitlab", "GitLab", "G", "orange", ("gitlab",), True),
    ServiceIcon("google", "Google", "G", "multi", ("google", "gmail", "youtube"), True),
    ServiceIcon("instagram", "Instagram", "I", "pink", ("instagram",), True),
    ServiceIcon("linkedin", "LinkedIn", "in", "blue", ("linkedin",)),
    ServiceIcon("microsoft", "Microsoft", "M", "blue", ("microsoft", "office", "outlook", "azure")),
    ServiceIcon("netflix", "Netflix", "N", "red", ("netflix",), True),
    ServiceIcon("notion", "Notion", "N", "dark", ("notion",), True),
    ServiceIcon("openai", "OpenAI", "O", "teal", ("openai", "chatgpt")),
    ServiceIcon("paypal", "PayPal", "P", "blue", ("paypal",), True),
    ServiceIcon("reddit", "Reddit", "r", "orange", ("reddit",), True),
    ServiceIcon("signal", "Signal", "S", "blue", ("signal",), True),
    ServiceIcon("slack", "Slack", "S", "multi", ("slack",)),
    ServiceIcon("spotify", "Spotify", "S", "green", ("spotify",), True),
    ServiceIcon("steam", "Steam", "S", "blue", ("steam",), True),
    ServiceIcon("stripe", "Stripe", "S", "violet", ("stripe",), True),
    ServiceIcon("telegram", "Telegram", "T", "blue", ("telegram",), True),
    ServiceIcon("tiktok", "TikTok", "T", "dark", ("tiktok",), True),
    ServiceIcon("twitch", "Twitch", "T", "violet", ("twitch",), True),
    ServiceIcon("x", "X / Twitter", "X", "dark", ("twitter", "xcom"), True),
    ServiceIcon("zalando", "Zalando", "Z", "orange", ("zalando",), True),
    ServiceIcon("zoom", "Zoom", "Z", "blue", ("zoom",), True),
)

_ICON_BY_KEY = {icon.key: icon for icon in SERVICE_ICONS}


def icon_catalog() -> tuple[ServiceIcon, ...]:
    return (_GENERIC, *SERVICE_ICONS)


def icon_by_key(key: str | None) -> ServiceIcon:
    if not key:
        return _GENERIC
    return _ICON_BY_KEY.get(key.strip().lower(), _GENERIC)


def detect_service_icon(address: str, description: str = "") -> ServiceIcon:
    local_part = address.partition("@")[0]
    haystack = f"{description} {local_part}".casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", haystack)
    tokens = set(normalized.split())
    compact = normalized.replace(" ", "")

    for icon in SERVICE_ICONS:
        for keyword in icon.keywords:
            folded = keyword.casefold()
            if folded in tokens or (len(folded) >= 4 and folded in compact):
                return icon
    return _GENERIC


def resolve_service_icon(
    address: str,
    description: str,
    override: str | None,
) -> ServiceIcon:
    if override and override != "auto":
        return icon_by_key(override)
    return detect_service_icon(address, description)
