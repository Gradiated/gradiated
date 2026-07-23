#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib


HERE = pathlib.Path(__file__).resolve().parent


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    binding = json.loads((HERE / "ITERATION2_BINDING.json").read_text())
    contract = json.loads((HERE / "ITERATION2_CONTRACT.json").read_text())
    design = binding["frozen_design"]
    expected = {
        "candidate_module_sha256": "two_stage_local_attention.py",
        "benchmark_sha256": "iteration2_benchmark.py",
        "analyzer_sha256": "analyze_iteration2.py",
        "remote_producer_sha256": "remote_iteration2.sh",
        "remote_consumer_sha256": "remote_iteration2_consumer.sh",
        "contract_sha256": "ITERATION2_CONTRACT.json",
        "physical_model_sha256": "ITERATION2_PHYSICAL_MODEL.json",
    }
    for field, name in expected.items():
        assert design[field] == sha256(HERE / name), field
    assert design["qk_recomputed"] is False
    assert contract["scope"]["q_heads"] == 32
    assert contract["scope"]["kv_heads"] == 16
    assert contract["scope"]["kv_cache_dtype"] == "fp8_e5m2"
    assert contract["scope"]["sliding_window_size"] == 1024
    assert contract["scope"]["representative_workspace_bytes"] == 303038464
    source = (HERE / "two_stage_local_attention.py").read_text()
    assert source.count("tl.dot(q") == 2
    assert "_qk_softmax_stage" in source and "_value_stage" in source
    assert "VALUE_SLICES = 2" in source and "BLOCK_DV_SLICE = 128" in source
    print(
        json.dumps(
            {
                "pass": True,
                "candidate": design["candidate_path"],
                "candidate_sha256": design["candidate_module_sha256"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
