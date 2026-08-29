from __future__ import annotations

import functools
import http.server
import os
import subprocess
import tempfile
import threading
from pathlib import Path

import pytest


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


def test_documented_curl_bootstrap_completes_outside_mailcow_dir() -> None:
    mailcow_dir = os.environ.get("MAILCOW_DIR")
    if not mailcow_dir:
        pytest.skip("real Mailcow integration environment is not configured")

    installer = Path(__file__).resolve().parents[1] / "scripts" / "install-mailcow-agent.sh"
    handler = functools.partial(
        _QuietHandler,
        directory=str(installer.parent),
    )
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    env = os.environ.copy()
    env["MAILCOW_DIR"] = mailcow_dir
    env["MOOLIAS_AGENT_IMAGE"] = os.environ.get(
        "MOOLIAS_AGENT_IMAGE",
        "moolias:sender-agent-ci",
    )
    env["MOOLIAS_AGENT_COOLDOWN_SECONDS"] = "1"
    env["MOOLIAS_IMPORT_EXISTING_SENDER_RULES"] = "no"

    port = server.server_address[1]
    env["MOOLIAS_AGENT_CORE_URL"] = (
        f"http://127.0.0.1:{port}/install-mailcow-agent-core.sh"
    )
    command = (
        f"curl -fsSL http://127.0.0.1:{port}/install-mailcow-agent.sh | "
        "sudo --preserve-env="
        "MAILCOW_DIR,MOOLIAS_AGENT_IMAGE,MOOLIAS_AGENT_COOLDOWN_SECONDS,"
        "MOOLIAS_IMPORT_EXISTING_SENDER_RULES,MOOLIAS_AGENT_CORE_URL bash"
    )

    try:
        result = subprocess.run(
            ["bash", "-o", "pipefail", "-c", command],
            cwd=tempfile.gettempdir(),
            check=False,
            text=True,
            capture_output=True,
            env=env,
            timeout=120,
        )
    finally:
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=5)

    assert result.returncode == 0, (
        "Documented curl bootstrap failed:\n"
        f"--- stdout ---\n{result.stdout}\n"
        f"--- stderr ---\n{result.stderr}"
    )
    assert "Moolias Mailcow Agent installed successfully" in result.stdout
    assert "NEXT STEP: Configure Moolias" in result.stdout
    assert "MOOLIAS_MAILCOW_AGENT_SECRET=" in result.stdout
