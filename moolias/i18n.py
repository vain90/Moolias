from __future__ import annotations

from collections.abc import Mapping

SUPPORTED_LANGUAGES = ("de", "en")
LANGUAGE_COOKIE = "moolias_lang"

_TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "landing_eyebrow": "MAIL ALIASES, SELF-HOSTED",
        "landing_lead": "Create and manage aliases for your mailcow mailbox.",
        "sign_in": "Sign in with mailcow",
        "aliases_title": "Aliases · Moolias",
        "your_aliases": "Your aliases",
        "signed_in_as": "Signed in as {user}",
        "sign_out": "Sign out",
        "help_open": "Help",
        "help_title": "How Moolias works",
        "help_intro": (
            "Moolias helps keep your real mailbox address private by using a separate "
            "alias for each service."
        ),
        "help_aliases_title": "One service, one alias",
        "help_aliases_body": (
            "Create a separate address for shops, apps, newsletters and other services. "
            "Every alias still delivers to your normal mailbox."
        ),
        "help_leaks_title": "Leaks stay isolated",
        "help_leaks_body": (
            "If an alias starts receiving spam or was shared, you can see which service "
            "used it and disable only that address."
        ),
        "help_offline_title": "Offline pool",
        "help_offline_body": (
            "Prepare a few aliases in advance so you can use a fresh address even when "
            "Moolias is unavailable. Assign its purpose later."
        ),
        "help_sogo_title": "Sending with aliases",
        "help_sogo_body": (
            "Enable SOGo only for aliases you want to select as a sender. Other aliases "
            "can stay receive-only in the SOGo interface."
        ),
        "help_storage_title": "mailcow stays the source of truth",
        "help_storage_body": (
            "Moolias does not keep a second alias database. Alias addresses, purposes, "
            "status and SOGo visibility stay in mailcow."
        ),
        "catch_all_active": "Catch-all active",
        "catch_all_hint": (
            "Even addresses you never created on {domain} reach your mailbox. This weakens "
            "one-alias-per-service because unknown or guessed addresses cannot be identified "
            "or disabled individually in Moolias. For clean separation, disable catch-all "
            "and use explicit aliases."
        ),
        "create_alias": "Create alias",
        "purpose": "Purpose",
        "purpose_placeholder": "Amazon, hotel, newsletter …",
        "address_style": "Address style",
        "address_style_hint": "Choose an address style.",
        "recommended": "Recommended",
        "readable_random": "Readable random",
        "readable_random_hint": "Neutral, readable and easy to dictate.",
        "name_random": "Name + random suffix",
        "name_random_hint": "Keeps the purpose recognizable in the address.",
        "custom_local_part": "Custom address",
        "custom_local_part_hint": "Choose the part before @ yourself.",
        "custom_address": "Custom address",
        "immutable_hint": "The address itself stays unchanged.",
        "show_in_sogo": "Show as sender in SOGo",
        "sogo_create_hint": "Adds the alias to the SOGo sender list.",
        "create_alias_button": "Create alias",
        "offline_pool": "Offline pool",
        "offline_pool_hint": "Prepare aliases for offline use.",
        "copy": "Copy",
        "copied": "Copied",
        "delete": "Delete",
        "delete_confirm": "Delete this unused offline alias permanently?",
        "copy_all": "Copy all",
        "plain_text": "Open as text",
        "no_prepared_aliases": "No prepared aliases.",
        "assigned_aliases": "Assigned aliases",
        "assigned_summary": "{filtered} of {total} aliases",
        "usage_settings_title": "Usage statistics",
        "usage_settings_unavailable": "Statistics settings are temporarily unavailable.",
        "usage_mode_inherit": "Use domain default",
        "usage_mode_off": "Off",
        "usage_mode_basic": "Standard",
        "usage_mode_domain": "Domains",
        "usage_mode_full": "Full",
        "usage_mode_off_hint": "Moolias does not collect new statistics for this mailbox.",
        "usage_mode_basic_hint": "Counts accepted received and sent messages.",
        "usage_mode_domain_hint": (
            "Counts received and sent messages and stores sender domains for received mail."
        ),
        "usage_mode_full_hint": (
            "Counts received and sent messages and stores full sender addresses for received mail."
        ),
        "usage_mode_conflict": (
            "Multiple statistics tags exist on the same level. Statistics are disabled for safety."
        ),
        "usage_source_mailbox": "Mailbox setting",
        "usage_source_domain": "Domain default",
        "usage_source_none": "No default",
        "usage_choose_mode": "Choose statistics mode",
        "usage_fix_conflict": "Choose a mode to resolve the conflict",
        "usage_received": "received",
        "usage_sent": "sent",
        "usage_last_used": "last used",
        "sender_stats_title": "Senders",
        "sender_stats_unexpected_short": "unexpected",
        "sender_stats_all": "All sender identities recorded since this sender mode was enabled.",
        "sender_stats_empty": "No sender data has been recorded in this mode yet.",
        "sender_state_confirmed": "Confirmed",
        "sender_state_automatic": "Automatically recognized",
        "sender_state_manual_unexpected": "Marked unexpected",
        "sender_state_unexpected": "Unexpected",
        "sender_action_expected": "Mark as expected",
        "sender_action_unexpected": "Mark as unexpected",
        "sender_action_clear": "Remove marking",
        "search_placeholder": "Search address or purpose",
        "search_aria": "Search aliases",
        "clear_search": "Clear search",
        "filter_all": "All",
        "filter_active": "Active",
        "filter_disabled": "Disabled",
        "filter_aria": "Filter aliases by status",
        "select_all": "Select all",
        "select_none": "Clear selection",
        "selected_count": "{count} selected",
        "select_alias": "Select {address}",
        "bulk_sogo_show": "Show in SOGo",
        "bulk_sogo_hide": "Hide in SOGo",
        "bulk_failed": "The bulk action could not be completed.",
        "no_purpose": "No purpose",
        "status_active": "Active",
        "status_inactive": "Inactive",
        "status_disabled": "Disabled",
        "sogo_on": "SOGo",
        "sogo_off": "SOGo hidden",
        "sogo_off_short": "SOGo off",
        "edit": "Edit",
        "save": "Save",
        "disable": "Disable",
        "enable": "Enable",
        "edit_sogo_hint": "Show this alias in SOGo's sender list.",
        "private_comment_hint": "",
        "address_unchanged": "The alias address stays unchanged.",
        "no_search_matches": "No matching aliases.",
        "no_assigned_aliases": "No aliases yet.",
        "showing_range": "{start}–{end} of {total}",
        "showing_zero": "0 aliases",
        "rows_per_page": "Rows per page",
        "apply": "Apply",
        "previous": "Previous",
        "next": "Next",
        "pagination_aria": "Alias pages",
        "assign_prepared": "Assign prepared alias",
        "assign_hint": "Add what you use this alias for.",
        "used_for_placeholder": "Used for …",
        "assign": "Assign",
        "close": "Close",
        "language": "Language",
    },
    "de": {
        "landing_eyebrow": "MAIL-ALIASE, SELBST GEHOSTET",
        "landing_lead": "Erstelle und verwalte Aliase für dein mailcow-Postfach.",
        "sign_in": "Mit mailcow anmelden",
        "aliases_title": "Aliase · Moolias",
        "your_aliases": "Deine Aliase",
        "signed_in_as": "Angemeldet als {user}",
        "sign_out": "Abmelden",
        "help_open": "Hilfe",
        "help_title": "So funktioniert Moolias",
        "help_intro": (
            "Moolias hilft dir, deine echte Postfachadresse privat zu halten. Dafür nutzt "
            "du für jeden Dienst eine eigene Alias-Adresse."
        ),
        "help_aliases_title": "Ein Dienst, ein Alias",
        "help_aliases_body": (
            "Erstelle für Shops, Apps, Newsletter und andere Dienste jeweils eine eigene "
            "Adresse. Alle Aliase landen weiterhin in deinem normalen Postfach."
        ),
        "help_leaks_title": "Leaks bleiben getrennt",
        "help_leaks_body": (
            "Bekommt ein Alias Spam oder wurde weitergegeben, erkennst du den betroffenen "
            "Dienst und deaktivierst nur diese eine Adresse."
        ),
        "help_offline_title": "Offline-Vorrat",
        "help_offline_body": (
            "Bereite einige Aliase vor, damit du auch ohne Moolias-Zugriff eine frische "
            "Adresse verwenden kannst. Den Zweck trägst du später ein."
        ),
        "help_sogo_title": "Mit Aliasen senden",
        "help_sogo_body": (
            "Aktiviere SOGo nur für Aliase, die du als Absender auswählen möchtest. Andere "
            "Aliase können in SOGo ausgeblendet bleiben."
        ),
        "help_storage_title": "mailcow bleibt die Datenquelle",
        "help_storage_body": (
            "Moolias führt keine zweite Alias-Datenbank. Adresse, Zweck, Status und "
            "SOGo-Sichtbarkeit bleiben direkt in mailcow gespeichert."
        ),
        "catch_all_active": "Catch-all aktiv",
        "catch_all_hint": (
            "Auch nicht angelegte Adressen auf {domain} landen in deinem Postfach. Dadurch "
            "wird das Prinzip eines eigenen Alias pro Dienst geschwächt, weil unbekannte oder "
            "erratene Adressen nicht einzeln in Moolias erkannt und deaktiviert werden können. "
            "Für eine saubere Trennung sollte Catch-all deaktiviert sein."
        ),
        "create_alias": "Alias erstellen",
        "purpose": "Zweck",
        "purpose_placeholder": "Amazon, Hotel, Newsletter …",
        "address_style": "Adressformat",
        "address_style_hint": "Wähle ein Adressformat.",
        "recommended": "Empfohlen",
        "readable_random": "Lesbar zufällig",
        "readable_random_hint": "Neutral, lesbar und gut diktierbar.",
        "name_random": "Name + Zufallssuffix",
        "name_random_hint": "Der Zweck bleibt in der Adresse erkennbar.",
        "custom_local_part": "Eigene Adresse",
        "custom_local_part_hint": "Bestimme den Teil vor @ selbst.",
        "custom_address": "Eigene Adresse",
        "immutable_hint": "Die Adresse selbst bleibt unverändert.",
        "show_in_sogo": "In SOGo als Absender anzeigen",
        "sogo_create_hint": "Fügt den Alias zur SOGo-Absenderliste hinzu.",
        "create_alias_button": "Alias erstellen",
        "offline_pool": "Offline-Vorrat",
        "offline_pool_hint": "Aliase für die Offline-Nutzung vorbereiten.",
        "copy": "Kopieren",
        "copied": "Kopiert",
        "delete": "Löschen",
        "delete_confirm": "Diesen ungenutzten Offline-Alias dauerhaft löschen?",
        "copy_all": "Alle kopieren",
        "plain_text": "Als Text öffnen",
        "no_prepared_aliases": "Keine vorbereiteten Aliase.",
        "assigned_aliases": "Zugeordnete Aliase",
        "assigned_summary": "{filtered} von {total} Aliasen",
        "usage_settings_title": "Nutzungsstatistik",
        "usage_settings_unavailable": (
            "Die Statistik-Einstellungen sind vorübergehend nicht verfügbar."
        ),
        "usage_mode_inherit": "Domain-Vorgabe verwenden",
        "usage_mode_off": "Aus",
        "usage_mode_basic": "Standard",
        "usage_mode_domain": "Domains",
        "usage_mode_full": "Vollständig",
        "usage_mode_off_hint": "Moolias erfasst für dieses Postfach keine neuen Statistikdaten.",
        "usage_mode_basic_hint": "Zählt akzeptierte empfangene und gesendete Nachrichten.",
        "usage_mode_domain_hint": (
            "Zählt Empfang und Versand und speichert bei eingehenden Nachrichten "
            "die Absender-Domain."
        ),
        "usage_mode_full_hint": (
            "Zählt Empfang und Versand und speichert bei eingehenden Nachrichten "
            "die vollständige Absenderadresse."
        ),
        "usage_mode_conflict": (
            "Auf derselben Ebene sind mehrere Statistik-Tags gesetzt. "
            "Die Statistik ist aus Sicherheitsgründen deaktiviert."
        ),
        "usage_source_mailbox": "Postfach-Einstellung",
        "usage_source_domain": "Domain-Vorgabe",
        "usage_source_none": "Keine Vorgabe",
        "usage_choose_mode": "Statistikmodus wählen",
        "usage_fix_conflict": "Modus wählen, um den Konflikt zu beheben",
        "usage_received": "empfangen",
        "usage_sent": "gesendet",
        "usage_last_used": "zuletzt",
        "sender_stats_title": "Absender",
        "sender_stats_unexpected_short": "nicht erkannt",
        "sender_stats_all": "Alle seit Aktivierung dieses Absendermodus erfassten Absender.",
        "sender_stats_empty": "In diesem Modus wurden noch keine Absenderdaten erfasst.",
        "sender_state_confirmed": "Bestätigt",
        "sender_state_automatic": "Automatisch erkannt",
        "sender_state_manual_unexpected": "Zur Prüfung markiert",
        "sender_state_unexpected": "Nicht erkannt",
        "sender_action_expected": "Als erwartet markieren",
        "sender_action_unexpected": "Zur Prüfung markieren",
        "sender_action_clear": "Markierung entfernen",
        "search_placeholder": "Adresse oder Zweck suchen",
        "search_aria": "Aliase durchsuchen",
        "clear_search": "Suche leeren",
        "filter_all": "Alle",
        "filter_active": "Aktiv",
        "filter_disabled": "Deaktiviert",
        "filter_aria": "Aliase nach Status filtern",
        "select_all": "Alle auswählen",
        "select_none": "Alle abwählen",
        "selected_count": "{count} ausgewählt",
        "select_alias": "{address} auswählen",
        "bulk_sogo_show": "In SOGo anzeigen",
        "bulk_sogo_hide": "In SOGo ausblenden",
        "bulk_failed": "Die Sammelaktion konnte nicht vollständig ausgeführt werden.",
        "no_purpose": "Kein Zweck",
        "status_active": "Aktiv",
        "status_inactive": "Inaktiv",
        "status_disabled": "Deaktiviert",
        "sogo_on": "SOGo",
        "sogo_off": "SOGo ausgeblendet",
        "sogo_off_short": "SOGo aus",
        "edit": "Bearbeiten",
        "save": "Speichern",
        "disable": "Deaktivieren",
        "enable": "Aktivieren",
        "edit_sogo_hint": "Zeigt den Alias in der SOGo-Absenderliste.",
        "private_comment_hint": "",
        "address_unchanged": "Die Alias-Adresse bleibt unverändert.",
        "no_search_matches": "Keine passenden Aliase.",
        "no_assigned_aliases": "Noch keine Aliase.",
        "showing_range": "{start}–{end} von {total}",
        "showing_zero": "0 Aliase",
        "rows_per_page": "Zeilen pro Seite",
        "apply": "Übernehmen",
        "previous": "Zurück",
        "next": "Weiter",
        "pagination_aria": "Alias-Seiten",
        "assign_prepared": "Vorbereiteten Alias zuordnen",
        "assign_hint": "Trage ein, wofür du diesen Alias verwendest.",
        "used_for_placeholder": "Verwendet für …",
        "assign": "Zuordnen",
        "close": "Schließen",
        "language": "Sprache",
    },
}


def detect_language(cookie_value: str | None, accept_language: str | None) -> str:
    if cookie_value in SUPPORTED_LANGUAGES:
        return cookie_value

    preferred = (accept_language or "").split(",", 1)[0].strip().lower()
    return "de" if preferred == "de" or preferred.startswith("de-") else "en"


def translations(language: str) -> Mapping[str, str]:
    return _TRANSLATIONS.get(language, _TRANSLATIONS["en"])
