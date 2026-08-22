from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from moolias.service_icon_assets import EXTRA_SERVICE_ICON_KEYS


@dataclass(frozen=True, slots=True)
class ServiceIcon:
    key: str
    label: str
    glyph: str
    tone: str
    keywords: tuple[str, ...] = ()
    has_logo: bool = False


_GENERIC = ServiceIcon("generic", "Generisch", "AL", "neutral")
_GENERIC_TONES = ("blue", "green", "violet", "orange", "pink", "teal", "red", "dark")


def _icon(
    key: str,
    label: str,
    glyph: str,
    tone: str,
    keywords: tuple[str, ...],
    has_logo: bool | None = None,
) -> ServiceIcon:
    if has_logo is None:
        has_logo = key in EXTRA_SERVICE_ICON_KEYS
    return ServiceIcon(key, label, glyph, tone, keywords, has_logo)


# A real logo is enabled only when Moolias has a local asset for it. Brands that
# Simple Icons marks as forbidden or whose usage remains unclear intentionally
# keep the neutral monogram fallback.
SERVICE_ICONS: tuple[ServiceIcon, ...] = (
    _icon("airbnb", "Airbnb", "A", "pink", ("airbnb",)),
    _icon("adidas", "Adidas", "A", "dark", ("adidas",)),
    _icon("aliexpress", "AliExpress", "A", "red", ("aliexpress", "ali express")),
    _icon("alipay", "Alipay", "A", "blue", ("alipay",)),
    _icon(
        "americanexpress",
        "American Express",
        "AX",
        "blue",
        ("americanexpress", "american express", "amex"),
    ),
    _icon("amazon", "Amazon", "A", "orange", ("amazon", "aws"), False),
    _icon("apple", "Apple", "A", "dark", ("apple", "icloud", "appstore"), True),
    _icon("bitwarden", "Bitwarden", "B", "blue", ("bitwarden",)),
    _icon("booking", "Booking.com", "B", "blue", ("booking", "bookingcom"), True),
    _icon("buhl", "Buhl", "B", "blue", ("buhl", "wiso", "wiso steuer")),
    _icon("check24", "CHECK24", "C", "blue", ("check24", "check 24"), False),
    _icon("cloudflare", "Cloudflare", "C", "orange", ("cloudflare",)),
    _icon("cursor", "Cursor", "C", "dark", ("cursor", "cursor coding")),
    _icon("deezer", "Deezer", "D", "violet", ("deezer",)),
    _icon(
        "deutschebahn",
        "Deutsche Bahn",
        "DB",
        "red",
        ("deutschebahn", "deutsche bahn", "bahn"),
    ),
    _icon("dhl", "DHL", "D", "red", ("dhl",)),
    _icon("digitalocean", "DigitalOcean", "D", "blue", ("digitalocean", "digital ocean")),
    _icon("discord", "Discord", "D", "violet", ("discord",), True),
    _icon("dji", "DJI", "D", "dark", ("dji",)),
    _icon("dm", "dm", "dm", "blue", ("dm", "drogeriemarkt")),
    _icon("docker", "Docker", "D", "blue", ("docker",)),
    _icon("dropbox", "Dropbox", "D", "blue", ("dropbox",), True),
    _icon("duolingo", "Duolingo", "D", "green", ("duolingo",)),
    _icon("ebay", "eBay", "e", "multi", ("ebay",), True),
    _icon("etsy", "Etsy", "E", "orange", ("etsy",)),
    _icon("facebook", "Facebook", "f", "blue", ("facebook",), True),
    _icon("fedex", "FedEx", "F", "violet", ("fedex", "fed ex")),
    _icon("figma", "Figma", "F", "multi", ("figma",)),
    _icon("fiverr", "Fiverr", "F", "green", ("fiverr",)),
    _icon("freelancer", "Freelancer", "F", "blue", ("freelancer", "frelancer")),
    _icon("galaxus", "Galaxus", "G", "orange", ("galaxus", "galaxus.eu")),
    _icon("gitea", "Gitea", "G", "green", ("gitea",)),
    _icon("github", "GitHub", "G", "dark", ("github",), True),
    _icon("gitlab", "GitLab", "G", "orange", ("gitlab",), True),
    _icon("glassdoor", "Glassdoor", "G", "green", ("glassdoor",)),
    _icon("google", "Google", "G", "multi", ("google", "gmail"), True),
    _icon("hellofresh", "HelloFresh", "H", "green", ("hellofresh", "hello fresh")),
    _icon("iberia", "Iberia", "I", "red", ("iberia",)),
    _icon("ikea", "IKEA", "I", "blue", ("ikea",)),
    _icon("instagram", "Instagram", "I", "pink", ("instagram",), True),
    _icon("kickstarter", "Kickstarter", "K", "green", ("kickstarter",)),
    _icon("kleinanzeigen", "Kleinanzeigen", "K", "green", ("kleinanzeigen",)),
    _icon("komoot", "Komoot", "K", "green", ("komoot",)),
    _icon("lastpass", "LastPass", "L", "red", ("lastpass", "last pass")),
    _icon("line", "LINE", "L", "green", ("line",)),
    _icon("linkedin", "LinkedIn", "in", "blue", ("linkedin",), False),
    _icon("linktree", "Linktree", "L", "green", ("linktree",)),
    _icon("lufthansa", "Lufthansa", "L", "blue", ("lufthansa",)),
    _icon("mailchimp", "Mailchimp", "M", "orange", ("mailchimp", "mail chimp")),
    _icon("mastodon", "Mastodon", "M", "violet", ("mastodon",)),
    _icon("medium", "Medium", "M", "dark", ("medium",)),
    _icon("messenger", "Messenger", "M", "blue", ("messenger", "facebook messenger")),
    _icon("meta", "Meta", "M", "blue", ("meta", "meta instagram", "meta facebook")),
    _icon(
        "microsoft",
        "Microsoft",
        "M",
        "blue",
        ("microsoft", "office", "outlook", "azure"),
        False,
    ),
    _icon("netflix", "Netflix", "N", "red", ("netflix",), True),
    _icon("nextcloud", "Nextcloud", "N", "blue", ("nextcloud", "next cloud")),
    _icon("nordvpn", "NordVPN", "N", "blue", ("nordvpn", "nord vpn")),
    _icon("notion", "Notion", "N", "dark", ("notion",), True),
    _icon("openai", "OpenAI", "O", "teal", ("openai", "chatgpt"), False),
    _icon("otto", "Otto", "O", "red", ("otto", "otto.de")),
    _icon("patreon", "Patreon", "P", "orange", ("patreon",)),
    _icon("payback", "PAYBACK", "P", "blue", ("payback",)),
    _icon("paypal", "PayPal", "P", "blue", ("paypal",), True),
    _icon("philipshue", "Philips Hue", "PH", "blue", ("philipshue", "philips hue")),
    _icon("pinterest", "Pinterest", "P", "red", ("pinterest",)),
    _icon("plex", "Plex", "P", "orange", ("plex",)),
    _icon(
        "protonmail",
        "Proton Mail",
        "P",
        "violet",
        ("protonmail", "proton mail", "proton"),
    ),
    _icon("quora", "Quora", "Q", "red", ("quora",)),
    _icon("reddit", "Reddit", "r", "orange", ("reddit",), True),
    _icon("revolut", "Revolut", "R", "dark", ("revolut",)),
    _icon("samsung", "Samsung", "S", "blue", ("samsung",)),
    _icon("shazam", "Shazam", "S", "blue", ("shazam",)),
    _icon("shopify", "Shopify", "S", "green", ("shopify",)),
    _icon("signal", "Signal", "S", "blue", ("signal",), True),
    _icon("slack", "Slack", "S", "multi", ("slack",), False),
    _icon("snapchat", "Snapchat", "S", "orange", ("snapchat",)),
    _icon("sonos", "Sonos", "S", "dark", ("sonos",)),
    _icon("soundcloud", "SoundCloud", "S", "orange", ("soundcloud", "sound cloud")),
    _icon("spotify", "Spotify", "S", "green", ("spotify",), True),
    _icon("squarespace", "Squarespace", "S", "dark", ("squarespace",)),
    _icon(
        "stackoverflow",
        "Stack Overflow",
        "SO",
        "orange",
        ("stackoverflow", "stack overflow"),
    ),
    _icon("steam", "Steam", "S", "blue", ("steam",), True),
    _icon("strava", "Strava", "S", "orange", ("strava",)),
    _icon("stripe", "Stripe", "S", "violet", ("stripe",), True),
    _icon(
        "takko",
        "Takko Fashion",
        "T",
        "red",
        ("takko", "takkofashion", "takko fashion"),
        False,
    ),
    _icon("teamviewer", "TeamViewer", "T", "blue", ("teamviewer", "team viewer")),
    _icon("telegram", "Telegram", "T", "blue", ("telegram",), True),
    _icon("threads", "Threads", "T", "dark", ("threads",)),
    _icon("tiktok", "TikTok", "T", "dark", ("tiktok",), True),
    _icon("tkmaxx", "TK Maxx", "TK", "red", ("tkmaxx", "tk maxx"), False),
    _icon("trello", "Trello", "T", "blue", ("trello",)),
    _icon("tripadvisor", "Tripadvisor", "T", "green", ("tripadvisor", "trip advisor")),
    _icon("tripcom", "Trip.com", "T", "blue", ("trip.com", "tripcom", "trip com")),
    _icon("tumblr", "Tumblr", "T", "blue", ("tumblr",)),
    _icon("twitch", "Twitch", "T", "violet", ("twitch",), True),
    _icon("uber", "Uber", "U", "dark", ("uber",)),
    _icon("unraid", "Unraid", "U", "orange", ("unraid",)),
    _icon("ups", "UPS", "U", "orange", ("ups",)),
    _icon("vimeo", "Vimeo", "V", "blue", ("vimeo",)),
    _icon("vinted", "Vinted", "V", "teal", ("vinted",)),
    _icon("vodafone", "Vodafone", "V", "red", ("vodafone",)),
    _icon("volkswagen", "Volkswagen", "VW", "blue", ("volkswagen", "weconnect", "we connect")),
    _icon("westernunion", "Western Union", "WU", "dark", ("westernunion", "western union")),
    _icon("whatsapp", "WhatsApp", "W", "green", ("whatsapp", "whats app")),
    _icon("wise", "Wise", "W", "green", ("wise", "transferwise")),
    _icon("wordpress", "WordPress", "W", "blue", ("wordpress", "word press")),
    _icon("x", "X / Twitter", "X", "dark", ("twitter", "x.com", "xcom"), True),
    _icon("yelp", "Yelp", "Y", "red", ("yelp",)),
    _icon("youtube", "YouTube", "Y", "red", ("youtube", "you tube")),
    _icon("zalando", "Zalando", "Z", "orange", ("zalando",), True),
    _icon("zoom", "Zoom", "Z", "blue", ("zoom",), True),
)

_ICON_BY_KEY = {icon.key: icon for icon in SERVICE_ICONS}


def _generic_icon(address: str, description: str = "") -> ServiceIcon:
    local_part = address.partition("@")[0]
    source = description.strip() or local_part.strip() or "Alias"
    words = re.findall(r"[^\W_]+", source, flags=re.UNICODE)
    if len(words) >= 2:
        glyph = "".join(word[0] for word in words[:2])
    elif words:
        glyph = words[0][:2]
    else:
        glyph = "AL"
    glyph = glyph.upper()[:2] or "AL"

    normalized = " ".join(words).casefold() or source.casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).digest()
    tone = _GENERIC_TONES[digest[0] % len(_GENERIC_TONES)]
    return ServiceIcon("generic", "Generisch", glyph, tone)


def icon_catalog() -> tuple[ServiceIcon, ...]:
    return (_GENERIC, *SERVICE_ICONS)


def icon_by_key(key: str | None) -> ServiceIcon:
    if not key:
        return _GENERIC
    return _ICON_BY_KEY.get(key.strip().lower(), _GENERIC)


def detect_service_icon(address: str, description: str = "") -> ServiceIcon:
    local_part = address.partition("@")[0]
    haystack = f"{description} {local_part}".casefold()
    normalized = re.sub(r"[^a-z0-9]+", " ", haystack).strip()
    tokens = set(normalized.split())
    padded = f" {normalized} "

    # Composite labels such as "Meta - Instagram und Facebook" should resolve
    # to the umbrella brand named first instead of whichever child service
    # happens to appear earlier in the catalog.
    if "meta" in tokens:
        return _ICON_BY_KEY["meta"]

    for icon in SERVICE_ICONS:
        for keyword in icon.keywords:
            folded_normalized = re.sub(
                r"[^a-z0-9]+",
                " ",
                keyword.casefold(),
            ).strip()
            if not folded_normalized:
                continue
            if f" {folded_normalized} " in padded:
                return icon
            if (
                " " not in folded_normalized
                and len(folded_normalized) >= 4
                and any(
                    re.fullmatch(rf"{re.escape(folded_normalized)}\d+", token)
                    for token in tokens
                )
            ):
                return icon
    return _generic_icon(address, description)


def resolve_service_icon(
    address: str,
    description: str,
    override: str | None,
) -> ServiceIcon:
    if override and override != "auto":
        if override.strip().lower() == "generic":
            return _generic_icon(address, description)
        return icon_by_key(override)
    return detect_service_icon(address, description)
