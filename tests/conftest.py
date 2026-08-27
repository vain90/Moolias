import pytest


@pytest.fixture(autouse=True)
def isolate_persistent_database(monkeypatch, tmp_path):
    monkeypatch.setenv(
        "MOOLIAS_USAGE_DB_PATH",
        str(tmp_path / "moolias-test.sqlite3"),
    )
    monkeypatch.setenv(
        "MOOLIAS_MAILCOW_AGENT_SECRET",
        "moolias-test-mailcow-agent-secret-0001",
    )
