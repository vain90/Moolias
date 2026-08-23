from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE_WORKFLOW = (ROOT / ".github" / "workflows" / "release.yml").read_text(
    encoding="utf-8"
)


def test_release_workflow_does_not_push_generated_assets_to_main():
    assert "git push origin HEAD:main" not in RELEASE_WORKFLOW
    assert "Commit release service icons when needed" not in RELEASE_WORKFLOW


def test_release_workflow_generates_icons_before_building_image():
    generate_index = RELEASE_WORKFLOW.index("Generate release service icons")
    build_index = RELEASE_WORKFLOW.index("Publish stable container image")
    assert generate_index < build_index


def test_release_workflow_publishes_after_generation_without_icon_state_gate():
    assert "steps.icon_state.outputs.committed" not in RELEASE_WORKFLOW
    assert "if: steps.release_state.outputs.exists != 'true'" in RELEASE_WORKFLOW
