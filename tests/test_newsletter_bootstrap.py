from __future__ import annotations

import os
import subprocess
from pathlib import Path


def test_newsletter_bootstrap_copies_siblings_and_cleans_temp(tmp_path: Path) -> None:
    repository_root = Path(__file__).resolve().parents[1]
    source_dir = tmp_path / "source"
    scripts_dir = source_dir / "scripts"
    rspamd_dir = scripts_dir / "rspamd"
    rspamd_dir.mkdir(parents=True)

    (scripts_dir / "install-newsletter-agent.sh").write_text(
        """#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
[[ -f "${SCRIPT_DIR}/install-newsletter-rspamd.sh" ]]
[[ -f "${SCRIPT_DIR}/rspamd/moolias_newsletter.lua" ]]
printf '%s\\n' "$(dirname -- "${SCRIPT_DIR}")" > "${MOOLIAS_BOOTSTRAP_TEST_OUTPUT}"
""",
        encoding="utf-8",
    )
    (scripts_dir / "install-newsletter-rspamd.sh").write_text(
        "#!/usr/bin/env bash\nset -euo pipefail\nexit 0\n",
        encoding="utf-8",
    )
    (rspamd_dir / "moolias_newsletter.lua").write_text(
        "-- newsletter bootstrap test fixture\n",
        encoding="utf-8",
    )

    result_file = tmp_path / "bootstrap-temp-path.txt"
    env = os.environ.copy()
    env.update(
        {
            "MOOLIAS_SOURCE_DIR": str(source_dir),
            "MOOLIAS_BOOTSTRAP_TEST_OUTPUT": str(result_file),
        }
    )

    completed = subprocess.run(
        ["bash", str(repository_root / "install-newsletter.sh")],
        cwd=repository_root,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Installing Newsletter Management from local-source..." in completed.stdout
    bootstrap_tmp = Path(result_file.read_text(encoding="utf-8").strip())
    assert not bootstrap_tmp.exists()
