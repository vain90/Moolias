from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = (ROOT / "update.sh").read_text(encoding="utf-8")
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")


def test_self_update_does_not_create_script_backup():
    assert 'backup_file="${SCRIPT_PATH}.previous"' not in UPDATER
    assert 'cp -a "${SCRIPT_PATH}"' not in UPDATER
    assert 'rm -f "${SCRIPT_PATH}.previous"' in UPDATER


def test_container_image_rollback_is_still_kept():
    assert 'docker tag "${CURRENT_IMAGE_ID}" "${IMAGE}:previous"' in UPDATER


def test_repository_reserves_compose_local_for_operator_overrides():
    assert not (ROOT / "compose.local.yml").exists()
    assert (ROOT / "compose.dev.yml").exists()


def test_updater_layers_base_and_local_compose_files():
    assert 'elif [[ -f "compose.yml" && -f "compose.local.yml" ]]; then' in UPDATER
    assert 'COMPOSE_ARGS=(-f "compose.yml" -f "compose.local.yml")' in UPDATER
    assert 'COMPOSE_DISPLAY="compose.yml + compose.local.yml"' in UPDATER
    assert 'docker compose "${COMPOSE_ARGS[@]}" "$@"' in UPDATER


def test_updater_ignores_legacy_stock_development_compose_file():
    assert "is_legacy_stock_dev_compose()" in UPDATER
    assert 'image: moolias:local' in UPDATER
    assert 'COMPOSE_ARGS=(-f "compose.yml")' in UPDATER
    assert 'legacy development compose.local.yml ignored' in UPDATER


def test_updater_keeps_explicit_compose_file_override():
    assert 'if [[ -n "${MOOLIAS_COMPOSE_FILE:-}" ]]; then' in UPDATER
    assert 'COMPOSE_ARGS=(-f "${MOOLIAS_COMPOSE_FILE}")' in UPDATER


def test_compose_validation_errors_are_not_silenced():
    assert 'compose config --images 2>/dev/null' not in UPDATER
    assert 'Docker Compose validation failed for ${COMPOSE_DISPLAY}' in UPDATER


def test_updater_requires_mailcow_agent_before_recreating_application():
    assert "MOOLIAS_MAILCOW_AGENT_SECRET" in UPDATER
    assert ".moolias-mailcow-install" in UPDATER
    assert UPDATER.index('agent_secret="$(sed -n') < UPDATER.index(
        'if [[ "${ASSUME_YES}" != true ]]'
    )
    assert UPDATER.index('agent_secret="$(sed -n') < UPDATER.index(
        'compose up -d --force-recreate --remove-orphans moolias'
    )


def test_beta_agent_migration_guidance_keeps_main_and_edge_together():
    assert (
        "MOOLIAS_INSTALL_REF=main MOOLIAS_IMAGE_TAG=edge bash"
        in UPDATER
    )
    assert (
        'migration_command="curl -fsSL '
        'https://raw.githubusercontent.com/vain90/Moolias/main/install.sh | sudo bash"'
        in UPDATER
    )


def test_docker_healthcheck_remains_liveness_only():
    assert "http://127.0.0.1:8000/healthz" in DOCKERFILE
    assert "/readyz" not in DOCKERFILE


def test_updater_waits_for_application_readiness():
    assert "container_ready()" in UPDATER
    assert "http://127.0.0.1:8000/readyz" in UPDATER
    assert "wait_for_ready()" in UPDATER
    assert 'if [[ "${state}" == "running" ]] && container_ready "${container_id}"; then' in UPDATER
    assert "Readiness check: OK" in UPDATER
    assert "did not become ready" in UPDATER


def test_updater_uses_readiness_for_update_and_rollback():
    assert UPDATER.count("if wait_for_ready; then") == 2
    assert "Rollback readiness check: OK" in UPDATER
    assert "wait_for_healthy" not in UPDATER


def test_stable_channel_uses_resolved_semver_image_tag():
    stable_start = UPDATER.index('else\n  CHANNEL="stable"')
    stable_end = UPDATER.index("\nfi\n\nself_update()", stable_start)
    stable_block = UPDATER[stable_start:stable_end]

    assert 'LATEST_VERSION="${LATEST_TAG#v}"' in stable_block
    assert 'TARGET_TAG="${LATEST_VERSION}"' in stable_block
    assert 'TARGET_TAG="latest"' not in stable_block
    assert 'TARGET_TAG="edge"' in UPDATER
    assert 'log "Pulling ${IMAGE}:${TARGET_TAG}..."' in UPDATER
    assert 'log "Pulling ${IMAGE}:latest..."' not in UPDATER


def test_stable_version_is_verified_after_readiness_before_success():
    readiness = UPDATER.index("if wait_for_ready; then")
    version_read = UPDATER.index('UPDATED_VERSION="$(container_version', readiness)
    version_check = UPDATER.index(
        'if [[ "${BETA}" != true && "${UPDATED_VERSION}" != "${LATEST_VERSION}" ]]; then',
        version_read,
    )
    success = UPDATER.index('log "Readiness check: OK"', version_check)
    rollback = UPDATER.index('log "Rolling back to the previously running image..."', success)

    assert readiness < version_read < version_check < success < rollback
    assert (
        'UPDATE_FAILURE="The updated Moolias container reports version '
        '${UPDATED_VERSION:-unknown}, expected ${LATEST_VERSION}."'
        in UPDATER
    )
    assert 'error "${UPDATE_FAILURE}"' in UPDATER


def test_updater_version_is_0_1_7():
    assert 'UPDATER_VERSION="0.1.7"' in UPDATER
