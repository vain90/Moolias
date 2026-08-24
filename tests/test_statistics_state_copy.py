from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = (ROOT / "moolias" / "templates" / "overview.html").read_text(encoding="utf-8")
BASE = (ROOT / "moolias" / "templates" / "base.html").read_text(encoding="utf-8")
STATISTICS = (ROOT / "moolias" / "templates" / "statistics.html").read_text(encoding="utf-8")
TOUR = (ROOT / "moolias" / "static" / "tour.js").read_text(encoding="utf-8")
DOCS = (ROOT / "docs" / "statistics.md").read_text(encoding="utf-8")

DOC_URL = "https://github.com/vain90/Moolias/blob/main/docs/statistics.md"


def test_server_disabled_statistics_state_is_consistent_across_ui():
    for template in (OVERVIEW, BASE, STATISTICS):
        assert "Nutzungsstatistik ist serverseitig deaktiviert" in template
        assert "Usage statistics are disabled server-side" in template
        assert DOC_URL in template
        assert 'target="_blank" rel="noopener noreferrer"' in template


def test_overview_distinguishes_server_mailbox_and_error_states():
    server_disabled = OVERVIEW.index("{% elif not stats_available %}")
    temporary_error = OVERVIEW.index("{% elif stats_error or not stats_state %}")
    mailbox_disabled = OVERVIEW.index("{% elif not usage_stats_visible %}")

    assert server_disabled < temporary_error < mailbox_disabled
    assert "Für dieses Postfach ist kein Statistikmodus aktiviert" in OVERVIEW
    assert "Statistikstatus ist vorübergehend nicht verfügbar" in OVERVIEW
    assert 'data-open-settings-section="statistics"' in OVERVIEW


def test_settings_only_calls_real_load_failures_temporarily_unavailable():
    server_branch = BASE.index("{% if not stats_available %}")
    error_branch = BASE.index("{% elif stats_error or not stats_state %}", server_branch)
    normal_branch = BASE.index("{% else %}", error_branch)

    assert server_branch < error_branch < normal_branch
    server_section = BASE[server_branch:error_branch]
    error_section = BASE[error_branch:normal_branch]
    assert "serverseitig deaktiviert" in server_section
    assert "usage_settings_unavailable" not in server_section
    assert "usage_settings_unavailable" in error_section


def test_statistics_page_distinguishes_server_and_mailbox_disabled_states():
    assert "Für dieses Postfach ist kein Statistikmodus aktiviert" in STATISTICS
    assert "Die Statistikfunktion ist serverseitig verfügbar." in STATISTICS
    assert "Statistikstatus ist vorübergehend nicht verfügbar" in STATISTICS


def test_guided_tour_explains_admin_control_for_optional_features():
    assert (
        "Auf diesem Server hat dein Administrator den Hauptadressenschutz nicht aktiviert"
        in TOUR
    )
    assert "Auf diesem Server sind Nutzungsstatistiken vom Administrator deaktiviert" in TOUR
    assert "Statistikmodus und Hauptadressenschutz sind dort nur nutzbar" in TOUR
    assert "Your administrator has not enabled primary-address protection" in TOUR
    assert "Usage statistics are disabled by the administrator" in TOUR
    assert "statisticsServerEnabled" in TOUR
    assert "primaryProtectionStatus" in TOUR


def test_statistics_documentation_has_same_host_enable_steps():
    assert "MOOLIAS_USAGE_STATS=true" in DOCS
    assert "cd /opt/moolias" in DOCS
    assert "docker compose up -d --force-recreate moolias" in DOCS
    assert "Choose a statistics mode" in DOCS
