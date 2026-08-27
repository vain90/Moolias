from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = (ROOT / "install.sh").read_text(encoding="utf-8")
INSTALLER = (ROOT / "scripts" / "install.sh").read_text(encoding="utf-8")
COMPOSE = (ROOT / "compose.mailcow.yml").read_text(encoding="utf-8")
ENV_EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
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
    assert 'MOOLIAS_INSTALL_REF=${install_ref}' in BOOTSTRAP


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
    assert "MOOLIAS_MAILCOW_AGENT_URL" in BOOTSTRAP
    assert '"${mailcow_internal_url}/moolias-agent"' in BOOTSTRAP


def test_bootstrap_validates_api_before_its_final_summary():
    assert "docker compose exec -T moolias python" in BOOTSTRAP
    assert "/api/v1/get/domain/all" in BOOTSTRAP
    assert 'os.environ.get("MAILCOW_INTERNAL_URL")' in BOOTSTRAP
    assert BOOTSTRAP.index("validate_mailcow_api_from_container\n") < BOOTSTRAP.index(
        "print_final_summary\n"
    )
    assert "Mailcow API:       OK" in BOOTSTRAP


def test_bootstrap_reports_mailcow_api_rejection_reason():
    assert 'payload.get("msg", "")' in BOOTSTRAP
    assert "Mailcow API rejected the request:" in BOOTSTRAP
    assert "If Mailcow reports a source IP outside these networks" in BOOTSTRAP


def test_bootstrap_suppresses_nested_success_blocks_and_never_reprints_agent_secret():
    assert 'line == "Moolias Mailcow Agent installed successfully"' in BOOTSTRAP
    assert 'line == "Moolias installed successfully"' in BOOTSTRAP
    assert "Agent secret:      saved automatically" in BOOTSTRAP
    assert "MOOLIAS_SENDER_AGENT_SECRET=" not in BOOTSTRAP


def test_bootstrap_preserves_existing_sender_protection_on_rerun():
    assert "resolve_sender_install_mode" in BOOTSTRAP
    assert 'read_key_value "$env_file" MOOLIAS_SENDER_PROTECTION' in BOOTSTRAP
    assert 'sender_install_mode="no"' in BOOTSTRAP
    assert '"MOOLIAS_INSTALL_SENDER_PROTECTION=${sender_install_mode}"' in BOOTSTRAP


def test_bootstrap_filters_successful_nginx_chatter_from_later_failures():
    assert "print_child_failure" in BOOTSTRAP
    assert "/nginx: \\[warn\\]/ { next }" in BOOTSTRAP
    assert "/nginx: configuration file .* test is successful/ { next }" in BOOTSTRAP


def test_bootstrap_waits_for_mailcow_acme_certificate_with_visible_progress():
    assert "certificate_matches_host" in BOOTSTRAP
    assert "MOOLIAS_TLS_WAIT_SECONDS" in BOOTSTRAP
    assert 'run_progress "Checking Mailcow TLS certificate"' in BOOTSTRAP
    assert "TLS certificate:   PENDING" in BOOTSTRAP
    assert "Do not bypass the browser certificate warning yet" in BOOTSTRAP


def test_bootstrap_preserves_tls_status_from_progress_subshell():
    assert 'local tls_status_file=""' in BOOTSTRAP
    assert "record_tls_status()" in BOOTSTRAP
    assert 'record_tls_status "ok"' in BOOTSTRAP
    assert 'record_tls_status "pending"' in BOOTSTRAP
    assert 'tls_status="$(tail -n1 "$tls_status_file")"' in BOOTSTRAP


def test_bootstrap_cleanup_does_not_depend_on_local_scope_at_exit():
    assert "printf -v tmp_file_cleanup '%q'" in BOOTSTRAP
    assert "printf -v child_stdout_cleanup '%q'" in BOOTSTRAP
    assert "printf -v child_stderr_cleanup '%q'" in BOOTSTRAP
    assert "printf -v tls_status_file_cleanup '%q'" in BOOTSTRAP
    trap_line = (
        'trap "rm -f -- ${tmp_file_cleanup} ${child_stdout_cleanup} '
        '${child_stderr_cleanup} ${tls_status_file_cleanup}" EXIT'
    )
    assert trap_line in BOOTSTRAP
    assert "trap 'rm -f \"$tmp_file\"' EXIT" not in BOOTSTRAP


def test_bootstrap_has_six_page_interactive_setup_wizard():
    assert "Moolias Setup" in BOOTSTRAP
    assert 'setup_page 1 "Public URL"' in BOOTSTRAP
    assert 'setup_page 2 "Mailcow API"' in BOOTSTRAP
    assert 'setup_page 3 "OAuth"' in BOOTSTRAP
    assert 'setup_page 4 "Access control"' in BOOTSTRAP
    assert 'setup_page 5 "TLS certificate"' in BOOTSTRAP
    assert 'setup_page 6 "Primary sender protection"' in BOOTSTRAP
    assert "clear_setup_screen" in BOOTSTRAP


def test_bootstrap_recommends_access_tag_and_sender_protection():
    assert "Recommended: moolias-access" in BOOTSTRAP
    assert 'access_tag="moolias-access"' in BOOTSTRAP
    assert 'set_key_value "$env_file" MOOLIAS_ACCESS_TAG "$access_tag"' in BOOTSTRAP
    assert 'prompt_yes_no \'Enable access restriction with "moolias-access"?\' "yes"' in BOOTSTRAP
    assert 'prompt_yes_no "Install primary sender protection?" "yes"' in BOOTSTRAP
    assert "Example: MOOLIAS_ACCESS_TAG=moolias-access" in ENV_EXAMPLE


def test_bootstrap_keeps_terminal_alive_during_long_install_steps():
    assert "run_progress()" in BOOTSTRAP
    assert "Installing Moolias and applying Mailcow/ACME changes" in BOOTSTRAP
    assert "Applying final private-network and access settings" in BOOTSTRAP
    assert "Validating Mailcow API access" in BOOTSTRAP
    assert "Checking Mailcow TLS certificate" in BOOTSTRAP


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


def test_installer_keeps_mailcow_http01_challenge_out_of_moolias_proxy():
    assert "    root /web;" in INSTALLER
    assert "    location ^~ /.well-known/acme-challenge/ {" in INSTALLER
    assert '        default_type "text/plain";' in INSTALLER
    assert "    location / {\n${http_behavior}\n" in INSTALLER


def test_installer_recreates_acme_container_after_additional_san_change():
    assert "mailcow_compose up -d --no-deps --force-recreate acme-mailcow" in INSTALLER
    assert "mailcow_compose restart acme-mailcow" not in INSTALLER


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


def test_installer_preserves_explicit_sender_rule_import_choice_without_tty():
    assert (
        'MOOLIAS_IMPORT_EXISTING_SENDER_RULES="${MOOLIAS_IMPORT_EXISTING_SENDER_RULES:-no}"'
        in INSTALLER
    )


def test_installer_refuses_known_nginx_hostname_conflicts():
    assert "ADDITIONAL_SERVER_NAMES" in INSTALLER
    assert "dedicated Moolias nginx server can own that hostname" in INSTALLER


def test_installer_supports_mailcow_acme_without_overwriting_existing_sans():
    assert "append_csv_value" in INSTALLER
    assert "ADDITIONAL_SAN" in INSTALLER
    assert "ONLY_MAILCOW_HOSTNAME" in INSTALLER
    assert "SKIP_LETS_ENCRYPT" in INSTALLER
