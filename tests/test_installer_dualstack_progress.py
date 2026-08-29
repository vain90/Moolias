from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_WRAPPER = (ROOT / "install.sh").read_text(encoding="utf-8")
BOOTSTRAP_CORE = (ROOT / "scripts" / "install-bootstrap-core.sh").read_text(encoding="utf-8")
BOOTSTRAP = BOOTSTRAP_WRAPPER + "\n" + BOOTSTRAP_CORE


def test_progress_spinner_frames_are_single_width():
    lines = BOOTSTRAP.splitlines()

    assert "    local -a frames=('|' '/' '-' $'\\\\')" in lines
    assert "    local -a frames=('|' '/' '-' '\\\\')" not in lines


def test_mailcow_api_allowlist_keeps_ipv4_and_ipv6_subnets():
    assert '  local detected_cidrs=""' in BOOTSTRAP
    assert 'detected_ipv4_cidrs' not in BOOTSTRAP
    assert '[[ "$subnet" == *:* ]] && continue' not in BOOTSTRAP
    assert 'detected_cidrs+="${detected_cidrs:+ }${subnet}"' in BOOTSTRAP
    assert BOOTSTRAP.count('for cidr in $detected_cidrs; do') >= 3


def test_mailcow_api_failure_guidance_mentions_detected_docker_cidrs():
    assert "The Mailcow read/write API key should allow these Docker network CIDRs:" in BOOTSTRAP
    assert "If Mailcow reports a source IP outside these networks" in BOOTSTRAP
