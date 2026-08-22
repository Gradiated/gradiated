from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_binding_is_complete_and_distinct() -> None:
    binding = json.loads(
        (ROOT / "B200_FP8_M32_NEXT_MECHANISM.json").read_text()
    )
    assert binding["classification"].endswith("_unmeasured")
    assert binding["mechanism"]["candidate_scheduler_tag"] == (
        "cutlass::gemm::StaticPersistentScheduler"
    )
    assert "M16" not in (
        ROOT / "m32_static_persistent_extension.cu"
    ).read_text()
    assert len(binding["production_geometry"]["families"]) == 6
    assert sum(
        row["multiplicity_per_decode_step"]
        for row in binding["production_geometry"]["families"]
    ) == 240
    assert binding["oracle"]["expected_rows"] == 6
    assert binding["lifecycle"]["claim_allowed_now"] is False
    assert binding["lifecycle"]["repair_contract"][
        "retains_claim_and_heartbeat"
    ]
    for field, filename in {
        "candidate_source_sha256": "m32_static_persistent_extension.cu",
        "build_script_sha256": "m32_static_scheduler_build.py",
        "runner_sha256": "b200_m32_static_scheduler_component.py",
        "owner_sha256": "b200_m32_static_scheduler_owner.py",
        "dockerfile_sha256": "m32_static_scheduler.Dockerfile",
    }.items():
        assert binding["artifact_hashes"][field] == digest(ROOT / filename)


def test_runner_binds_production_quantizers_and_resume() -> None:
    runner = (
        ROOT / "b200_m32_static_scheduler_component.py"
    ).read_text()
    assert "use_per_token_if_dynamic=True" in runner
    assert "weight_nk.t()" in runner
    assert "bitwise_equal" in runner
    assert "--resume" in runner
    assert "ROW_{name}.json" in runner


def test_owner_has_separate_repair_and_release_paths() -> None:
    owner = (ROOT / "b200_m32_static_scheduler_owner.py").read_text()
    assert '"repair_wait"' in owner
    assert "wait_for_repair" in owner
    assert "execute_scope" in owner
    assert 'self.release("available", terminal)' in owner
    assert 'self.release("maintenance", terminal)' in owner
    assert "finally" in owner
    finally_block = owner.rsplit("finally:", 1)[1]
    assert "self.release(" not in finally_block
