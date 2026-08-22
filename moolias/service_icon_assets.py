from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

EXTRA_SERVICE_ICON_SLUGS: dict[str, str] = {
    "airbnb": "airbnb",
    "adidas": "adidas",
    "aliexpress": "aliexpress",
    "alipay": "alipay",
    "americanexpress": "americanexpress",
    "bitwarden": "bitwarden",
    "buhl": "buhl",
    "cloudflare": "cloudflare",
    "cursor": "cursor",
    "deezer": "deezer",
    "deutschebahn": "deutschebahn",
    "dhl": "dhl",
    "digitalocean": "digitalocean",
    "dji": "dji",
    "dm": "dm",
    "docker": "docker",
    "duolingo": "duolingo",
    "etsy": "etsy",
    "fedex": "fedex",
    "figma": "figma",
    "fiverr": "fiverr",
    "freelancer": "freelancer",
    "galaxus": "galaxus",
    "gitea": "gitea",
    "glassdoor": "glassdoor",
    "hellofresh": "hellofresh",
    "iberia": "iberia",
    "ikea": "ikea",
    "kickstarter": "kickstarter",
    "kleinanzeigen": "kleinanzeigen",
    "komoot": "komoot",
    "lastpass": "lastpass",
    "line": "line",
    "linktree": "linktree",
    "lufthansa": "lufthansa",
    "mailchimp": "mailchimp",
    "mastodon": "mastodon",
    "medium": "medium",
    "messenger": "messenger",
    "meta": "meta",
    "nextcloud": "nextcloud",
    "nordvpn": "nordvpn",
    "otto": "otto",
    "patreon": "patreon",
    "payback": "payback",
    "philipshue": "philipshue",
    "pinterest": "pinterest",
    "plex": "plex",
    "protonmail": "protonmail",
    "quora": "quora",
    "revolut": "revolut",
    "samsung": "samsung",
    "shazam": "shazam",
    "shopify": "shopify",
    "snapchat": "snapchat",
    "sonos": "sonos",
    "soundcloud": "soundcloud",
    "squarespace": "squarespace",
    "stackoverflow": "stackoverflow",
    "strava": "strava",
    "teamviewer": "teamviewer",
    "threads": "threads",
    "trello": "trello",
    "tripadvisor": "tripadvisor",
    "tripcom": "tripdotcom",
    "tumblr": "tumblr",
    "uber": "uber",
    "unraid": "unraid",
    "ups": "ups",
    "vimeo": "vimeo",
    "vinted": "vinted",
    "vodafone": "vodafone",
    "volkswagen": "volkswagen",
    "westernunion": "westernunion",
    "whatsapp": "whatsapp",
    "wise": "wise",
    "wordpress": "wordpress",
    "yelp": "yelp",
    "youtube": "youtube",
}

EXTRA_SERVICE_ICON_KEYS = frozenset(EXTRA_SERVICE_ICON_SLUGS)
DEFAULT_OUTPUT_PATH = Path(__file__).resolve().parent / "static" / "service-icons.generated.svg"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _strip_namespaces(element: ElementTree.Element) -> None:
    element.tag = _local_name(element.tag)
    for child in element:
        _strip_namespaces(child)


def _symbol_from_svg(key: str, svg: str) -> str:
    root = ElementTree.fromstring(svg)
    view_box = root.attrib.get("viewBox", "0 0 24 24")
    children: list[str] = []
    for child in root:
        if _local_name(child.tag) == "title":
            continue
        _strip_namespaces(child)
        child.set("fill", "currentColor")
        children.append(ElementTree.tostring(child, encoding="unicode", short_empty_elements=True))
    if not children:
        raise RuntimeError(f"Simple Icons asset {key!r} did not contain drawable SVG content")
    body = "".join(children)
    return f'<symbol id="service-{key}" viewBox="{view_box}">{body}</symbol>'


def build_service_icon_sprite(output_path: Path = DEFAULT_OUTPUT_PATH) -> Path:
    from simple_icons_pack import get_icon

    symbols: list[str] = []
    missing: list[str] = []
    for key, slug in EXTRA_SERVICE_ICON_SLUGS.items():
        icon = get_icon(slug)
        if icon is None:
            missing.append(f"{key} ({slug})")
            continue
        symbols.append(_symbol_from_svg(key, icon.svg))

    if missing:
        raise RuntimeError("Missing Simple Icons assets: " + ", ".join(missing))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" aria-hidden="true" style="display:none">\n'
        + "\n".join(f"  {symbol}" for symbol in symbols)
        + "\n</svg>\n",
        encoding="utf-8",
    )
    return output_path


def ensure_service_icon_sprite(output_path: Path = DEFAULT_OUTPUT_PATH) -> Path | None:
    if output_path.exists():
        return output_path
    try:
        return build_service_icon_sprite(output_path)
    except (ImportError, OSError, RuntimeError, ElementTree.ParseError):
        return None


def main() -> None:
    path = build_service_icon_sprite()
    print(f"Generated {len(EXTRA_SERVICE_ICON_SLUGS)} service icons at {path}")


if __name__ == "__main__":
    main()
