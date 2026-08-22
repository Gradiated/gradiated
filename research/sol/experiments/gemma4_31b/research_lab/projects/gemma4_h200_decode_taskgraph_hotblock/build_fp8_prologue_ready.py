#!/usr/bin/env python3
"""Validate frozen owner inputs and atomically publish owner readiness."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
WORKSPACE = Path("/root/workspace")
BINDING = PROJECT / "DIRECTOR_TASKGRAPH_FP8_PROLOGUE_H200_EXECUTION_20260729T2148Z.json"
SOURCE = (
    WORKSPACE
    / ".agents/runtime/sglang-v0.5.13-source/python/sglang/srt/layers/quantization/fp8_utils.py"
)
TRACE = (
    WORKSPACE
    / "research/sol/experiments/gemma4_31b/research_lab/projects/"
    "gemma4_h200_v0513_fp8_qkv_residual_profile/artifacts/"
    "residual-profile-20260720t0821z/pair/nsys-stats.csv"
)
EXPECTED_BINDING = "82da8037e760b7fb07a01bd161ea2ce7ba6d07454670367f568d8da76c1db289"
READY = PROJECT / "FP8_PROLOGUE_H200_OWNER_READY.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def immutable(path: Path) -> dict:
    return {"absolute_path": str(path.resolve()), "sha256": sha256(path), "bytes": path.stat().st_size}


def main() -> None:
    owner = PROJECT / "fp8_prologue_h200_owner.py"
    runner = PROJECT / "fp8_prologue_h200_runner.py"
    fixture = PROJECT / "fp8_prologue_cpu_fixture.py"
    for path in [owner, runner, fixture, Path(__file__), BINDING, SOURCE, TRACE]:
        ast.parse(path.read_text()) if path.suffix == ".py" else None
    assert sha256(BINDING) == EXPECTED_BINDING
    fixture_run = subprocess.run(
        [sys.executable, str(fixture)], check=True, capture_output=True, text=True
    )
    fixture_result = json.loads(fixture_run.stdout)
    assert fixture_result["pass"] is True
    subprocess.run(
        [sys.executable, "-m", "py_compile", str(owner), str(runner), str(fixture), str(Path(__file__))],
        check=True,
    )
    source_text = SOURCE.read_text()
    required_source = [
        "qinput, x_scale = sglang_per_token_quant_fp8(input_2d)",
        "output = fp8_scaled_mm(",
        "out_dtype=input.dtype",
    ]
    assert all(token in source_text for token in required_source)
    trace_line = next(
        line for line in TRACE.read_text().splitlines() if "per_token_quant_fp8_small_batch_kernel" in line
    )
    assert ",323396400,14640," in trace_line
    files = [immutable(path) for path in [owner, runner, fixture, Path(__file__), BINDING, SOURCE, TRACE]]
    ready = {
        "schema_version": 1,
        "artifact_type": "fp8_prologue_h200_owner_ready",
        "created_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "project": "gemma4_h200_decode_taskgraph_hotblock",
        "decision": "ready_for_one_bound_mutable_h200_owner",
        "binding": {"path": BINDING.name, "sha256": EXPECTED_BINDING},
        "reservation": {
            "authorized_cumulative_usd": 6.0,
            "actual_spend_usd_before_claim": 0.0,
            "reserved_at_utc": "2026-07-29T21:44:08.760922Z",
            "hourly_rate_usd": 2.45,
        },
        "bench": {
            "id": "h200-qkv-endpoint-computeinstance-e00qxw871hz1r79fjt",
            "required_status": "available",
            "gpu_uuid": "GPU-81ca2c99-6df0-5bf8-023c-3ee78a68f3d8",
            "ssh_ed25519_fingerprint": "SHA256:3hDhNCJKQQo68DtW7LV5dperdxrj4cJJ39CVq0w1ZRM",
            "watchdog_unit": "gemma4-pq-mips-20260729t2107z-watchdog-r4.service",
            "watchdog_pid": 299583,
            "claim_start_by_utc": "2026-07-29T22:25:00Z",
            "owner_deadline_utc": "2026-07-29T23:48:00Z",
        },
        "component": {
            "projection": "model.language_model.layers.0.self_attn.q_proj.weight",
            "checkpoint_shape": [8192, 5376],
            "consumer_shape": {"M": 32, "K": 5376, "N": 8192},
            "input": {"dtype": "bfloat16", "shape": [32, 5376]},
            "activation_quantization": {
                "dtype": "float8_e4m3fn",
                "scale": "one float32 scale per input row [32]",
                "amax_divisor": 448.0,
                "zero_guard": "max(amax,1e-12)",
            },
            "weight": {
                "identity": "real layer-0 q_proj checkpoint tensor",
                "source_dtype": "bfloat16",
                "consumer_dtype": "float8_e4m3fn",
                "scale": "one float32 scale per output column [8192]",
                "shard": "model-00001-of-00002.safetensors",
                "shard_bytes": 49784788364,
                "shard_sha256": "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa",
                "index_sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
                "resident_path": "/home/glmrunner/qkv-direct-a7fc5afbe3c3b292/checkpoint",
            },
            "stock": "sgl_per_token_quant_fp8 then unchanged fp8_scaled_mm",
            "candidate": "row_scale_kernel then fused_quant_gemm_kernel with E4M3 conversion on tile load",
            "candidate_preserves_scale_barrier": True,
            "candidate_removes_global_quantized_activation": True,
        },
        "experiment": {
            "hypothesis": "Eliminating global qactivation write/read can outweigh on-tile conversion despite preserving the row-scale barrier.",
            "correctness_gate": {
                "finite": True,
                "relative_l2_max": 0.02,
                "cosine_min": 0.999,
                "scale_relative_error_max": 2e-5,
                "negative_control": "rolled weight-scale vector must diverge",
            },
            "timing": {
                "order": ["stock", "candidate", "stock", "candidate", "stock", "candidate", "stock"],
                "warmup": 8,
                "inner": 20,
                "unit": "ns per complete producer-plus-consumer interval",
                "full_output_consumed": True,
                "profiler": "off",
            },
            "output_contract": [
                "IDENTITY.json",
                "SCIENCE_STARTED.json",
                "STOCK_SMOKE_COMPLETE.json",
                "CANDIDATE_SMOKE_COMPLETE.json",
                "CORRECTNESS.json",
                "TIMING_ROWS.json when correctness passes",
                "TERMINAL.json",
            ],
            "whole_request_transfer": "forbidden without endpoint A/B or scope-matched critical-path attribution",
        },
        "owner": {
            "path": owner.name,
            "sha256": sha256(owner),
            "unit_manager": "pid",
            "controller": "/root/workspace/research/factory/tools/detached-owner",
            "heartbeat": True,
            "repair_dispatch": "hash-bound project-local runner replacement, worker-only retry, same claim",
            "release": "generation-fenced with expected claimed_at; available on quiescent terminal, maintenance only on nonrecoverable/deadline boundary",
        },
        "runner": {"path": runner.name, "sha256": sha256(runner)},
        "fixture": {"path": fixture.name, "sha256": sha256(fixture), "result": fixture_result},
        "commands": {
            "claim": "PYTHONPATH=research/factory/src python3 -m grad_research.gpu_pool --lab /root/workspace/research/sol/experiments/gemma4_31b/research_lab claim --project gemma4_h200_decode_taskgraph_hotblock --bench h200-qkv-endpoint-computeinstance-e00qxw871hz1r79fjt",
            "owner": "research/factory/tools/detached-owner start --unit-manager pid --state ABS_OWNER_STATE --log ABS_OWNER_LOG --cwd ABS_PROJECT -- python3 ABS_OWNER --bench h200-qkv-endpoint-computeinstance-e00qxw871hz1r79fjt --claimed-at CLAIMED_AT --owner-state ABS_OWNER_STATE --artifact-root ABS_ARTIFACT_ROOT",
            "container": f"sudo -n docker run --rm --gpus all --ipc=host -v REMOTE_ROOT:/work -v REMOTE_CHECKPOINT:/checkpoint:ro {os.environ.get('FP8_IMAGE','docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6')} python3 /work/RUNNER --checkpoint-root /checkpoint --output-root /work/out-N",
        },
        "immutable_files": files,
        "validation": {
            "python_compile": True,
            "source_symbols": required_source,
            "trace_row": trace_line,
            "cpu_fixture": fixture_result,
        },
    }
    tmp = READY.with_suffix(".json.part")
    tmp.write_text(json.dumps(ready, indent=2, sort_keys=True) + "\n")
    json.loads(tmp.read_text())
    os.replace(tmp, READY)
    print(json.dumps({"ready": str(READY), "sha256": sha256(READY)}, sort_keys=True))


if __name__ == "__main__":
    main()
