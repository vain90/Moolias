from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPDATER = (ROOT / "update.sh").read_text(encoding="utf-8")


def test_self_update_does_not_create_script_backup():
    assert 'backup_file="${SCRIPT_PATH}.previous"' not in UPDATER
    assert 'cp -a "${SCRIPT_PATH}"' not in UPDATER
    assert 'rm -f "${SCRIPT_PATH}.previous"' in UPDATER


def test_container_image_rollback_is_still_kept():
    assert 'docker tag "${CURRENT_IMAGE_ID}" "${IMAGE}:previous"' in UPDATER


def test_updater_layers_base_and_local_compose_files():
    assert 'elif [[ -f "compose.yml" && -f "compose.local.yml" ]]; then' in UPDATER
    assert 'COMPOSE_ARGS=(-f "compose.yml" -f "compose.local.yml")' in UPDATER
    assert 'COMPOSE_DISPLAY="compose.yml + compose.local.yml"' in UPDATER
    assert 'docker compose "${COMPOSE_ARGS[@]}" "$@"' in UPDATER


def test_updater_keeps_explicit_compose_file_override():
    assert 'if [[ -n "${MOOLIAS_COMPOSE_FILE:-}" ]]; then' in UPDATER
    assert 'COMPOSE_ARGS=(-f "${MOOLIAS_COMPOSE_FILE}")' in UPDATER


def test_compose_validation_errors_are_not_silenced():
    assert 'compose config --images 2>/dev/null' not in UPDATER
    assert 'Docker Compose validation failed for ${COMPOSE_DISPLAY}' in UPDATER


def test_updater_version_is_0_1_3():
    assert 'UPDATER_VERSION="0.1.3"' in UPDATER
