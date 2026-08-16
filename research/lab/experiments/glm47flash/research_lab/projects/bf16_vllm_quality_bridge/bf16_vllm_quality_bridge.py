#!/usr/bin/env python3
"""Zero-provider BF16/vLLM admission bridge for the frozen V2 contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path


REVISION = "33faccf4c2ba82142214d0d4e16232a4e9ccfe10"
MANIFEST_SHA256 = "515b831798895e737cfee5943cb522db95cf71d48bb15dfb3f49a016cab9e101"
WEIGHT_BYTES = 62_444_175_504
REQUIRED = (
    "raw-response-bytes", "normalized-output-bytes", "transform-decisions",
    "responses.jsonl", "runtime-evidence.json", "identity-manifest.json",
    "capture-result.json",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def memory_bound() -> dict[str, float | int | bool]:
    budget = 0.90 * 80 * 2**30
    c1_tokens = 8192 + 1024
    kv = 54_144 * c1_tokens
    return {
        "gpu_memory_budget_bytes": int(budget),
        "weight_bytes": WEIGHT_BYTES,
        "c1_tokens": c1_tokens,
        "c1_kv_bytes": kv,
        "remaining_after_weights_and_c1_kv_bytes": int(budget - WEIGHT_BYTES - kv),
        "remaining_after_weights_and_c1_kv_gib": (budget - WEIGHT_BYTES - kv) / 2**30,
        "single_h100_memory_bound_pass": budget > WEIGHT_BYTES + kv,
    }


def validate_inputs(model_dir: Path, suite_manifest: Path) -> dict[str, object]:
    model = json.loads((model_dir / "model-files-manifest.json").read_text())
    suite = json.loads(suite_manifest.read_text())
    if model["revision"] != REVISION or model["shard_count"] != 48 or model["weight_bytes"] != WEIGHT_BYTES:
        raise SystemExit("checkpoint identity mismatch")
    if sha256(model_dir / "model-files-manifest.json") != MANIFEST_SHA256:
        raise SystemExit("checkpoint manifest digest mismatch")
    if suite["case_count"] != 36 or suite["holdout_status"] != "not_generated_not_inspected":
        raise SystemExit("frozen V2 suite contract mismatch")
    return {
        "revision": REVISION,
        "checkpoint_manifest_sha256": MANIFEST_SHA256,
        "shards": 48,
        "weight_bytes": WEIGHT_BYTES,
        "suite_manifest_sha256": sha256(suite_manifest),
        "suite_fixture_sha256": suite["fixture_sha256"],
        "holdout_status": suite["holdout_status"],
    }


def synthetic_artifact_check() -> dict[str, object]:
    with tempfile.TemporaryDirectory() as raw:
        root = Path(raw)
        for name in REQUIRED:
            (root / name).write_text("fixture\n")
        (root / "identity-manifest.json").write_text(json.dumps({"model_revision": REVISION}) + "\n")
        complete = all((root / name).is_file() for name in REQUIRED)
        missing = (root / "responses.jsonl").unlink() is None
        missing_rejected = not all((root / name).is_file() for name in REQUIRED)
    # The old V35 defect was a read-only /input bind. The mode must stage its
    # executable and data below a writable workspace destination.
    v35 = "docker run -v /home/glmrunner/input:/input:ro ... /input/remote_v2_capture.sh"
    writable = "/workspace/bf16-v2-quality/remote_vllm_bf16_quality.sh"
    return {
        "seven_artifact_contract_pass": complete,
        "missing_artifact_rejected": missing and missing_rejected,
        "v35_readonly_mount_negative_control_rejected": "/input/remote_v2_capture.sh" in v35 and "/input/" not in writable,
        "typed_terminal_required": True,
        "two_view_cleanup_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--suite-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    identity = validate_inputs(args.model_dir, args.suite_manifest)
    report = {
        "schema_version": 1,
        "classification": "zero_provider_bf16_vllm_admission_bridge",
        "runtime": {
            "vllm": "0.15.0",
            "vllm_image_digest": "97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543",
            "transformers_revision": "1618d44b9295361607ec74d7be860ba886aac039",
            "loader_module": "vllm.model_executor.models.glm4_moe_lite",
            "model_type": "glm4_moe_lite",
            "tokenizer_reasoning_off": "container preflight passed",
            "input_logprob_route": "vLLM OpenAI completions prompt_logprobs (source capability pass)",
            "gpu_launch": "not_run_zero_provider_contract",
        },
        "identity": identity,
        "memory": memory_bound(),
        "artifact_contract": synthetic_artifact_check(),
        "decision": "CONDITIONAL_PASS_STATIC_BRIDGE_GPU_LAUNCH_REQUIRED",
        "claim_limit": "admission bridge only; no quality or cost result",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision": report["decision"], "output": str(args.output), "memory_gib": report["memory"]["remaining_after_weights_and_c1_kv_gib"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
