from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
INSTALL_DOC = (ROOT / "docs" / "install-on-mailcow.md").read_text(encoding="utf-8")
SENDER_DOC = (ROOT / "docs" / "sender-protection.md").read_text(encoding="utf-8")
NEWSLETTER_DOC = (ROOT / "docs" / "newsletter-management.md").read_text(encoding="utf-8")


def test_same_host_agent_routing_docs_match_direct_docker_urls():
    for source in (ENV_EXAMPLE, INSTALL_DOC, SENDER_DOC):
        assert "http://moolias-agent:8081" in source
    for source in (ENV_EXAMPLE, INSTALL_DOC, NEWSLETTER_DOC):
        assert "http://moolias-newsletter-agent:8082" in source

    assert "MOOLIAS_MAILCOW_AGENT_URL=http://nginx-mailcow:80/moolias-agent" not in INSTALL_DOC
    assert (
        "MOOLIAS_NEWSLETTER_AGENT_URL=http://nginx-mailcow:80/moolias-newsletter-agent"
        not in INSTALL_DOC
    )
    assert "configures the private Mailcow-nginx URL" not in SENDER_DOC
