from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "scripts" / "install-mailcow-agent.sh").read_text(encoding="utf-8")


def test_first_delivery_bypass_uses_exact_dynamic_recipient_map():
    assert (
        "MOOLIAS_AGENT_BYPASS_MAP_PATH=/rspamd-custom/"
        "moolias_firstmail_recipients.map"
    ) in INSTALLER
    assert "./data/conf/rspamd/custom/moolias-agent:/rspamd-custom" in INSTALLER
    assert (
        "file:///etc/rspamd/custom/moolias-agent/"
        "moolias_firstmail_recipients.map"
    ) in INSTALLER
    assert 'local recipients = task:get_recipients("smtp")' in INSTALLER
    assert "#recipients ~= 1" in INSTALLER
    assert "recipient_map:get_key(string.lower(recipient))" in INSTALLER


def test_first_delivery_bypass_disables_only_greylisting_symbols():
    disabled_lines = [
        line.strip()
        for line in INSTALLER.splitlines()
        if "task:disable_symbol(" in line
    ]
    assert disabled_lines == [
        'task:disable_symbol("GREYLIST_CHECK")',
        'task:disable_symbol("GREYLIST_SAVE")',
    ]
    assert "disable_all_symbols" not in INSTALLER
    assert "set_pre_result" not in INSTALLER


def test_rspamd_restart_restores_agent_map_permissions_and_validates_config():
    assert "Managed by Moolias First Mail Delivery" in INSTALLER
    assert (
        "chown 10001:10001 /etc/rspamd/custom/moolias-agent/"
        "moolias_firstmail_recipients.map"
    ) in INSTALLER
    assert "docker compose exec -T rspamd-mailcow rspamadm configtest" in INSTALLER
    assert "docker compose exec -T moolias-agent test -w /rspamd-custom" in INSTALLER
