from pathlib import Path

import build_clean_materialization as build


def test_payload_policy_is_explicit_and_disjoint_from_controls():
    assert len(build.PAYLOAD_NAMES) == 12
    assert not set(build.PAYLOAD_NAMES) & set(build.CONTROL_NAMES)
    assert "minimal_depth_checkpoint_manifest.json" not in build.PAYLOAD_NAMES


def test_frozen_root_is_not_the_v2_output_namespace():
    assert build.FROZEN_ROOT.name != "glm47flash-awq-minimal-depth42-v2"
    assert build.SOURCE != build.FROZEN_ROOT
