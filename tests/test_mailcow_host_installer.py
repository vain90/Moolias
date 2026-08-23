from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "install.sh").read_text(encoding="utf-8")
INSTALLER = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.mailcow.yml").read_text(encoding="utf-8")
AUTH = (ROOT / "moolias" / "auth.py").read_text(encoding="utf-8")
CONFIG = (ROOT / "moolias" / "config.py").read_text(encoding="utf-8")


def test_mailcow_compose_has_no_published_application_port():
    assert "    ports:\n" not in COMPOSE
    assert "      - moolias-data:/data" in COMPOSE
    assert "          - moolias-app" in COMPOSE
    assert "    external: true" in COMPOSE
    assert "MAILCOW_DOCKER_NETWORK" in COMPOSE


def test_mailcow_compose_does_not_override_application_connection_urls():
    assert "MAILCOW_PUBLIC_URL" not in COMPOSE
    assert "MAILCOW_URL:" not in COMPOSE
    assert "MAILCOW_INTERNAL_URL:" not in COMPOSE
    assert 'mailcow_internal_url: str = Field(default="", alias="MAILCOW_INTERNAL_URL")' in CONFIG
    assert "def mailcow_backend_url" in CONFIG
    assert "settings.mailcow_url}/oauth/authorize" in AUTH
    assert "backend_url = settings.mailcow_backend_url" in AUTH


def test_installer_bootstrap_prefers_stable_and_has_initial_release_fallback():
    assert "releases/latest" in BOOTSTRAP
    assert "compose.mailcow.yml" in BOOTSTRAP
    assert 'install_ref="$latest_ref"' in BOOTSTRAP
    assert 'install_ref="main"' in BOOTSTRAP
    assert 'MOOLIAS_INSTALL_REF="$install_ref"' in BOOTSTRAP


def test_bootstrap_guides_mailcow_api_allowlist_from_detected_network():
    assert '[[ "$label" == "mailcow-network" ]]' in BOOTSTRAP
    assert ".IPAM.Config" in BOOTSTRAP
    assert "Mailcow API access" in BOOTSTRAP
    assert 'Skip IP check for API' in BOOTSTRAP
    assert "individual Moolias container IP" in BOOTSTRAP


def test_bootstrap_derives_internal_port_from_mailcow_http_port():
    assert 'read_key_value "$mailcow_conf" HTTP_PORT' in BOOTSTRAP
    assert 'mailcow_http_port="80"' in BOOTSTRAP
    assert 'mailcow_internal_url="http://nginx-mailcow:${mailcow_http_port}"' in BOOTSTRAP
    assert "nginx-mailcow:8080 directly" not in BOOTSTRAP


def test_bootstrap_writes_internal_backend_and_sender_agent_urls():
    assert 'set_key_value "$env_file" MAILCOW_INTERNAL_URL "$mailcow_internal_url"' in BOOTSTRAP
    assert "MOOLIAS_SENDER_AGENT_URL" in BOOTSTRAP
    assert '"${mailcow_internal_url}/moolias-agent"' in BOOTSTRAP


def test_bootstrap_validates_api_before_its_final_summary():
    assert "docker compose exec -T moolias python" in BOOTSTRAP
    assert "/api/v1/get/domain/all" in BOOTSTRAP
    assert 'os.environ.get("MAILCOW_INTERNAL_URL")' in BOOTSTRAP
    assert BOOTSTRAP.index("validate_mailcow_api_from_container\n") < BOOTSTRAP.index(
        "print_final_summary\n"
    )
    assert "Mailcow API:       OK" in BOOTSTRAP


def test_bootstrap_suppresses_nested_success_blocks_and_never_reprints_agent_secret():
    assert 'line == "Moolias Mailcow Agent installed successfully"' in BOOTSTRAP
    assert 'line == "Moolias installed successfully"' in BOOTSTRAP
    assert "Agent secret:      saved automatically" in BOOTSTRAP
    assert "MOOLIAS_SENDER_AGENT_SECRET=" not in BOOTSTRAP


def test_bootstrap_waits_for_mailcow_acme_certificate():
    assert "certificate_matches_host" in BOOTSTRAP
    assert "MOOLIAS_TLS_WAIT_SECONDS" in BOOTSTRAP
    assert "Waiting for Mailcow ACME certificate" in BOOTSTRAP
    assert "TLS certificate:   PENDING" in BOOTSTRAP
    assert "Do not bypass the browser certificate warning yet" in BOOTSTRAP


def test_bootstrap_cleanup_does_not_depend_on_local_scope_at_exit():
    assert "printf -v tmp_file_cleanup '%q'" in BOOTSTRAP
    assert "printf -v child_stderr_cleanup '%q'" in BOOTSTRAP
    assert 'trap "rm -f -- ${tmp_file_cleanup} ${child_stderr_cleanup}" EXIT' in BOOTSTRAP
    assert "trap 'rm -f \"$tmp_file\"' EXIT" not in BOOTSTRAP


def test_installer_discovers_mailcow_network_instead_of_assuming_project_name():
    assert "com.docker.compose.network" in INSTALLER
    assert '[[ "$label" == "mailcow-network" ]]' in INSTALLER
    assert "mailcowdockerized_mailcow-network" not in INSTALLER


def test_installer_does_not_modify_mailcow_main_compose_file():
    assert "docker-compose.yml" in INSTALLER
    assert 'set_key_value "$MAILCOW_CONF" ADDITIONAL_SAN' in INSTALLER
    assert 'set_key_value "${MAILCOW_DIR}/docker-compose.yml"' not in INSTALLER
    assert "docker-compose.override.yml" not in INSTALLER


def test_installer_uses_dedicated_nginx_site_and_internal_upstream():
    assert "data/conf/nginx/moolias.conf" in INSTALLER
    assert "proxy_pass http://moolias-app:8000;" in INSTALLER
    assert "The Moolias application has no published host port." in INSTALLER


def test_installer_keeps_secrets_off_standard_output():
    assert "read -r -s value" in INSTALLER
    assert "Secrets were written to ${env_file}" in INSTALLER
    assert "MAILCOW_API_KEY=${api_key}" not in INSTALLER
    assert "MAILCOW_OAUTH_CLIENT_SECRET=${oauth_secret}" not in INSTALLER


def test_installer_supports_curl_pipe_and_noninteractive_mode():
    assert "main() {" in BOOTSTRAP
    assert 'main "$@"' in BOOTSTRAP
    assert "main() {" in INSTALLER
    assert 'main "$@"' in INSTALLER
    assert "exec 3<>/dev/tty" in INSTALLER
    assert "MOOLIAS_NONINTERACTIVE" in INSTALLER
    assert "MOOLIAS_SOURCE_DIR" in INSTALLER
    assert "MOOLIAS_SKIP_PULL" in INSTALLER


def test_installer_refuses_known_nginx_hostname_conflicts():
    assert "ADDITIONAL_SERVER_NAMES" in INSTALLER
    assert "dedicated Moolias nginx server can own that hostname" in INSTALLER


def test_installer_supports_mailcow_acme_without_overwriting_existing_sans():
    assert "append_csv_value" in INSTALLER
    assert "ADDITIONAL_SAN" in INSTALLER
    assert "ONLY_MAILCOW_HOSTNAME" in INSTALLER
    assert "SKIP_LETS_ENCRYPT" in INSTALLER
