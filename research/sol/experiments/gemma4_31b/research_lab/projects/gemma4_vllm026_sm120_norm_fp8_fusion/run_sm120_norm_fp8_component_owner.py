#!/usr/bin/env python3
"""Durable controller-host owner for the bound one-shot sm_120 component oracle.

This program is intentionally inert until a director execution binding names a
bench it may atomically claim.  It never starts, stops, or reloads the resident endpoint.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY_SRC = PROJECT.parents[5] / "factory" / "src"
POOL = [
    sys.executable,
    "-m",
    "grad_research.gpu_pool",
    "--lab",
    str(LAB),
]
PROJECT_ID = "gemma4_vllm026_sm120_norm_fp8_fusion"
SOURCE_RESULT = PROJECT / "VLLM026_SM120_NORM_FP8_FUSION_OFFLINE_RESULT.json"
PREPARATION = PROJECT / "DIRECTOR_VLLM026_SM120_NORM_FP8_COMPONENT_PREPARATION_20260729T0658Z.json"
PATCH = PROJECT / "implementation" / "vllm026_sm120_norm_fp8_fusion.patch"
ORACLE = PROJECT / "sm120_framework_oracle.py"
ORACLE_CONTEXT_WRAPPER = PROJECT / "framework_oracle_vllm_context.py"
INSTALLED_OVERLAY_PATCH = PROJECT / "implementation" / "installed_source_overlay_patch.py"
WHEEL_SHA256 = "6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b"
SOURCE_RESULT_SHA256 = "4e7312e233034c4ad3b208ac1a1298003602999bb2592d23756b935bab3b463f"
PREPARATION_SHA256 = "9709dbd0ad78a7f5e42a7d7b8974734fb8b5aa26ebdb7d181c92e75edce350ef"
INSTALLED_BASE_HASHES = {
    "model_executor/models/gemma4.py": "3d63af0ad265d56e09e3244a08102767efb6579a553db2c8213aa8912660b093",
    "model_executor/layers/quantization/online/fp8.py": "e7bbca668d3ce6134d24110ff3b5070f51d3fee21852a3fd90c1c83d4a04f2fc",
    "model_executor/kernels/linear/scaled_mm/cutlass.py": "d01b6fe09e3c3fa3991045f6ac7b469a58a550c56426ffd8900badbbe7e5355b",
    "model_executor/layers/fusion/quant_activation.py": "0b206185e76fc5b793b55bc21806b66d90ede201914de0a8104e4b9cdc91b63f",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def run(command: list[str], *, timeout: int, **kwargs: Any) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout, **kwargs)


def binding_value(binding: dict[str, Any], name: str) -> Any:
    value = binding.get(name)
    if value is None:
        raise RuntimeError(f"execution_binding_missing:{name}")
    return value


def validate_binding(binding: dict[str, Any]) -> None:
    if binding.get("project") != PROJECT_ID:
        raise RuntimeError("execution_binding_project_mismatch")
    if binding.get("claim_allowed") is not True:
        raise RuntimeError("execution_binding_claim_not_allowed")
    if binding.get("source_result_sha256") != SOURCE_RESULT_SHA256:
        raise RuntimeError("execution_binding_source_result_mismatch")
    if binding.get("preparation_sha256") != PREPARATION_SHA256:
        raise RuntimeError("execution_binding_preparation_mismatch")
    if binding.get("patch_sha256") != sha256(PATCH):
        raise RuntimeError("execution_binding_patch_mismatch")
    if binding.get("oracle_sha256") != sha256(ORACLE):
        raise RuntimeError("execution_binding_oracle_mismatch")
    if binding.get("scientific_submission_limit") != 1:
        raise RuntimeError("execution_binding_submission_limit_invalid")
    for name in (
        "bench_id",
        "claim_start_by_utc",
        "deadline_utc",
        "runtime_python",
        "runtime_wheel",
        "endpoint_health_command",
        "endpoint_driver_census_command",
        "remote_shell",
        "remote_project",
        "repair_deadline_utc",
    ):
        binding_value(binding, name)


def parse_utc(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def pool(arguments: list[str], timeout: int = 60) -> dict[str, Any]:
    result = run(["env", f"PYTHONPATH={FACTORY_SRC}", *POOL, *arguments], timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"gpu_pool_{arguments[0]}_failed:{result.stderr[-800:]}")
    return json.loads(result.stdout)


def claim_exact(binding: dict[str, Any], adopt_claimed_at: str | None = None) -> dict[str, str]:
    fence = parse_utc(binding_value(binding, "claim_start_by_utc"))
    if dt.datetime.now(dt.timezone.utc) >= fence:
        bench = pool(["show", "--bench", binding["bench_id"]])
        claim = bench.get("claim")
        claimed_at = claim.get("claimed_at") if isinstance(claim, dict) else None
        if (
            isinstance(claim, dict)
            and claim.get("project") == PROJECT_ID
            and isinstance(claimed_at, str)
            and parse_utc(claimed_at) < fence
            and (adopt_claimed_at is None or claimed_at == adopt_claimed_at)
        ):
            return {"bench_id": binding["bench_id"], "claimed_at": claimed_at}
        raise RuntimeError("claim_start_fence_expired")
    bench = pool(["claim", "--project", PROJECT_ID, "--bench", binding["bench_id"]])
    claim = bench.get("claim")
    claimed_at = claim.get("claimed_at") if isinstance(claim, dict) else None
    if bench.get("id") != binding["bench_id"] or not isinstance(claimed_at, str):
        raise RuntimeError("atomic_claim_response_missing_exact_generation")
    return {"bench_id": bench["id"], "claimed_at": claimed_at}


def heartbeat(stop: threading.Event, bench: str, events: list[dict[str, Any]]) -> None:
    while not stop.wait(25):
        try:
            claim = pool(["heartbeat", "--project", PROJECT_ID, "--bench", bench])
            events.append({"at_utc": utc_now(), "kind": "heartbeat", "claim": claim.get("claim")})
        except Exception as error:  # The terminal preserves this; do not silently lose a lease.
            events.append({"at_utc": utc_now(), "kind": "heartbeat_failed", "error": repr(error)})


def remote(binding: dict[str, Any], script: str, timeout: int) -> subprocess.CompletedProcess[str]:
    shell = binding_value(binding, "remote_shell")
    if not isinstance(shell, list) or not all(isinstance(part, str) for part in shell):
        raise RuntimeError("execution_binding_remote_shell_invalid")
    return run(shell + ["bash", "-s"], input=script, timeout=timeout)


def remote_root(binding: dict[str, Any], generation: dict[str, str], repair_id: str) -> str:
    stamp = generation["claimed_at"].replace(":", "").replace("+", "").replace("-", "")
    return f"{binding_value(binding, 'remote_project')}/component-{stamp}-{repair_id}"


def stage_remote_inputs(binding: dict[str, Any], generation: dict[str, str], repair_id: str) -> None:
    root = remote_root(binding, generation, repair_id)
    patch_b64 = base64.b64encode(PATCH.read_bytes()).decode()
    oracle_b64 = base64.b64encode(ORACLE.read_bytes()).decode()
    wrapper_b64 = base64.b64encode(ORACLE_CONTEXT_WRAPPER.read_bytes()).decode()
    overlay_patch_b64 = base64.b64encode(INSTALLED_OVERLAY_PATCH.read_bytes()).decode()
    script = f'''set -euo pipefail
ROOT={json.dumps(root)}
mkdir -p "$ROOT/inputs" "$ROOT/artifacts"
printf %s {json.dumps(patch_b64)} | base64 -d > "$ROOT/inputs/.patch.part"
printf %s {json.dumps(oracle_b64)} | base64 -d > "$ROOT/inputs/.oracle.part"
printf %s {json.dumps(wrapper_b64)} | base64 -d > "$ROOT/inputs/.oracle-wrapper.part"
printf %s {json.dumps(overlay_patch_b64)} | base64 -d > "$ROOT/inputs/.installed-overlay-patch.part"
test "$(sha256sum "$ROOT/inputs/.patch.part" | cut -d' ' -f1)" = {sha256(PATCH)}
test "$(sha256sum "$ROOT/inputs/.oracle.part" | cut -d' ' -f1)" = {sha256(ORACLE)}
test "$(sha256sum "$ROOT/inputs/.oracle-wrapper.part" | cut -d' ' -f1)" = {sha256(ORACLE_CONTEXT_WRAPPER)}
test "$(sha256sum "$ROOT/inputs/.installed-overlay-patch.part" | cut -d' ' -f1)" = {sha256(INSTALLED_OVERLAY_PATCH)}
mv -f "$ROOT/inputs/.patch.part" "$ROOT/inputs/vllm026_sm120_norm_fp8_fusion.patch"
mv -f "$ROOT/inputs/.oracle.part" "$ROOT/inputs/sm120_framework_oracle.py"
mv -f "$ROOT/inputs/.oracle-wrapper.part" "$ROOT/inputs/framework_oracle_vllm_context.py"
mv -f "$ROOT/inputs/.installed-overlay-patch.part" "$ROOT/inputs/installed_source_overlay_patch.py"
'''
    result = remote(binding, script, 120)
    if result.returncode:
        raise RuntimeError(f"remote_stage_failed:{result.stderr[-800:]}")


def remote_script(binding: dict[str, Any], generation: dict[str, str], repair_id: str) -> str:
    """Use a disposable copy of the installed package, never the endpoint's files."""
    root = remote_root(binding, generation, repair_id)
    runtime_python = binding_value(binding, "runtime_python")
    runtime_wheel = binding_value(binding, "runtime_wheel")
    health = binding_value(binding, "endpoint_health_command")
    census = binding_value(binding, "endpoint_driver_census_command")
    patch_sha = sha256(PATCH)
    oracle_sha = sha256(ORACLE)
    wrapper_sha = sha256(ORACLE_CONTEXT_WRAPPER)
    installed_overlay_patch_sha = sha256(INSTALLED_OVERLAY_PATCH)
    base_checks = "\n".join(
        f"test \"$(sha256sum \"$PKG/{name}\" | cut -d' ' -f1)\" = {digest}"
        for name, digest in INSTALLED_BASE_HASHES.items()
    )
    return f'''set -euo pipefail
ROOT={json.dumps(root)}
PY={json.dumps(runtime_python)}
WHEEL={json.dumps(runtime_wheel)}
mkdir -p "$ROOT/overlay"
test "$(sha256sum "$WHEEL" | cut -d' ' -f1)" = {WHEEL_SHA256}
"$PY" -c 'import torch,vllm; assert torch.__version__ == "2.11.0+cu130"; assert vllm.__version__.startswith("0.26.0")'
"$PY" -c 'import torch; assert torch.cuda.get_device_capability() == (12, 0)'
PKG="$($PY -c 'import pathlib,vllm; print(pathlib.Path(vllm.__file__).resolve().parent)')"
{base_checks}
{health}
if ! {census}; then
  echo 'endpoint driver is active or census is incomplete' >&2
  exit 72
fi
test "$(sha256sum "$ROOT/inputs/vllm026_sm120_norm_fp8_fusion.patch" | cut -d' ' -f1)" = {patch_sha}
test "$(sha256sum "$ROOT/inputs/sm120_framework_oracle.py" | cut -d' ' -f1)" = {oracle_sha}
test "$(sha256sum "$ROOT/inputs/framework_oracle_vllm_context.py" | cut -d' ' -f1)" = {wrapper_sha}
test "$(sha256sum "$ROOT/inputs/installed_source_overlay_patch.py" | cut -d' ' -f1)" = {installed_overlay_patch_sha}
cp -a "$PKG" "$ROOT/overlay/vllm"
"$PY" "$ROOT/inputs/installed_source_overlay_patch.py" "$ROOT/overlay/vllm"
trap 'rm -rf "$ROOT/overlay"' EXIT
printf '%s\\n' '{{"schema_version":1,"state":"science_started","oracle":"sm120_framework_oracle.py"}}' > "$ROOT/artifacts/SCIENCE_STARTED.json"
PYTHONPATH="$ROOT/overlay${{PYTHONPATH:+:$PYTHONPATH}}" CUDA_VISIBLE_DEVICES=0 "$PY" "$ROOT/inputs/framework_oracle_vllm_context.py" "$ROOT/inputs/sm120_framework_oracle.py" --rows 1,32,33,2048 --warmup 10 --repeats 50 --output "$ROOT/artifacts/SM120_FRAMEWORK_ORACLE.json"
'''


def retrieve_oracle(binding: dict[str, Any], generation: dict[str, str], artifacts: Path, repair_id: str) -> tuple[Path | None, bool]:
    root = remote_root(binding, generation, repair_id)
    result = remote(
        binding,
        f"cat {json.dumps(root + '/artifacts/SM120_FRAMEWORK_ORACLE.json')}",
        timeout=120,
    )
    started = remote(
        binding,
        f"test -f {json.dumps(root + '/artifacts/SCIENCE_STARTED.json')}",
        timeout=30,
    )
    if result.returncode:
        return None, started.returncode == 0
    destination = artifacts / "SM120_FRAMEWORK_ORACLE.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(result.stdout)
    json.loads(temporary.read_text())
    temporary.replace(destination)
    return destination, started.returncode == 0


def terminal_payload(binding: dict[str, Any], generation: dict[str, str], artifacts: Path, result: subprocess.CompletedProcess[str], events: list[dict[str, Any]], repair_id: str) -> dict[str, Any]:
    result_path, science_started = retrieve_oracle(binding, generation, artifacts, repair_id)
    oracle = json.loads(result_path.read_text()) if result_path else None
    complete = bool(oracle and oracle.get("passed") is True and len(oracle.get("rows", [])) == 7)
    return {
        "schema_version": 1,
        "classification": "component_terminal" if complete else "recoverable_integration_or_incomplete",
        "decision": "positive_component" if complete and any(row["warm_latency_ms"]["median_delta"] > 0 for row in oracle["rows"]) else "nonpositive_or_invalid",
        "science_consumed": science_started,
        "oracle_complete": complete,
        "stock_candidate_rows": 7 if oracle else 0,
        "path_evidence": {
            "candidate_producer": "ops.rms_norm_dynamic_per_token_quant via rms_norm_to_fp8_linear",
            "unchanged_consumer": "CutlassFP8ScaledMMLinearKernel.apply_weights -> ops.cutlass_scaled_mm",
            "oracle_sha256": sha256(ORACLE),
            "patch_sha256": sha256(PATCH),
            "installed_overlay_patch_sha256": sha256(INSTALLED_OVERLAY_PATCH),
        },
        "result_path": str(result_path) if result_path else None,
        "result_sha256": sha256(result_path) if result_path else None,
        "stdout": result.stdout[-4000:],
        "stderr": result.stderr[-4000:],
        "exit_code": result.returncode,
        "binding_sha256": sha256(Path(binding["_path"])),
        "events": events,
    }


def retain_for_repair(artifacts: Path, binding: dict[str, Any], generation: dict[str, str], terminal: dict[str, Any], repair_id: str, repair_deadline_utc: str) -> dict[str, Any]:
    ready = PROJECT.parents[5] / "factory" / "tools" / "repair-handshake"
    diagnostic = artifacts / "OWNER_TERMINAL.json"
    ready_result = run(
        [str(ready), "ready", "--root", str(artifacts), "--repair-id", repair_id,
         "--deadline", repair_deadline_utc, "--failure-kind", "integration",
         "--diagnostic", str(diagnostic), "--retry-scope", "framework_oracle_only"],
        timeout=30,
    )
    if ready_result.returncode and "repair_request_already_exists" not in ready_result.stderr:
        raise RuntimeError(f"repair_ready_failed:{ready_result.stderr[-800:]}")
    terminal["repair_handshake"] = {"repair_id": repair_id, "retry_scope": "framework_oracle_only"}
    atomic_json(diagnostic, terminal)
    hold_result = run(
        [str(ready), "hold", "--root", str(artifacts), "--repair-id", repair_id,
         "--deadline", repair_deadline_utc, "--failure-kind", "integration",
         "--diagnostic", str(diagnostic), "--retry-scope", "framework_oracle_only"],
        timeout=max(30, int(dt.datetime.fromisoformat(repair_deadline_utc.replace("Z", "+00:00")).timestamp() - time.time())),
    )
    status = run([str(ready), "status", "--root", str(artifacts), "--repair-id", repair_id], timeout=30)
    if status.returncode not in (0, 3):
        raise RuntimeError(f"repair_status_failed:{status.stderr[-800:]}")
    value = json.loads(status.stdout)
    value["hold_exit_code"] = hold_result.returncode
    return value


def release_generation(binding: dict[str, Any], generation: dict[str, str], terminal: dict[str, Any], artifacts: Path, condition: str) -> None:
    contents = artifacts / "RELEASE_CONTENTS.json"
    atomic_json(contents, {
        "runtime": "official vLLM 0.26.0+cu129 remains resident; endpoint was not stopped",
        "component_terminal_sha256": sha256(artifacts / "OWNER_TERMINAL.json") if (artifacts / "OWNER_TERMINAL.json").is_file() else None,
        "component_result_sha256": terminal.get("result_sha256"),
        "condition": condition,
        "claimed_at": generation["claimed_at"],
    })
    pool(["release", "--project", PROJECT_ID, "--bench", generation["bench_id"],
          "--expected-claimed-at", generation["claimed_at"],
          "--condition", "maintenance", "--contents", str(contents)])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--repair-id")
    parser.add_argument("--repair-deadline-utc")
    parser.add_argument("--adopt-claimed-at")
    parser.add_argument("--release-deadline-utc")
    args = parser.parse_args()
    binding = json.loads(args.binding.read_text())
    binding["_path"] = str(args.binding)
    validate_binding(binding)
    if sha256(SOURCE_RESULT) != SOURCE_RESULT_SHA256 or sha256(PREPARATION) != PREPARATION_SHA256:
        raise RuntimeError("offline_admission_hash_mismatch")
    artifacts = args.artifact_root.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    generation = claim_exact(binding, args.adopt_claimed_at)
    repair_id = args.repair_id or f"sm120-norm-fp8-{generation['claimed_at'].replace(':', '').replace('+', '')}"
    repair_deadline_utc = args.repair_deadline_utc or binding["repair_deadline_utc"]
    atomic_json(artifacts / "REPAIR_GENERATION.json", {"repair_id": repair_id, "claimed_at": generation["claimed_at"], "predecessor_repair_id": None})
    stop = threading.Event()
    events: list[dict[str, Any]] = [{"at_utc": utc_now(), "kind": "atomic_claim", **generation}]
    thread = threading.Thread(target=heartbeat, args=(stop, generation["bench_id"], events), daemon=True)
    thread.start()
    try:
        while True:
            try:
                stage_remote_inputs(binding, generation, repair_id)
                release_seconds = 900
                if args.release_deadline_utc:
                    release_seconds = max(1, int(parse_utc(args.release_deadline_utc).timestamp() - time.time()))
                result = remote(binding, remote_script(binding, generation, repair_id), timeout=min(900, release_seconds))
                payload = terminal_payload(binding, generation, artifacts, result, events, repair_id)
            except Exception as error:
                payload = {
                    "schema_version": 1,
                    "classification": "recoverable_integration_or_incomplete",
                    "decision": "nonpositive_or_invalid",
                    "science_consumed": False,
                    "oracle_complete": False,
                    "stock_candidate_rows": 0,
                    "error": repr(error),
                    "binding_sha256": sha256(Path(binding["_path"])),
                    "events": events,
                }
            atomic_json(artifacts / "OWNER_TERMINAL.json", payload)
            if payload["oracle_complete"]:
                release_generation(
                    binding, generation, payload, artifacts,
                    "correct_positive_component_result" if payload["decision"] == "positive_component" else "correct_nonpositive_component_result",
                )
                return 0 if payload["decision"] == "positive_component" else 4
            repair = retain_for_repair(artifacts, binding, generation, payload, repair_id, repair_deadline_utc)
            if repair.get("state") != "requested":
                release_generation(binding, generation, payload, artifacts, "repair_deadline_or_incomplete")
                return 75
            events.append({"at_utc": utc_now(), "kind": "repair_requested", "repair": repair})
    finally:
        stop.set()
        thread.join(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
