#!/usr/bin/env python3
"""Persist the exact host-mirror operations used by the pinned consumer."""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys

import torch


ROOT = Path(__file__).resolve().parent
ARTIFACT = ROOT / "artifacts" / "seq-lens-cpu-tensor-contract-20260726t0359z" / "SEQ_LENS_CPU_CONTRACT.json"


class Batch:
    seq_lens = torch.tensor([4214, 17, 9], dtype=torch.int32)
    seq_lens_cpu = None


def main() -> int:
    spec = importlib.util.spec_from_file_location("driver_contract", ROOT / "forward_batch_dual_cache_driver.py")
    assert spec and spec.loader
    driver = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = driver
    spec.loader.exec_module(driver)
    batch = Batch()
    changed = driver.materialize_seq_lens_cpu(batch)
    mirror = batch.seq_lens_cpu
    checks = {
        "changed_absent_only": changed,
        "cpu_tensor": isinstance(mirror, torch.Tensor) and mirror.device.type == "cpu",
        "dtype_preserved": mirror.dtype == batch.seq_lens.dtype,
        "index": int(mirror[1]) == 17,
        "length": len(mirror) == 3,
        "sum": int(mirror.sum()) == 4240,
    }
    stock = torch.tensor([5], dtype=torch.int64)
    batch.seq_lens_cpu = stock
    checks["present_stock_preserved"] = not driver.materialize_seq_lens_cpu(batch) and batch.seq_lens_cpu is stock
    payload = {
        "schema_version": 1,
        "kind": "exact_seq_lens_cpu_index_len_sum_contract",
        "driver_sha256": hashlib.sha256((ROOT / "forward_batch_dual_cache_driver.py").read_bytes()).hexdigest(),
        "source": {"values": [4214, 17, 9], "dtype": "torch.int32", "device": "cpu"},
        "mirror": {"type": type(mirror).__name__, "dtype": str(mirror.dtype), "device": mirror.device.type, "index_1": int(mirror[1]), "length": len(mirror), "sum": int(mirror.sum())},
        "checks": checks,
        "pass": all(checks.values()),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    part = ARTIFACT.with_suffix(".part")
    part.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")
    part.replace(ARTIFACT)
    print(json.dumps(payload, sort_keys=True))
    return 0 if payload["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
