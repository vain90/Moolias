from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = ROOT / "install.sh"
INSTALL_DIR = Path("/tmp/moolias-host-install")
MOOLIAS_HOSTNAME = "moolias.mailcow-ci.test"


def _run(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        cwd=cwd,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    if result.returncode != 0:
        if result.stdout:
            print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
        result.check_returncode()
    return result


def _mailcow_compose(*args: str) -> subprocess.CompletedProcess[str]:
    return _run("docker", "compose", *args, cwd=Path(os.environ["MAILCOW_DIR"]))


def _installed_compose(*args: str) -> subprocess.CompletedProcess[str]:
    return _run("sudo", "docker", "compose", *args, cwd=INSTALL_DIR)


def _mailcow_network() -> str:
    nginx_id = _mailcow_compose("ps", "-q", "nginx-mailcow").stdout.strip()
    assert nginx_id
    networks = _run(
        "docker",
        "inspect",
        "--format",
        "{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}",
        nginx_id,
    ).stdout.splitlines()
    for network in networks:
        label = _run(
            "docker",
            "network",
            "inspect",
            "--format",
            '{{index .Labels "com.docker.compose.network"}}',
            network,
        ).stdout.strip()
        if label == "mailcow-network":
            return network
    raise AssertionError("Mailcow network was not found")


def _network_ipv4_cidrs(network: str) -> list[str]:
    subnets = _run(
        "docker",
        "network",
        "inspect",
        "--format",
        "{{range .IPAM.Config}}{{println .Subnet}}{{end}}",
        network,
    ).stdout.splitlines()
    return [subnet for subnet in subnets if subnet and ":" not in subnet]


@pytest.mark.skipif(
    os.environ.get("MOOLIAS_TEST_SCENARIO") != "fresh",
    reason="run the full host installer only once per Mailcow matrix",
)
def test_recommended_mailcow_host_installer() -> None:
    mailcow_dir = Path(os.environ["MAILCOW_DIR"])
    mailcow_conf = mailcow_dir / "mailcow.conf"
    nginx_custom = mailcow_dir / "data" / "conf" / "nginx" / "moolias.conf"
    override_file = mailcow_dir / "docker-compose.override.yml"

    mailcow_conf_before = mailcow_conf.read_bytes()
    override_before = override_file.read_bytes() if override_file.exists() else None

    if INSTALL_DIR.exists():
        subprocess.run(["sudo", "rm", "-rf", str(INSTALL_DIR)], check=True)
    if nginx_custom.exists():
        subprocess.run(["sudo", "rm", "-f", str(nginx_custom)], check=True)

    network = _mailcow_network()
    ipv4_cidrs = _network_ipv4_cidrs(network)
    assert ipv4_cidrs
    public_mailcow_url = f"http://{os.environ['MAILCOW_HOSTNAME']}:8080"

    command = [
        "sudo",
        "env",
        "MOOLIAS_NONINTERACTIVE=true",
        f"MOOLIAS_SOURCE_DIR={ROOT}",
        "MOOLIAS_INSTALL_REF=integration-test",
        f"MOOLIAS_INSTALL_DIR={INSTALL_DIR}",
        "MOOLIAS_IMAGE_REPOSITORY=moolias",
        "MOOLIAS_IMAGE_TAG=sender-agent-ci",
        "MOOLIAS_SKIP_PULL=true",
        f"MOOLIAS_BASE_URL=http://{MOOLIAS_HOSTNAME}:8080",
        f"MAILCOW_URL={public_mailcow_url}",
        f"MAILCOW_API_KEY={os.environ['MAILCOW_API_KEY']}",
        "MAILCOW_OAUTH_CLIENT_ID=integration-client",
        "MAILCOW_OAUTH_CLIENT_SECRET=integration-secret",
        "MOOLIAS_TLS_MODE=none",
        "MOOLIAS_INSTALL_SENDER_PROTECTION=no",
        f"MAILCOW_DIR={mailcow_dir}",
        "bash",
        str(BOOTSTRAP),
    ]

    try:
        result = _run(*command, cwd=ROOT)
        assert "Mailcow API access" in result.stdout
        assert network in result.stdout
        for cidr in ipv4_cidrs:
            assert cidr in result.stdout
        assert 'Skip IP check for API' in result.stdout
        assert "nginx-mailcow:8080" in result.stdout
        assert "Moolias installed successfully" in result.stdout
        assert "Mailcow API access from Moolias container: OK" in result.stdout
        assert "The Moolias application has no published host port." in result.stdout

        assert (INSTALL_DIR / "compose.yml").is_file()
        assert (INSTALL_DIR / "update.sh").is_file()
        assert (INSTALL_DIR / ".moolias-mailcow-install").is_file()
        assert stat.S_IMODE((INSTALL_DIR / ".env").stat().st_mode) == 0o600

        container_id = _installed_compose("ps", "-q", "moolias").stdout.strip()
        assert container_id

        port_bindings = _run(
            "docker",
            "inspect",
            "--format",
            "{{json .HostConfig.PortBindings}}",
            container_id,
        ).stdout.strip()
        assert port_bindings in {"{}", "null"}

        attached_networks = _run(
            "docker",
            "inspect",
            "--format",
            "{{range $name, $_ := .NetworkSettings.Networks}}{{println $name}}{{end}}",
            container_id,
        ).stdout.splitlines()
        assert network in attached_networks

        health = _run(
            "docker",
            "inspect",
            "--format",
            "{{.State.Health.Status}}",
            container_id,
        ).stdout.strip()
        assert health == "healthy"

        runtime_urls = _installed_compose(
            "exec",
            "-T",
            "moolias",
            "python",
            "-c",
            (
                "import os; "
                "print(os.environ.get('MAILCOW_URL', '')); "
                "print(os.environ.get('MAILCOW_PUBLIC_URL', ''))"
            ),
        ).stdout.splitlines()
        assert runtime_urls == ["http://nginx-mailcow:8080", public_mailcow_url]

        response = _run(
            "curl",
            "--noproxy",
            "*",
            "--fail",
            "--silent",
            "--show-error",
            "--resolve",
            f"{MOOLIAS_HOSTNAME}:8080:127.0.0.1",
            f"http://{MOOLIAS_HOSTNAME}:8080/healthz",
        ).stdout
        assert response

        assert nginx_custom.is_file()
        assert "Managed by Moolias Mailcow installer" in nginx_custom.read_text(
            encoding="utf-8"
        )
        assert mailcow_conf.read_bytes() == mailcow_conf_before
        if override_before is None:
            assert not override_file.exists()
        else:
            assert override_file.read_bytes() == override_before
    finally:
        if (INSTALL_DIR / "compose.yml").exists():
            subprocess.run(
                ["sudo", "docker", "compose", "down", "-v", "--remove-orphans"],
                cwd=INSTALL_DIR,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        subprocess.run(["sudo", "rm", "-rf", str(INSTALL_DIR)], check=False)
        subprocess.run(["sudo", "rm", "-f", str(nginx_custom)], check=False)
        subprocess.run(
            [
                "docker",
                "compose",
                "exec",
                "-T",
                "nginx-mailcow",
                "nginx",
                "-s",
                "reload",
            ],
            cwd=mailcow_dir,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
