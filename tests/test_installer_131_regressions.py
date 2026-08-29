from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALL_WRAPPER = ROOT / "install.sh"
AGENT_WRAPPER = ROOT / "scripts" / "install-mailcow-agent.sh"


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "docker.log"
    _write_executable(
        bin_dir / "docker",
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'printf \'%s\\n\' "$*" >> "$DOCKER_LOG"\n',
    )
    return bin_dir, log


def _fake_agent_core(tmp_path: Path) -> Path:
    core = tmp_path / "agent-core.sh"
    _write_executable(
        core,
        """#!/usr/bin/env bash
set -euo pipefail
POSTFIX_HOOK_DIR="${MAILCOW_DIR}/data/hooks/postfix"
RSPAMD_HOOK_DIR="${MAILCOW_DIR}/data/hooks/rspamd"
stamp=teststamp
stale_postfix="$POSTFIX_HOOK_DIR/moolias-old.before-moolias-agent-old.bak"
stale_rspamd="$RSPAMD_HOOK_DIR/moolias-old.before-moolias-agent-old.bak"
[[ ! -x "$stale_postfix" ]]
[[ ! -x "$stale_rspamd" ]]
backup_file() {
  local path="$1"
  if [[ -e "$path" ]]; then
    cp -a "$path" "${path}.before-moolias-agent-${stamp}.bak"
  fi
}
hook="$POSTFIX_HOOK_DIR/moolias-sender-protection.sh"
printf '#!/usr/bin/env bash\\nexit 0\\n' > "$hook"
chmod 0755 "$hook"
backup_file "$hook"
[[ ! -x "${hook}.before-moolias-agent-${stamp}.bak" ]]
""",
    )
    return core


def _run_agent_wrapper(tmp_path: Path, image: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    mailcow_dir = tmp_path / "mailcow"
    postfix_hooks = mailcow_dir / "data" / "hooks" / "postfix"
    rspamd_hooks = mailcow_dir / "data" / "hooks" / "rspamd"
    postfix_hooks.mkdir(parents=True)
    rspamd_hooks.mkdir(parents=True)

    stale_postfix = postfix_hooks / "moolias-old.before-moolias-agent-old.bak"
    stale_rspamd = rspamd_hooks / "moolias-old.before-moolias-agent-old.bak"
    _write_executable(stale_postfix, "#!/bin/sh\n")
    _write_executable(stale_rspamd, "#!/bin/sh\n")

    bin_dir, docker_log = _fake_docker(tmp_path)
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{bin_dir}:{env['PATH']}",
            "DOCKER_LOG": str(docker_log),
            "MAILCOW_DIR": str(mailcow_dir),
            "MOOLIAS_AGENT_IMAGE": image,
            "MOOLIAS_AGENT_CORE_PATH": str(_fake_agent_core(tmp_path)),
        }
    )

    result = subprocess.run(
        ["bash", str(AGENT_WRAPPER)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(stale_postfix.stat().st_mode) == 0o644
    assert stat.S_IMODE(stale_rspamd.stat().st_mode) == 0o644

    new_backup = postfix_hooks / (
        "moolias-sender-protection.sh.before-moolias-agent-teststamp.bak"
    )
    assert new_backup.is_file()
    assert stat.S_IMODE(new_backup.stat().st_mode) == 0o644
    return result, docker_log


def test_agent_wrapper_refreshes_registry_images_and_disables_hook_backups(tmp_path: Path) -> None:
    _, docker_log = _run_agent_wrapper(tmp_path, "ghcr.io/vain90/moolias:latest")
    assert "pull ghcr.io/vain90/moolias:latest" in docker_log.read_text(encoding="utf-8")


def test_agent_wrapper_keeps_local_development_images_without_forced_pull(tmp_path: Path) -> None:
    _, docker_log = _run_agent_wrapper(tmp_path, "moolias:local-test")
    content = docker_log.read_text(encoding="utf-8") if docker_log.exists() else ""
    assert "pull moolias:local-test" not in content


def test_main_wrapper_can_install_newsletter_management_in_same_run(tmp_path: Path) -> None:
    base_core = tmp_path / "base-core.sh"
    newsletter = tmp_path / "newsletter.sh"
    install_dir = tmp_path / "moolias"
    log = tmp_path / "install.log"

    _write_executable(
        base_core,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'mkdir -p "$MOOLIAS_INSTALL_DIR"\n'
        'touch "$MOOLIAS_INSTALL_DIR/.env"\n'
        'echo base >> "$MOOLIAS_TEST_LOG"\n',
    )
    _write_executable(
        newsletter,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'echo "newsletter:${MOOLIAS_DIR}" >> "$MOOLIAS_TEST_LOG"\n',
    )

    env = os.environ.copy()
    env.update(
        {
            "MOOLIAS_INSTALL_DIR": str(install_dir),
            "MOOLIAS_BOOTSTRAP_CORE_PATH": str(base_core),
            "MOOLIAS_NEWSLETTER_INSTALLER_PATH": str(newsletter),
            "MOOLIAS_INSTALL_NEWSLETTER": "yes",
            "MOOLIAS_NONINTERACTIVE": "true",
            "MOOLIAS_TEST_LOG": str(log),
        }
    )

    result = subprocess.run(
        ["bash", str(INSTALL_WRAPPER)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "base",
        f"newsletter:{install_dir}",
    ]


def test_main_wrapper_keeps_newsletter_disabled_by_default_when_unattended(tmp_path: Path) -> None:
    base_core = tmp_path / "base-core.sh"
    newsletter = tmp_path / "newsletter.sh"
    install_dir = tmp_path / "moolias"
    log = tmp_path / "install.log"

    _write_executable(
        base_core,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'mkdir -p "$MOOLIAS_INSTALL_DIR"\n'
        'touch "$MOOLIAS_INSTALL_DIR/.env"\n'
        'echo base >> "$MOOLIAS_TEST_LOG"\n',
    )
    _write_executable(
        newsletter,
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        'echo newsletter >> "$MOOLIAS_TEST_LOG"\n',
    )

    env = os.environ.copy()
    env.update(
        {
            "MOOLIAS_INSTALL_DIR": str(install_dir),
            "MOOLIAS_BOOTSTRAP_CORE_PATH": str(base_core),
            "MOOLIAS_NEWSLETTER_INSTALLER_PATH": str(newsletter),
            "MOOLIAS_INSTALL_NEWSLETTER": "ask",
            "MOOLIAS_NONINTERACTIVE": "true",
            "MOOLIAS_TEST_LOG": str(log),
        }
    )

    result = subprocess.run(
        ["bash", str(INSTALL_WRAPPER)],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == ["base"]
