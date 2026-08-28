from __future__ import annotations

from moolias.config import Settings


def _settings(monkeypatch, *, bypass_seconds: int, monitoring_days: int = 30) -> Settings:
    values = {
        "MOOLIAS_BASE_URL": "https://aliases.example.org",
        "MOOLIAS_SESSION_SECRET": "moolias-test-session-secret-00000001",
        "MOOLIAS_MAILCOW_AGENT_SECRET": "moolias-test-mailcow-agent-secret-0001",
        "MOOLIAS_ALIAS_WORKFLOW_BYPASS_SECONDS": str(bypass_seconds),
        "MOOLIAS_ALIAS_REPLACEMENT_MONITORING_MAX_DAYS": str(monitoring_days),
        "MAILCOW_URL": "https://mail.example.org",
        "MAILCOW_API_KEY": "test-api-key",
        "MAILCOW_OAUTH_CLIENT_ID": "test-client-id",
        "MAILCOW_OAUTH_CLIENT_SECRET": "test-client-secret",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return Settings()  # type: ignore[call-arg]


def test_zero_bypass_uses_replacement_monitoring_limit(monkeypatch):
    settings = _settings(monkeypatch, bypass_seconds=0, monitoring_days=30)

    assert settings.alias_workflow_bypass_seconds == 30 * 86400


def test_zero_bypass_tracks_custom_replacement_monitoring_limit(monkeypatch):
    settings = _settings(monkeypatch, bypass_seconds=0, monitoring_days=45)

    assert settings.alias_workflow_bypass_seconds == 45 * 86400


def test_positive_bypass_keeps_explicit_seconds(monkeypatch):
    settings = _settings(monkeypatch, bypass_seconds=900)

    assert settings.alias_workflow_bypass_seconds == 900
