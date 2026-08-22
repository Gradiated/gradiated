#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile


PROJECT = Path(__file__).resolve().parent
OWNER = PROJECT / "run_sm120_norm_fp8_component_owner.py"
ORACLE = PROJECT / "sm120_framework_oracle.py"
PATCH = PROJECT / "implementation" / "vllm026_sm120_norm_fp8_fusion.patch"
INSTALLED_OVERLAY_PATCH = PROJECT / "implementation" / "installed_source_overlay_patch.py"
SOURCE = PROJECT / "VLLM026_SM120_NORM_FP8_FUSION_OFFLINE_RESULT.json"
PREPARATION = PROJECT / "DIRECTOR_VLLM026_SM120_NORM_FP8_COMPONENT_PREPARATION_20260729T0658Z.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_claim_behavior() -> dict[str, bool]:
    spec = importlib.util.spec_from_file_location("component_owner", OWNER)
    assert spec and spec.loader
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    calls: list[list[str]] = []

    def fake_pool(arguments: list[str], timeout: int = 60) -> dict:
        calls.append(arguments)
        if arguments[0] == "claim":
            return {"id": "bound-bench", "claim": {"claimed_at": "2026-07-29T07:12:00Z"}}
        if arguments[0] == "release":
            return {"id": "bound-bench", "claim": None}
        raise AssertionError(arguments)

    owner.pool = fake_pool
    binding = {"bench_id": "bound-bench", "claim_start_by_utc": "2099-01-01T00:00:00Z"}
    generation = owner.claim_exact(binding)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / "OWNER_TERMINAL.json").write_text("{}\n")
        owner.release_generation(binding, generation, {"result_sha256": None}, root, "test")
    source = OWNER.read_text()
    main_start = source.index("def main()")
    return {
        "claim_first": calls[0][:2] == ["claim", "--project"],
        "returned_generation_used_for_release": calls[1][calls[1].index("--expected-claimed-at") + 1] == generation["claimed_at"],
        "claim_before_heartbeat_and_remote": source.index("generation = claim_exact(binding, args.adopt_claimed_at)") < source.index("thread = threading.Thread", source.index("generation = claim_exact(binding, args.adopt_claimed_at)")) < source.index("result = remote(", source.index("generation = claim_exact(binding, args.adopt_claimed_at)")),
        "no_preclaim_timestamp_requirement": "claim_started_at_utc" not in source,
        "stage_before_consumer": source.index("stage_remote_inputs(binding, generation, repair_id)", main_start) < source.index("result = remote(", main_start),
        "complete_terminal_releases": source.index("if payload[\"oracle_complete\"]", main_start) < source.index("release_generation(", source.index("if payload[\"oracle_complete\"]", main_start)),
        "incomplete_retains_before_release": source.index("repair = retain_for_repair", main_start) < source.index("repair_deadline_or_incomplete", main_start),
    }


def main() -> int:
    ast.parse(OWNER.read_text())
    ast.parse(ORACLE.read_text())
    text = OWNER.read_text()
    oracle_text = ORACLE.read_text()
    required = {
        "one_scientific_submission": 'scientific_submission_limit") != 1',
        "resident_runtime": "runtime_python",
        "endpoint_health": "endpoint_health_command",
        "endpoint_driver_census": "endpoint_driver_census_command",
        "preclaim_source_hash": "offline_admission_hash_mismatch",
        "atomic_claim": "def claim_exact",
        "postclaim_stage": "def stage_remote_inputs",
        "installed_package_overlay": "cp -a \"$PKG\" \"$ROOT/overlay/vllm\"",
        "installed_source_adapter": "installed_source_overlay_patch.py",
        "framework_config_wrapper": "framework_oracle_vllm_context.py",
        "all_bound_rows": "--rows 1,32,33,2048",
        "fully_consumed_oracle": "output.float().sum().item()" in oracle_text,
        "same_claim_heartbeat": "gpu_pool",
        "no_endpoint_teardown": "never starts, stops, or reloads",
        "recoverable_incomplete": "recoverable_integration_or_incomplete",
    }
    contract = {
        name: (fragment if isinstance(fragment, bool) else fragment in text)
        for name, fragment in required.items()
    }
    behavior = atomic_claim_behavior()
    payload = {
        "schema_version": 1,
        "classification": "offline_component_owner_validation",
        "owner_sha256": digest(OWNER),
        "oracle_sha256": digest(ORACLE),
        "patch_sha256": digest(PATCH),
        "installed_overlay_patch_sha256": digest(INSTALLED_OVERLAY_PATCH),
        "source_result_sha256": digest(SOURCE),
        "preparation_sha256": digest(PREPARATION),
        "required_contract": contract,
        "atomic_claim_behavior": behavior,
        "detached_command": (
            "/root/workspace/research/factory/tools/detached-owner start --unit-manager pid "
            f"--state {PROJECT}/artifacts/sm120-norm-fp8-component/OWNER_STATE.json "
            f"--log {PROJECT}/artifacts/sm120-norm-fp8-component/OWNER.log -- "
            f"python3 {OWNER} --binding <future-director-execution-binding.json> "
            f"--artifact-root {PROJECT}/artifacts/sm120-norm-fp8-component"
        ),
    }
    payload["passed"] = all(payload["required_contract"].values()) and all(behavior.values())
    target = PROJECT / "artifacts" / "COMPONENT_OWNER_OFFLINE_VALIDATION.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(target)
    print(json.dumps(payload, indent=2))
    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
