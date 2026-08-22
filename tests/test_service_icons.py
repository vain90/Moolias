from pathlib import Path

from moolias.service_icon_assets import EXTRA_SERVICE_ICON_KEYS, build_service_icon_sprite
from moolias.service_icons import detect_service_icon, resolve_service_icon


def test_service_icon_is_detected_from_description() -> None:
    icon = detect_service_icon("safe-k7@example.org", "GitHub notifications")

    assert icon.key == "github"
    assert icon.has_logo is True


def test_service_icon_is_detected_from_alias_local_part() -> None:
    icon = detect_service_icon("netflix-p4@example.org", "Streaming")

    assert icon.key == "netflix"
    assert icon.has_logo is True


def test_unknown_service_uses_deterministic_generic_fallback() -> None:
    icon = detect_service_icon("feder-hafen-27@example.org", "Bettenhaus Leinetal")
    repeated = detect_service_icon("other-address@example.org", "Bettenhaus Leinetal")

    assert icon.key == "generic"
    assert icon.glyph == "BL"
    assert icon.tone == repeated.tone
    assert icon.has_logo is False


def test_generic_initials_are_limited_to_two_letters() -> None:
    icon = detect_service_icon(
        "feder-hafen-27@example.org",
        "Bettenhaus Leinetal Hannover",
    )

    assert icon.glyph == "BL"
    assert len(icon.glyph) == 2


def test_manual_generic_override_uses_generated_monogram() -> None:
    icon = resolve_service_icon(
        "github-k7@example.org",
        "Bettenhaus Leinetal",
        "generic",
    )

    assert icon.key == "generic"
    assert icon.glyph == "BL"


def test_manual_service_icon_override_wins_over_detection() -> None:
    icon = resolve_service_icon("amazon-k7@example.org", "Amazon", "github")

    assert icon.key == "github"
    assert icon.has_logo is True


def test_auto_override_keeps_detection_enabled() -> None:
    icon = resolve_service_icon("amazon-k7@example.org", "Amazon", "auto")

    assert icon.key == "amazon"
    assert icon.has_logo is False


def test_paypal_uses_bundled_logo() -> None:
    icon = detect_service_icon("paypal-k7@example.org", "PayPal")

    assert icon.key == "paypal"
    assert icon.has_logo is True


def test_requested_services_are_detected() -> None:
    expected = {
        "dm": True,
        "lufthansa": True,
        "sonos": True,
        "vodafone": True,
        "check24": False,
        "takko": False,
        "tkmaxx": False,
    }

    for service, has_logo in expected.items():
        icon = detect_service_icon(f"{service}-k7@example.org", service)
        assert icon.key == service
        assert icon.has_logo is has_logo


def test_generated_sprite_contains_every_expanded_logo(tmp_path: Path) -> None:
    output = build_service_icon_sprite(tmp_path / "service-icons.generated.svg")
    sprite = output.read_text(encoding="utf-8")

    assert len(EXTRA_SERVICE_ICON_KEYS) >= 50
    for key in EXTRA_SERVICE_ICON_KEYS:
        assert f'id="service-{key}"' in sprite
