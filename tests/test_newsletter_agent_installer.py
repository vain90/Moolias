from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "scripts" / "install-newsletter-agent.sh").read_text(
    encoding="utf-8"
)


def test_newsletter_agent_installer_uses_direct_sidecar_url():
    assert '"MOOLIAS_NEWSLETTER_AGENT_URL"' in INSTALLER
    assert '"http://moolias-newsletter-agent:8082"' in INSTALLER
    assert '${mailcow_internal_url}/moolias-newsletter-agent' not in INSTALLER
    assert "networks:\n      - mailcow-network" in INSTALLER
