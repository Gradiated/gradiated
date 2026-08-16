"""Corrected no-mutation loader-contract audit for the materialized student."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = Path("/root/.cache/glm47flash-awq-student39-183247870f89")
LAUNCHER = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius/vllm_smoke_control.py")
REMOTE = LAUNCHER.with_name("remote_awq_smoke.sh")
sys.path.insert(0, str(LAUNCHER.parent))
from awq_smoke_control import validate_local_model  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    manifest = json.loads((ROOT / "model-files-manifest.json").read_text())
    result: dict[str, object] = {
        "evidence_class": "measured_local_contract_failure_plus_pinned_runtime_no_gpu_diagnostic",
        "student_root": str(ROOT),
        "student_manifest_sha256": sha256(ROOT / "model-files-manifest.json"),
        "student_weight_bytes": manifest["weight_bytes"],
        "shared_launcher": str(LAUNCHER),
        "shared_launcher_sha256": sha256(LAUNCHER),
        "remote_script_sha256": sha256(REMOTE),
        "declared_remote_script_sha256": "afab442b83cedf22cced6d3fd70e9d855c016fa7251449a545cd54eaf5796dbd",
        "launcher_expected_control_weight_bytes": 20170199928,
        "provider_create_attempted": False,
        "provider_spend_usd": 0.0,
    }
    try:
        validate_local_model(ROOT)
    except Exception as error:
        result["shared_launcher_validation"] = {"status": "FAIL_EXPECTED", "type": type(error).__name__, "message": str(error)}
    else:
        result["shared_launcher_validation"] = {"status": "UNEXPECTED_PASS"}
    result["pinned_runtime_source"] = {
        "image": "glm-vllm:0.15.0-transformers-1618d44",
        "image_id": "sha256:4672d4aa966cf5f4d437d9f7fd9fb4d1b662a067455f3db46d2ab6cce3f3f62c",
        "config_registry_and_quantization": "static source screen PASS in VLLM_RELEASE_DELTA_SCREEN_2026-07-15.json",
        "local_executable_preflight": {"status": "BLOCKED_NO_CUDA", "returncode": 1, "diagnostic": "torch RuntimeError: No CUDA GPUs are available after vLLM/Transformers import and config parse"},
    }
    result["decision"] = "CLOSE_ZERO_COST_NO_PROVIDER: shared launcher rejects the smaller physical checkpoint; launcher edit or deceptive manifest would be required"
    (HERE / "student39_loader_contract_diagnostic.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    preflight_path = HERE / "student39_runtime_preflight.json"
    preflight = json.loads(preflight_path.read_text())
    preflight["status"] = "STRUCTURAL_ONLY_LOADER_CLOSURE_NOT_PROVEN"
    preflight["loader_contract_diagnostic"] = "student39_loader_contract_diagnostic.json"
    preflight["provider_safe_to_create"] = False
    preflight_path.write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
