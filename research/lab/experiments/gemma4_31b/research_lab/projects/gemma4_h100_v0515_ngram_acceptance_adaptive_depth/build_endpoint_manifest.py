#!/usr/bin/env python3
from __future__ import annotations

import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()

def main() -> None:
    source_root = ROOT / "inputs/candidate-v0.5.15/source/python/sglang/srt"
    files = {}
    for path in sorted(source_root.rglob("*.py")):
        files[str(path.relative_to(ROOT))] = {"bytes": path.stat().st_size, "sha256": sha(path)}
    local = ["adaptive_depth_contract.py", "endpoint_integration.py", "run_endpoint_integration_fixtures.py"]
    for name in local:
        path = ROOT / name
        files[name] = {"bytes": path.stat().st_size, "sha256": sha(path)}
    manifest = {
        "schema_version": 1,
        "manifest_type": "immutable_endpoint_integration_source_and_launch_config",
        "project": "gemma4_h100_v0515_ngram_acceptance_adaptive_depth",
        "source": {
            "runtime_release": "v0.5.15",
            "runtime_commit": "f63458b5beaceabbd9d749b9fc956370e1b649e6",
            "official_image": "docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd",
            "tree_root": "inputs/candidate-v0.5.15/source/python/sglang/srt",
            "files": files,
            "read_only_snapshot": True,
        },
        "integration": {
            "adapter": "endpoint_integration.py",
            "depth_rule": {"batch_size_1_to_7": 12, "batch_size_8_plus": 6},
            "native_producers": [12, 6],
            "active_depth_metadata": True,
            "ragged_result_ownership": True,
            "scheduler_stride": "active_depth",
            "graph_admission": "depth-12 exact shape only",
            "eager_fallback": "depth-6 only; no padding or graph disguise",
            "checkpoint": "none",
        },
        "launch_config": {
            "authorized": False,
            "provider_or_gpu": False,
            "endpoint_requests_submitted": 0,
            "model_checkpoint": None,
            "speculative_algorithm": "NGRAM",
            "speculative_num_draft_tokens_capacity": 12,
            "adaptive_depth_threshold": 8,
            "target_verify_attention": "triton eager for depth 6; existing captured graph only for depth 12",
            "quality_or_economic_claim": False,
        },
    }
    out = ROOT / "ADAPTIVE_DEPTH_ENDPOINT_INTEGRATION_SOURCE_MANIFEST.json"
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"path": str(out), "files": len(files), "manifest_sha256": sha(out)}, indent=2))

if __name__ == "__main__": main()
