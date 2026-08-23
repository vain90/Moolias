from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.mailcow.yml").read_text(encoding="utf-8")


def test_mailcow_compose_has_no_published_application_port():
    rendered = COMPOSE.replace(
        "${MOOLIAS_IMAGE:-ghcr.io/vain90/moolias}",
        "ghcr.io/vain90/moolias",
    ).replace("${MOOLIAS_TAG:-latest}", "latest").replace(
        "${MAILCOW_DOCKER_NETWORK:?MAILCOW_DOCKER_NETWORK is set by the Moolias installer}",
        "mailcowdockerized_mailcow-network",
    )
    config = yaml.safe_load(rendered)
    service = config["services"]["moolias"]

    assert "ports" not in service
    assert service["volumes"] == ["moolias-data:/data"]
    assert service["networks"]["mailcow"]["aliases"] == ["moolias-app"]
    assert config["networks"]["mailcow"]["external"] is True


def test_installer_discovers_mailcow_network_instead_of_assuming_project_name():
    assert 'com.docker.compose.network' in INSTALLER
    assert '[[ "$label" == "mailcow-network" ]]' in INSTALLER
    assert 'mailcowdockerized_mailcow-network' not in INSTALLER


def test_installer_does_not_modify_mailcow_main_compose_file():
    assert 'docker-compose.yml' in INSTALLER
    assert 'set_key_value "$MAILCOW_CONF" ADDITIONAL_SAN' in INSTALLER
    assert 'set_key_value "${MAILCOW_DIR}/docker-compose.yml"' not in INSTALLER
    assert 'docker-compose.override.yml' not in INSTALLER


def test_installer_uses_dedicated_nginx_site_and_internal_upstream():
    assert 'data/conf/nginx/moolias.conf' in INSTALLER
    assert 'proxy_pass http://moolias-app:8000;' in INSTALLER
    assert 'The Moolias application has no published host port.' in INSTALLER


def test_installer_keeps_secrets_off_standard_output():
    assert 'read -r -s value' in INSTALLER
    assert 'Secrets were written to ${env_file}' in INSTALLER
    assert 'printf.*MAILCOW_API_KEY' not in INSTALLER


def test_installer_supports_curl_pipe_and_noninteractive_mode():
    assert 'main() {' in INSTALLER
    assert 'main "$@"' in INSTALLER
    assert 'exec 3<>/dev/tty' in INSTALLER
    assert 'MOOLIAS_NONINTERACTIVE' in INSTALLER
    assert 'MOOLIAS_SOURCE_DIR' in INSTALLER
    assert 'MOOLIAS_SKIP_PULL' in INSTALLER


def test_installer_refuses_known_nginx_hostname_conflicts():
    assert 'ADDITIONAL_SERVER_NAMES' in INSTALLER
    assert 'dedicated Moolias nginx server can own that hostname' in INSTALLER


def test_installer_supports_mailcow_acme_without_overwriting_existing_sans():
    assert 'append_csv_value' in INSTALLER
    assert 'ADDITIONAL_SAN' in INSTALLER
    assert 'ONLY_MAILCOW_HOSTNAME' in INSTALLER
    assert 'SKIP_LETS_ENCRYPT' in INSTALLER
