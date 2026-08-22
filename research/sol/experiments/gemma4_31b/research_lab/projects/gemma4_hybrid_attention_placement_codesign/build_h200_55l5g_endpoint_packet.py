#!/usr/bin/env python3
"""Build and validate the zero-GPU packet for the sole unconsumed endpoint pair.

The packet deliberately has no bench identity.  A future director binding must
copy connection, image, checkpoint, and lifecycle values from a then-live pool
record; this builder only seals local immutable inputs and executable guards.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PACKET = ROOT / "inputs" / "h200_55l5g_endpoint_packet"
SOURCE = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_h200_ngram_tree_verify_attention/inputs/checkpoint")
MODEL_FILES = ("config.json", "tokenizer.json", "tokenizer_config.json", "processor_config.json", "chat_template.jinja")
OWNER = ROOT / "run_h200_55l5g_endpoint_owner.py"
PAIR = ROOT / "run_h200_55l5g_endpoint_pair.py"
RUNTIME = ROOT / "run_h200_55l5g_endpoint_runtime.py"
GUARD = ROOT / "endpoint_readiness_guard.py"
WORKLOAD = Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab/projects/gemma4_causal_parallel_offset_head/inputs/qualified_c32_workload.json")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        json.dump(value, f, indent=2, sort_keys=True)
        f.write("\n")
        tmp = Path(f.name)
    json.loads(tmp.read_text())
    tmp.replace(path)


def hardlink(src: Path, dest: Path) -> None:
    if dest.exists():
        if sha(src) != sha(dest):
            raise RuntimeError(f"immutable_packet_destination_mismatch:{dest}")
        return
    try:
        os.link(src, dest)
    except OSError:
        shutil.copy2(src, dest)
        if sha(src) != sha(dest):
            raise RuntimeError(f"packet_copy_hash_mismatch:{dest}")
    dest.chmod(0o444)


def build() -> dict[str, Any]:
    model_root = PACKET / "model_inputs"
    model_root.mkdir(parents=True, exist_ok=True)
    for name in MODEL_FILES:
        hardlink(SOURCE / name, model_root / name)
    local_workload = PACKET / "qualified_c32_workload.json"
    hardlink(WORKLOAD, local_workload)
    files = [model_root / name for name in MODEL_FILES] + [OWNER, PAIR, RUNTIME, GUARD, local_workload]
    manifest = {
        "schema_version": 1,
        "scope": "one_quality_unsafe_stock_permanent_55l5g_c32_pair",
        "quality_preservation_claimed": False,
        "no_gpu_or_provider_operation": True,
        "immutable_files": [{"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files],
        "future_live_bench_contract": {
            "must_come_from_live_bench_record": ["resource.public_ipv4", "resource.ssh_user", "resource.known_hosts_namespace", "resource.ssh_ed25519_fingerprint", "checkpoint_path", "image", "lifecycle", "claim_generation"],
            "forbidden_historical_defaults": True,
        },
        "readiness_contract": {
            "health_endpoint": "/health",
            "poll_seconds": 2,
            "fail_immediately_when": ["container_not_running", "container_exit_code_nonzero", "child_pid_not_alive", "fatal_log_marker"],
            "generation_probe_forbidden": True,
        },
        "pair_contract": {"stock_then_candidate": True, "concurrency": 32, "prompt_tokens": 4214, "output_tokens": 358, "workload_path": str(local_workload.relative_to(ROOT)), "maximum_valid_pair_invocations": 1},
    }
    atomic_json(PACKET / "MANIFEST.json", manifest)
    return manifest


def validate_future(binding: dict[str, Any], bench: dict[str, Any], manifest: dict[str, Any]) -> None:
    required = manifest["future_live_bench_contract"]["must_come_from_live_bench_record"]
    if bench.get("status") != "available" or bench.get("claim") is not None:
        raise RuntimeError("future_bench_not_live_available_unclaimed")
    if binding.get("bench_id") != bench.get("id"):
        raise RuntimeError("future_binding_bench_id_mismatch")
    for field in required:
        cursor: Any = bench
        for part in field.split("."):
            cursor = cursor.get(part) if isinstance(cursor, dict) else None
        if cursor is None:
            raise RuntimeError(f"future_live_bench_field_missing:{field}")
        if binding.get("resolved_from_live_bench", {}).get(field) != cursor:
            raise RuntimeError(f"future_live_bench_field_not_resolved:{field}")
    if binding.get("owner_sha256") != sha(OWNER) or binding.get("pair_sha256") != sha(PAIR):
        raise RuntimeError("future_binding_executable_hash_mismatch")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--validate-future", action="store_true")
    p.add_argument("--binding", type=Path)
    p.add_argument("--bench-record", type=Path)
    args = p.parse_args()
    manifest = build()
    if args.validate_future:
        if not args.binding or not args.bench_record:
            raise RuntimeError("future_binding_and_bench_record_required")
        validate_future(json.loads(args.binding.read_text()), json.loads(args.bench_record.read_text()), manifest)
    print(json.dumps({"packet": str(PACKET), "manifest_sha256": sha(PACKET / "MANIFEST.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
