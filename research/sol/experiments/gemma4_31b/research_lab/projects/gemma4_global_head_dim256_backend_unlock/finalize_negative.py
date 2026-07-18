#!/usr/bin/env python3
import hashlib
import json
import os
import sys
from pathlib import Path


def atomic(path: Path, value: dict) -> None:
    part = path.with_suffix(path.suffix + ".part")
    with part.open("w") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


def atomic_text(path: Path, value: str) -> None:
    part = path.with_suffix(path.suffix + ".part")
    with part.open("w") as handle:
        handle.write(value)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(part, path)


root = Path(sys.argv[1])
raw_path = root / "global-head256-xqa-20260718t2130z" / "RESULT.json"
raw = json.loads(raw_path.read_text())
rows = raw["rows"]
by = {(row["head_dim"], row["component"]): row for row in rows}
prompt_chunks_per_request = 4214 * (1.0 - 0.127) / 2048
projection_weights = {
    "qkv_prompt_chunk": 10 * prompt_chunks_per_request,
    "o_prompt_chunk": 10 * prompt_chunks_per_request,
    "qkv_decode_step": 10 * 358 / 32,
    "o_decode_step": 10 * 358 / 32,
    "prompt_attention_triton": 10 / 32,
}
components = []
current = 0.0
candidate = 0.0
for component, weight in projection_weights.items():
    current_seconds = by[(512, component)]["p50_ms"] * weight / 1000
    candidate_seconds = by[(256, component)]["p50_ms"] * weight / 1000
    current += current_seconds
    candidate += candidate_seconds
    components.append(
        {
            "component": component,
            "weight": weight,
            "current_seconds_per_request": current_seconds,
            "candidate_seconds_per_request": candidate_seconds,
        }
    )

terminal = {
    "schema_version": 1,
    "status": "terminal",
    "pass": False,
    "classification": "candidate_xqa_runtime_failure",
    "decision": "close_architecture_backend_line",
    "evidence_type": "measured exact-H200 non-quality-preserving architecture proxy",
    "quality_claim": False,
    "identity": raw["identity"],
    "geometry": {
        "hidden_size": 5376,
        "query_heads": 32,
        "kv_heads": 4,
        "current_global_head_dim": 512,
        "candidate_global_head_dim": 256,
        "global_layers": 10,
        "concurrency": 32,
        "prompt_tokens_per_request": 4214,
        "output_tokens_per_request": 358,
        "cached_prompt_fraction": 0.127,
        "peak_global_context": 4571,
        "page_size": 64,
    },
    "candidate_kernel": {
        "symbol": "flashinfer.decode.trtllm_batch_decode_with_kv_cache",
        "requested_backend": "xqa",
        "kv_dtype": "torch.float8_e5m2",
        "layout": "HND native GQA page-64",
        "dense_kv_repetition": False,
        "supported": False,
        "oracle_pass": False,
        "oracle_status": "not_reached",
        "outcome": raw["error"],
        "failure_stage": raw["stage"],
    },
    "measured_partial_subgraph": {
        "components": components,
        "current_seconds_per_request": current,
        "candidate_seconds_per_request": candidate,
        "savings_seconds_per_request": current - candidate,
        "minimum_required_savings_seconds_per_request": 0.04597286970625021,
        "includes": "BF16 QKV/O prompt and decode projections plus exact cached-prefix Triton prompt attention",
        "excludes": "decode attention and BF16-to-E5M2 KV writes because mandatory candidate XQA faulted first",
        "savings_gate_evaluable": False,
    },
    "hard_gates": {
        "candidate_kernel_supported": False,
        "candidate_kernel_avoids_dense_kv_repetition": True,
        "candidate_oracle_pass": False,
        "savings_gate_pass": False,
    },
    "rows": rows,
    "raw_result": {
        "path": str(raw_path.relative_to(root)),
        "sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
    },
}
atomic(root / "RESULT.json", terminal)
manifest_paths = (
    root / "RESULT.json",
    raw_path,
    root / "global-head256-xqa-20260718t2130z" / "gpu-samples.csv",
    root / "global-head256-xqa-20260718t2130z" / "remote-runner-sha256.txt",
    root / "local-input-sha256.txt",
)
atomic_text(
    root / "SHA256SUMS",
    "".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.relative_to(root)}\n" for path in manifest_paths),
)
