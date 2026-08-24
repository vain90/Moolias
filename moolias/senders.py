from __future__ import annotations

import re
import unicodedata

import tldextract

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "alias",
        "email",
        "mail",
        "newsletter",
        "shop",
        "store",
        "info",
        "kontakt",
        "contact",
        "service",
        "support",
        "konto",
        "account",
        "login",
        "online",
        "web",
        "www",
        "app",
        "test",
    }
)
_SHORT_BRAND_TOKENS = frozenset({"dm", "ing"})

# Use tldextract's bundled Public Suffix List snapshot, including private suffixes
# such as github.io. Sender matching must not cause network access at runtime merely
# to refresh suffix data, and multi-tenant suffixes must not create brand trust.
_DOMAIN_EXTRACTOR = tldextract.TLDExtract(
    cache_dir=None,
    suffix_list_urls=(),
    fallback_to_snapshot=True,
    include_psl_private_domains=True,
)


def _ascii(value: str) -> str:
    return (
        unicodedata.normalize("NFKD", value)
        .encode("ascii", "ignore")
        .decode("ascii")
        .lower()
    )


def _significant_tokens(value: str) -> list[str]:
    return [
        token
        for token in _TOKEN_RE.findall(_ascii(value))
        if len(token) >= 4 and not token.isdigit() and token not in _STOPWORDS
    ]


def _tokens(value: str) -> set[str]:
    return set(_significant_tokens(value))


def _identity_candidates(value: str) -> set[str]:
    tokens = _significant_tokens(value)
    candidates = set(tokens)
    for first, second in zip(tokens, tokens[1:], strict=False):
        candidates.add(f"{first}-{second}")
        candidates.add(f"{first}{second}")
    return candidates


def alias_identity_tokens(alias_address: str, name: str) -> set[str]:
    local_part = alias_address.split("@", 1)[0]
    return _identity_candidates(local_part) | _identity_candidates(name)


def description_identity_tokens(description: str) -> set[str]:
    # A private description is supporting context, not a second alias name.
    # Only exact significant tokens count; adjacent words are not promoted to
    # compound brand identities and short-brand exceptions are not applied.
    return _tokens(description)


def _short_brand_tokens(alias_address: str, name: str) -> set[str]:
    local_part = alias_address.split("@", 1)[0]
    raw_tokens = set(_TOKEN_RE.findall(_ascii(f"{local_part} {name}")))
    return raw_tokens & _SHORT_BRAND_TOKENS


def _canonical_domain(sender_domain: str) -> str | None:
    labels = sender_domain.strip().strip(".").split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return None
    try:
        return ".".join(label.encode("idna").decode("ascii") for label in labels).lower()
    except UnicodeError:
        return None


def _domain_identity(sender_domain: str) -> tuple[str, bool] | None:
    canonical = _canonical_domain(sender_domain)
    if canonical is None:
        return None
    extracted = _DOMAIN_EXTRACTOR(canonical)
    if not extracted.domain or not extracted.suffix:
        return None
    return extracted.domain.lower(), bool(extracted.is_private)


def registered_domain_label(sender_domain: str) -> str | None:
    identity = _domain_identity(sender_domain)
    return identity[0] if identity is not None else None


def sender_domain_tokens(sender_domain: str) -> set[str]:
    identity = _domain_identity(sender_domain)
    if identity is None or identity[1]:
        return set()
    return {identity[0]}


def sender_match_token(
    alias_address: str,
    name: str,
    sender_domain: str,
    *,
    private_description: str | None = None,
) -> str | None:
    identity = _domain_identity(sender_domain)
    if identity is None:
        return None
    registered_label, is_private = identity
    if is_private:
        return None

    if private_description is None:
        private_description = str(getattr(name, "private_description", ""))

    if registered_label in _short_brand_tokens(alias_address, name):
        return registered_label
    if registered_label in alias_identity_tokens(alias_address, name):
        return registered_label
    if registered_label in description_identity_tokens(private_description):
        return registered_label
    return None


def sender_matches_alias(
    alias_address: str,
    name: str,
    sender_domain: str,
    *,
    private_description: str | None = None,
) -> bool:
    return (
        sender_match_token(
            alias_address,
            name,
            sender_domain,
            private_description=private_description,
        )
        is not None
    )
