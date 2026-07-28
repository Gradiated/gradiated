#!/usr/bin/env python3
"""Exact component runner with an attribution boundary after every first arm."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import time

import torch
from torch.utils.cpp_extension import load

from accuracy_redesign_component_runner import (
    CONTROL_SHA256, fixture, high_precision_reference, install_control_import_stubs,
    invoke, load_module, timed_ms,
)
from streaming_accuracy_component_runner import CandidateAdapter, resource_usage


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temp, path)


def distribution(values: list[float]) -> dict:
    return {"samples_ms": values, "minimum_ms": min(values), "p50_ms": statistics.median(values), "maximum_ms": max(values)}


def first_arm(name: str, module, tensors, output, *, local: bool, head_dim: int, root: Path, candidate: bool) -> dict | None:
    marker = root / f"{name.upper()}_COMPLETION.json"
    atomic(marker, {"arm": name, "state": "submitted", "candidate_cuda_invocation_started": candidate, "at_unix_s": time.time()})
    try:
        invoke(module, tensors, output, local=local, head_dim=head_dim)
        torch.cuda.synchronize()
    except Exception as error:
        result = {"arm": name, "state": "cuda_fault", "candidate_cuda_invocation_started": candidate, "error": repr(error), "at_unix_s": time.time()}
        atomic(marker, result)
        return result
    result = {"arm": name, "state": "completed", "candidate_cuda_invocation_started": candidate, "at_unix_s": time.time()}
    atomic(marker, result)
    return None


def evaluate(control, candidate, *, local: bool, head_dim: int, kv_heads: int, prefix: int, seed: int, repetitions: int, root: Path) -> dict:
    tensors = fixture(seed=seed, head_dim=head_dim, kv_heads=kv_heads, prefix=prefix)
    stock_a, stock_b, actual = (torch.empty_like(tensors["q"]) for _ in range(3))
    for name, module, output, is_candidate in (("stock_a", control, stock_a, False), ("stock_b", control, stock_b, False), ("candidate", candidate, actual, True)):
        fault = first_arm(name, module, tensors, output, local=local, head_dim=head_dim, root=root, candidate=is_candidate)
        if fault:
            return {"result": "arm_isolated_cuda_fault", "fault": fault}
    reference = high_precision_reference(tensors, head_dim=head_dim, kv_heads=kv_heads, prefix=prefix, local=local)
    delta, aa = actual.double() - reference, stock_a.float() - stock_b.float()
    candidate_samples, control_samples = [], []
    for index in range(repetitions):
        first, second = ((candidate, actual, candidate_samples), (control, stock_a, control_samples)) if index % 2 == 0 else ((control, stock_a, control_samples), (candidate, actual, candidate_samples))
        first[2].append(timed_ms(lambda: invoke(first[0], tensors, first[1], local=local, head_dim=head_dim)))
        second[2].append(timed_ms(lambda: invoke(second[0], tensors, second[1], local=local, head_dim=head_dim)))
    return {"result": "completed", "geometry": {"kind": "local_d256" if local else "global_d512", "head_dim": head_dim, "kv_heads": kv_heads, "prefix_tokens": prefix, "batch": 32, "query_rows": 384, "query_heads": 32}, "stock_aa": {"max_abs": float(aa.abs().max()), "relative_l2": float(torch.linalg.vector_norm(aa) / torch.linalg.vector_norm(stock_a.float()).clamp_min(1e-30))}, "candidate_vs_fp64": {"relative_l2": float(torch.linalg.vector_norm(delta) / torch.linalg.vector_norm(reference).clamp_min(1e-30)), "max_abs": float(delta.abs().max()), "all_finite": bool(torch.isfinite(actual).all())}, "unchanged_output_consumer_square_sum": float(actual.float().square().sum()), "control": distribution(control_samples), "candidate": distribution(candidate_samples)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--control", required=True, type=Path)
    parser.add_argument("--repetitions", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    root = args.artifact_root
    root.mkdir(parents=True, exist_ok=True)
    (root / "build").mkdir(parents=True, exist_ok=True)
    atomic(root / "INVOCATION_STATE.json", {"schema_version": 1, "phase": "pre_science", "candidate_cuda_invocation_started": False})
    if digest(args.source) != args.source_sha256 or digest(args.control) != CONTROL_SHA256:
        raise RuntimeError("immutable_input_digest_mismatch")
    if not torch.cuda.is_available() or torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("sm90_cuda_required")
    os.environ["TORCH_CUDA_ARCH_LIST"] = "9.0a"
    headers = [f"-I/usr/local/lib/python3.12/dist-packages/nvidia/{name}/include" for name in "cublas cuda_cupti cuda_nvrtc cuda_runtime cudnn cufft cufile curand cusolver cusparse cusparselt nccl nvjitlink nvshmem nvtx".split()]
    extension = load(name=f"packed_m384_isolated_{args.source_sha256[:12]}", sources=[str(args.source)], extra_cuda_cflags=[*headers, "-include", "/usr/local/cuda/include/math_constants.h", "-include", "/project/cluster_dim_compat.h", "-O3", "-lineinfo", "-arch=sm_90a"], build_directory=str((root / "build").resolve()), verbose=True)
    resources = resource_usage(Path(extension.__file__), root)
    install_control_import_stubs()
    control, candidate = load_module("packed_m384_isolated_control", args.control), CandidateAdapter(extension)
    atomic(root / "INVOCATION_STATE.json", {"schema_version": 1, "phase": "stock_arms_started", "candidate_cuda_invocation_started": False})
    local = evaluate(control, candidate, local=True, head_dim=256, kv_heads=16, prefix=1024, seed=args.seed, repetitions=args.repetitions, root=root)
    rows = [local]
    if local["result"] == "completed":
        rows.append(evaluate(control, candidate, local=False, head_dim=512, kv_heads=4, prefix=4214, seed=args.seed + 1, repetitions=args.repetitions, root=root / "global_d512"))
    fault = next((row for row in rows if row["result"] != "completed"), None)
    terminal = {"schema_version": 1, "type": "packed_m384_streaming_arm_isolated_result", "result": "arm_isolated_cuda_fault" if fault else "component_completed", "scientific_result": True, "rows": rows, "compiled_resources": resources, "identity": {"source_sha256": digest(args.source), "control_sha256": digest(args.control), "extension_sha256": digest(Path(extension.__file__)), "gpu": torch.cuda.get_device_name(), "capability": list(torch.cuda.get_device_capability()), "torch": torch.__version__}, "protocol": "stock A, stock B, and candidate each synchronized and atomically persisted before proceeding"}
    atomic(root / "PACKED_M384_STREAMING_ARM_ISOLATED_RESULT.json", terminal)
    atomic(root / "INVOCATION_STATE.json", {"schema_version": 1, "phase": "scientific_terminal_recorded", "candidate_cuda_invocation_started": any((row.get("fault") or {}).get("candidate_cuda_invocation_started", False) for row in rows), "terminal": "PACKED_M384_STREAMING_ARM_ISOLATED_RESULT.json"})
    print(json.dumps(terminal, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
