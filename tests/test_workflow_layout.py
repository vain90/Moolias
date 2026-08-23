from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CI = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
EDGE = (WORKFLOWS / "docker.yml").read_text(encoding="utf-8")
MAILCOW = (WORKFLOWS / "mailcow-integration.yml").read_text(encoding="utf-8")


def test_ci_push_trigger_is_limited_to_main():
    assert "push:\n    branches: [main]" in CI
    assert "pull_request:" in CI


def test_edge_image_workflow_does_not_publish_stable_tags():
    assert "name: Edge image" in EDGE
    assert "tags: ['v*']" not in EDGE
    assert "type=semver" not in EDGE
    assert "moolias:edge" in EDGE


def test_obsolete_mailcow_feasibility_workflow_is_removed():
    assert not (WORKFLOWS / "mailcow-feasibility.yml").exists()


def test_mailcow_integration_tracks_real_contract_files():
    for path in (
        "moolias/mailcow.py",
        "moolias/aliases.py",
        "moolias/stats_mode.py",
        "moolias/config.py",
        "Dockerfile",
    ):
        assert f'- "{path}"' in MAILCOW
