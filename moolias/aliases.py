from __future__ import annotations

import re
import secrets
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files

RESERVED_MARKER = "reserved"
USED_RESERVED_MARKER = "reserved-used"
RESERVED_COMMENT = f"[moolias:{RESERVED_MARKER}]"
USED_RESERVED_COMMENT = f"[moolias:{USED_RESERVED_MARKER}]"
_MOOLIAS_MARKER_RE = re.compile(r"\[moolias:([a-z0-9][a-z0-9._-]*)\]", re.IGNORECASE)
_SUFFIX_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"
_LOCAL_PART_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")


def moolias_markers(private_comment: str) -> frozenset[str]:
    return frozenset(
        match.group(1).lower()
        for match in _MOOLIAS_MARKER_RE.finditer(private_comment or "")
    )


def private_comment_description(private_comment: str) -> str:
    """Return the human description while hiding Moolias metadata markers."""
    without_markers = _MOOLIAS_MARKER_RE.sub(" ", private_comment or "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in without_markers.splitlines()]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def compose_private_comment(description: str, markers: Iterable[str] = ()) -> str:
    """Build a private comment from user text plus explicit Moolias markers."""
    clean_description = private_comment_description(description)
    normalized_markers = sorted(
        {
            str(marker).strip().lower()
            for marker in markers
            if str(marker).strip()
        }
    )
    parts = [clean_description] if clean_description else []
    parts.extend(f"[moolias:{marker}]" for marker in normalized_markers)
    return "\n".join(parts)


def update_private_comment(
    private_comment: str,
    *,
    description: str | None = None,
    add_markers: Iterable[str] = (),
    remove_markers: Iterable[str] = (),
) -> str:
    """Update only Moolias metadata and/or the human description."""
    markers = set(moolias_markers(private_comment))
    markers.difference_update(str(marker).strip().lower() for marker in remove_markers)
    markers.update(str(marker).strip().lower() for marker in add_markers if str(marker).strip())
    text = (
        private_comment_description(private_comment)
        if description is None
        else private_comment_description(description)
    )
    return compose_private_comment(text, markers)


class AliasPurpose(str):
    """Public alias name carrying its optional private description for matchers."""

    private_description: str

    def __new__(cls, name: str, private_description: str = "") -> AliasPurpose:
        value = super().__new__(cls, name)
        value.private_description = private_description
        return value


@dataclass(frozen=True, slots=True)
class AliasRecord:
    id: int
    address: str
    goto: str
    domain: str
    active: bool
    private_comment: str
    public_comment: str
    sogo_visible: bool = False
    sender_allowed: bool | None = None
    is_catch_all: bool = False

    @classmethod
    def from_mailcow(cls, data: dict) -> AliasRecord:
        sender_allowed = data.get("sender_allowed")
        return cls(
            id=int(data["id"]),
            address=str(data.get("address", "")),
            goto=str(data.get("goto", "")),
            domain=str(data.get("domain", "")),
            active=str(data.get("active", "0")) == "1",
            private_comment=str(data.get("private_comment") or ""),
            public_comment=str(data.get("public_comment") or ""),
            sogo_visible=str(data.get("sogo_visible", "0")) == "1",
            sender_allowed=(str(sender_allowed) == "1") if sender_allowed is not None else None,
            is_catch_all=str(data.get("is_catch_all", "0")) == "1",
        )

    @property
    def markers(self) -> frozenset[str]:
        return moolias_markers(self.private_comment)

    @property
    def is_reserved(self) -> bool:
        return bool({RESERVED_MARKER, USED_RESERVED_MARKER} & self.markers)

    @property
    def is_reserved_used(self) -> bool:
        return USED_RESERVED_MARKER in self.markers

    @property
    def name(self) -> str:
        return self.public_comment.strip()

    @property
    def private_description(self) -> str:
        return private_comment_description(self.private_comment)

    @property
    def description(self) -> AliasPurpose:
        # Keep existing purpose/name consumers compatible while attaching the
        # private description for sender matching.
        return AliasPurpose(self.name, self.private_description)


def mailbox_domain(email: str) -> str:
    local, separator, domain = email.strip().lower().rpartition("@")
    if separator != "@" or not local or not domain:
        raise ValueError("Invalid mailbox address")
    return domain


def validate_local_part(value: str) -> str:
    value = value.strip().lower()
    if not _LOCAL_PART_RE.fullmatch(value):
        raise ValueError(
            "Use 1-63 lowercase letters, numbers, dots, underscores or hyphens; "
            "the first character must be a letter or number."
        )
    return value


def slugify(value: str, max_length: int = 28) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_value).strip("-")
    slug = slug[:max_length].rstrip("-")
    return slug or "alias"


def random_suffix(length: int = 2) -> str:
    return "".join(secrets.choice(_SUFFIX_ALPHABET) for _ in range(length))


def named_local_part(name: str) -> str:
    return f"{slugify(name)}-{random_suffix()}"


def load_words(language: str) -> tuple[str, ...]:
    path = files("moolias").joinpath("wordlists", f"{language}.txt")
    words = tuple(
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    )
    if len(words) < 32:
        raise RuntimeError(f"Wordlist {language!r} is too small")
    return words


def _distinct_words(words: tuple[str, ...], count: int) -> list[str]:
    chosen: list[str] = []
    while len(chosen) < count:
        word = secrets.choice(words)
        if word not in chosen:
            chosen.append(word)
    return chosen


def readable_local_part(language: str = "en") -> str:
    words = load_words(language)
    first, second = _distinct_words(words, 2)
    number = secrets.randbelow(90) + 10
    return f"{first}-{second}-{number}"


def _targets_mailbox(alias: AliasRecord, user_email: str) -> bool:
    user_email = user_email.strip().lower()
    targets = {target.strip().lower() for target in alias.goto.split(",") if target.strip()}
    return user_email in targets


def is_primary_mailbox_alias(alias: AliasRecord, user_email: str) -> bool:
    user_email = user_email.strip().lower()
    domain = mailbox_domain(user_email)
    return (
        not alias.is_catch_all
        and alias.address.strip().lower() == user_email
        and alias.domain.strip().lower() == domain
        and alias.goto.strip().lower() == user_email
    )


def is_mailbox_catch_all(alias: AliasRecord, user_email: str) -> bool:
    domain = mailbox_domain(user_email)
    address = alias.address.strip().lower()
    return (
        alias.active
        and alias.domain.strip().lower() == domain
        and (alias.is_catch_all or address == f"@{domain}")
        and _targets_mailbox(alias, user_email)
    )


def is_owned_alias(alias: AliasRecord, user_email: str) -> bool:
    user_email = user_email.lower()
    domain = mailbox_domain(user_email)
    address = alias.address.strip().lower()
    if alias.is_catch_all or address.startswith("@"):
        return False
    if alias.domain.lower() != domain:
        return False
    if not address.endswith(f"@{domain}"):
        return False
    # Shared aliases are deliberately excluded. The authenticated mailbox must be the only target.
    return alias.goto.strip().lower() == user_email
