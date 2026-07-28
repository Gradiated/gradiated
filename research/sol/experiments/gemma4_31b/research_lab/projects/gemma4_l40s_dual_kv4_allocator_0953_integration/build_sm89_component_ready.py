#!/usr/bin/env python3
"""Build the immutable packet manifest and offline readiness contract."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / "L40S_DUAL_KV4_SM89_PACKET_MANIFEST.json"
READY = ROOT / "L40S_DUAL_KV4_SM89_COMPONENT_READY.json"
FILES = (
    "sm89_dual_kv4_runner.py", "l40s_dual_kv4_owner.py",
    "local_kv4_outlier_bindings.cpp", "local_kv4_outlier_cuda.cu",
    "global_tiered_kv4_bindings.cpp", "global_tiered_kv4_cuda.cu",
    "packet/MODEL_CONFIG.json", "packet/WORKLOAD.json",
)
AUTHORITATIVE = {
    "offline_terminal": "L40S_DUAL_KV4_ALLOCATOR_0953_OFFLINE_TERMINAL.json",
    "local_component_ready": "../gemma4_l40s_kv4_outlier_sm89_component/L40S_KV4_OUTLIER_SM89_COMPONENT_READY.json",
    "global_tiered_terminal": "../gemma4_l40s_global_tiered_kv4_outlier/L40S_GLOBAL_TIERED_KV4_OUTLIER_OFFLINE_TERMINAL.json",
}
EXPECTED = {
    "offline_terminal": "e98777580a46ef458e1ea704ceea6fc827030150fe4efa8e67ef380e99fd0090",
    "local_component_ready": "ac9ea0118c943f33b55cd4f99ce858f70eacba21e3f80f5e7f4d93be59a4043c",
    "global_tiered_terminal": "46db0a82a29f1af4299f5e8a6af7ddaf8bf1c859f5c08c823e9bbfb9c4a79e83",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    direct = {}
    for name, relative in AUTHORITATIVE.items():
        path = (ROOT / relative).resolve()
        actual = sha256(path)
        if actual != EXPECTED[name]:
            raise RuntimeError(f"authoritative_digest_changed:{name}:{actual}")
        direct[name] = {"path": str(path), "sha256": actual, "evidence": "direct"}
    rows = [{"path": name, "bytes": (ROOT / name).stat().st_size, "sha256": sha256(ROOT / name)} for name in FILES]
    atomic(MANIFEST, {"schema_version": 1, "kind": "checkpoint_free_sm89_dual_kv4_packet", "files": rows, "fixed_contract": {"accelerator": "NVIDIA L40S SM89", "c32": 32, "decode_steps": 358, "local_layers": 50, "global_layers": 10, "page_size": 1, "warmups": 5, "repeats": 31}})
    checked = subprocess.run(["python3", "-m", "py_compile", "sm89_dual_kv4_runner.py", "l40s_dual_kv4_owner.py", "build_sm89_component_ready.py", "test_sm89_dual_kv4_ready.py"], cwd=ROOT, text=True, capture_output=True, check=False)
    tests = subprocess.run(["python3", "-m", "unittest", "-v", "test_dual_kv4_contract.py", "test_sm89_dual_kv4_ready.py"], cwd=ROOT, text=True, capture_output=True, check=False)
    if checked.returncode or tests.returncode:
        raise RuntimeError(json.dumps({"py_compile": checked.stderr, "tests": tests.stdout + tests.stderr}))
    ready = {
        "schema_version": 1, "kind": "l40s_dual_kv4_sm89_component_ready", "project": ROOT.name,
        "classification": "offline_ready_lifecycle_pure_checkpoint_free_component", "pass": True,
        "scientific_result": "unmeasured_target_gpu_execution_required", "actual_spend_usd": 0.0,
        "direct_hashes": {"authoritative": direct, "packet_manifest": {"path": str(MANIFEST), "sha256": sha256(MANIFEST)}, "runner": {"path": str(ROOT / "sm89_dual_kv4_runner.py"), "sha256": sha256(ROOT / "sm89_dual_kv4_runner.py")}, "owner": {"path": str(ROOT / "l40s_dual_kv4_owner.py"), "sha256": sha256(ROOT / "l40s_dual_kv4_owner.py")}},
        "fixed_contract": {"accelerator": "one NVIDIA L40S SM89", "runtime_commit": "c6a6200a1a778a799ba61c395ac292317f01ebc9", "runtime_image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6", "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4", "c32": 32, "decode_steps": 358, "local_layers": 50, "global_layers": 10, "page_size": 1, "local": "D256 group-64 KV4 O4", "global": "D512 recent-1024 E5M2 / old group-64 KV4 O8"},
        "arm_isolation": {"first_call_markers": ["local baseline_first_untimed_complete", "local candidate_first_untimed_complete", "global baseline_first_untimed_complete", "global candidate_first_untimed_complete"], "rule": "each marker is persisted only after a CUDA synchronization and before timing"},
        "correctness_and_resources": {"outputs": ["finite", "relative_l2", "max_abs", "cosine"], "compiler": ["cuobjdump resource usage", "shared/local/register output when emitted", "extension SHA-256"], "timing": "five warmups and 31 synchronized, order-alternated complete producer-plus-consumer rows per arm"},
        "terminal_inequality": {"complete_request_equation": "T_dual = T_e5m2_l40s - 0.559375*m_local_ms - 0.111875*m_global_ms + O_integration", "price_normalized_acceptance": "0.559375*m_local_ms + 0.111875*m_global_ms - O_integration >= T_e5m2_l40s_s_per_request - 1.4776251501079425", "endpoint_claim": False, "integration_overhead": "unmeasured and never invented by the component runner"},
        "focused_offline_checks": [{"command": "python3 -m py_compile sm89_dual_kv4_runner.py l40s_dual_kv4_owner.py build_sm89_component_ready.py test_sm89_dual_kv4_ready.py", "result": "pass"}, {"command": "python3 -m unittest -v test_dual_kv4_contract.py test_sm89_dual_kv4_ready.py", "result": "pass", "covers": ["frozen memory ledger", "local/global source reachability", "arm isolation markers", "repair-aware owner", "no checkpoint/server path"]}],
        "scope": {"gpu_pool_claimed": False, "provider_api_used": False, "ssh_used": False, "cuda_invoked": False, "checkpoint_shards_read": False, "image_pulled": False, "model_server_started": False, "representation_sweep": False},
        "reservation": {"authorized_usd": 1.5, "planned_max_lifecycle_seconds": 5400, "latest_measured_hourly_usd": 0.8629833, "conservative_lifecycle_usd": 1.29447495, "actual_spend_usd": 0.0, "authority": "reservation only; director must create/register a bench after observing this readiness artifact"},
        "owner": {"controller": "/root/workspace/research/factory/tools/detached-owner", "owner_path": str(ROOT / "l40s_dual_kv4_owner.py"), "packet_manifest": str(MANIFEST), "unit_manager": "pid", "repair_disposition": "ordinary pre-science compile, API, launcher, transfer, or retrieval defects emit a hash-bound repair handshake while the outer owner retains and heartbeats the claim", "exact_detached_owner_command": f"/root/workspace/research/factory/tools/detached-owner start --unit-manager pid --state {ROOT}/artifacts/dual-kv4-owner-DIRECTOR_BOUND_UTC/OWNER.json --log {ROOT}/artifacts/dual-kv4-owner-DIRECTOR_BOUND_UTC/OWNER.log -- python3 {ROOT}/l40s_dual_kv4_owner.py --bench DIRECTOR_REGISTERED_L40S_BENCH --artifact-root {ROOT}/artifacts/dual-kv4-component-DIRECTOR_BOUND_UTC --deadline-seconds 5400", "active_session_record": "after launch record the emitted absolute state path as unit plus pid, start_ticks, unit_manager=pid, deadline, and artifact_root"},
        "next_action": "A later director may register one bounded 90-minute L40S lifecycle, use the exact command, and only promote after both retrieved arms and the terminal inequality are measured."}
    atomic(READY, ready)


if __name__ == "__main__":
    main()
