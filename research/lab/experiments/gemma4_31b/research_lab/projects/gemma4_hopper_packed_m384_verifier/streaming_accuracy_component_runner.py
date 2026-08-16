#!/usr/bin/env python3
"""Lifecycle-pure future H100 runner for the streaming cluster candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import time
from typing import Any

import torch
from torch.utils.cpp_extension import load

from accuracy_redesign_component_runner import (
    CONTROL_SHA256,
    fixture,
    high_precision_reference,
    install_control_import_stubs,
    invoke,
    load_module,
    timed_ms,
)


PRIOR = {
    "local_d256": {
        "relative_l2": 0.026936529204249382,
        "max_abs": 0.00927734375,
        "control_ms": 1.3924800157546997,
        "candidate_ms": 0.4918079972267151,
    },
    "global_d512": {
        "relative_l2": 0.029003974050283432,
        "max_abs": 0.0047607421875,
        "control_ms": 3.2703680992126465,
        "candidate_ms": 2.910111904144287,
    },
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def distribution(values: list[float]) -> dict[str, object]:
    return {
        "samples_ms": values,
        "minimum_ms": min(values),
        "p50_ms": statistics.median(values),
        "maximum_ms": max(values),
    }


def candidate_graph_replay(
    candidate, tensors, output, *, local: bool, head_dim: int
) -> bool:
    invoke(candidate, tensors, output, local=local, head_dim=head_dim)
    torch.cuda.synchronize()
    expected = output.clone()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        invoke(candidate, tensors, output, local=local, head_dim=head_dim)
    graph.replay()
    torch.cuda.synchronize()
    return bool(torch.equal(expected, output))


class CandidateAdapter:
    def __init__(self, extension) -> None:
        self.extension = extension

    def extend_attention_fwd(
        self,
        q,
        k,
        v,
        output,
        k_cache,
        v_cache,
        qo_indptr,
        kv_indptr,
        kv_indices,
        custom_mask,
        is_causal,
        mask_indptr,
        max_len_extend,
        k_scale,
        v_scale,
        sm_scale,
        **kwargs,
    ) -> None:
        if not is_causal or max_len_extend != 12:
            raise RuntimeError("streaming_runner_exact_causal_m384_required")
        self.extension.forward(
            q,
            k,
            v,
            output,
            k_cache,
            v_cache,
            qo_indptr,
            kv_indptr,
            kv_indices,
            custom_mask,
            mask_indptr,
            q.shape[-1] == 256,
            float(k_scale),
            float(v_scale),
            float(sm_scale),
        )


def resource_usage(module_path: Path, artifact_root: Path) -> dict[str, object]:
    completed = subprocess.run(
        ["cuobjdump", "--dump-resource-usage", str(module_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    raw_path = artifact_root / "cuobjdump-resource-usage.txt"
    raw_path.write_text(
        completed.stdout + completed.stderr, encoding="utf-8"
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"cuobjdump_resource_usage_failed:{completed.returncode}"
        )
    register_counts = [
        int(value)
        for value in re.findall(r"\bREG:(\d+)\b", completed.stdout)
    ]
    stack_bytes = [
        int(value)
        for value in re.findall(r"\bSTACK:(\d+)\b", completed.stdout)
    ]
    shared_bytes = [
        int(value)
        for value in re.findall(r"\bSHARED:(\d+)\b", completed.stdout)
    ]
    if not register_counts:
        raise RuntimeError("cuobjdump_register_metadata_missing")
    return {
        "raw_path": raw_path.name,
        "raw_sha256": digest(raw_path),
        "register_counts": register_counts,
        "maximum_registers_per_thread": max(register_counts),
        "stack_bytes": stack_bytes,
        "maximum_stack_bytes": max(stack_bytes, default=0),
        "shared_bytes": shared_bytes,
        "maximum_static_shared_bytes": max(shared_bytes, default=0),
    }


def evaluate(
    control,
    candidate,
    *,
    local: bool,
    head_dim: int,
    kv_heads: int,
    prefix: int,
    seed: int,
    repetitions: int,
) -> dict[str, object]:
    tensors = fixture(
        seed=seed, head_dim=head_dim, kv_heads=kv_heads, prefix=prefix
    )
    stock_a = torch.empty_like(tensors["q"])
    stock_b = torch.empty_like(tensors["q"])
    actual = torch.empty_like(tensors["q"])
    invoke(control, tensors, stock_a, local=local, head_dim=head_dim)
    invoke(control, tensors, stock_b, local=local, head_dim=head_dim)
    invoke(candidate, tensors, actual, local=local, head_dim=head_dim)
    torch.cuda.synchronize()
    reference = high_precision_reference(
        tensors,
        head_dim=head_dim,
        kv_heads=kv_heads,
        prefix=prefix,
        local=local,
    )
    delta = actual.double() - reference
    aa_delta = stock_a.float() - stock_b.float()
    graph_bitwise = candidate_graph_replay(
        candidate,
        tensors,
        actual,
        local=local,
        head_dim=head_dim,
    )
    candidate_samples: list[float] = []
    control_samples: list[float] = []
    for index in range(repetitions):
        if index % 2 == 0:
            candidate_samples.append(
                timed_ms(
                    lambda: invoke(
                        candidate,
                        tensors,
                        actual,
                        local=local,
                        head_dim=head_dim,
                    )
                )
            )
            control_samples.append(
                timed_ms(
                    lambda: invoke(
                        control,
                        tensors,
                        stock_a,
                        local=local,
                        head_dim=head_dim,
                    )
                )
            )
        else:
            control_samples.append(
                timed_ms(
                    lambda: invoke(
                        control,
                        tensors,
                        stock_a,
                        local=local,
                        head_dim=head_dim,
                    )
                )
            )
            candidate_samples.append(
                timed_ms(
                    lambda: invoke(
                        candidate,
                        tensors,
                        actual,
                        local=local,
                        head_dim=head_dim,
                    )
                )
            )
    kind = "local_d256" if local else "global_d512"
    relative_l2 = float(
        torch.linalg.vector_norm(delta)
        / torch.linalg.vector_norm(reference).clamp_min(1e-30)
    )
    max_abs = float(delta.abs().max().item())
    prior = PRIOR[kind]
    candidate_distribution = distribution(candidate_samples)
    control_distribution = distribution(control_samples)
    maximum_candidate_ms = prior["candidate_ms"] + 0.2 * (
        prior["control_ms"] - prior["candidate_ms"]
    )
    return {
        "kind": kind,
        "geometry": {
            "batch": 32,
            "query_rows": 384,
            "query_heads": 32,
            "kv_heads": kv_heads,
            "head_dim": head_dim,
            "prefix_tokens": prefix,
            "page_size": 1,
        },
        "stock_aa": {
            "max_abs": float(aa_delta.abs().max().item()),
            "relative_l2": float(
                torch.linalg.vector_norm(aa_delta)
                / torch.linalg.vector_norm(stock_a.float()).clamp_min(1e-30)
            ),
        },
        "candidate_vs_fp64": {
            "relative_l2": relative_l2,
            "max_abs": max_abs,
            "all_finite": bool(torch.isfinite(actual).all().item()),
        },
        "closed_v2_improvement_factor": {
            "relative_l2": prior["relative_l2"] / relative_l2,
            "max_abs": prior["max_abs"] / max_abs,
        },
        "graph_replay_bitwise": graph_bitwise,
        "unchanged_output_consumer_square_sum": float(
            actual.float().square().sum().item()
        ),
        "control": control_distribution,
        "candidate": candidate_distribution,
        "maximum_candidate_ms": maximum_candidate_ms,
        "gates": {
            "numerical": (
                relative_l2 <= prior["relative_l2"] / 10.0
                and max_abs <= prior["max_abs"] / 10.0
            ),
            "timing": (
                float(candidate_distribution["p50_ms"])
                <= maximum_candidate_ms
            ),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=25)
    parser.add_argument("--seed", type=int, default=20260726)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation,
        {
            "schema_version": 1,
            "phase": "pre_science",
            "candidate_cuda_invocation_started": False,
        },
    )
    if digest(args.source) != args.source_sha256:
        raise RuntimeError("streaming_source_digest_mismatch")
    if digest(args.control) != CONTROL_SHA256:
        raise RuntimeError("control_digest_mismatch")
    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable")
    if torch.cuda.get_device_capability() != (9, 0):
        raise RuntimeError("sm90_required")
    source_text = args.source.read_text(encoding="utf-8")
    for forbidden in (
        "packed_m384_attention_v2",
        "partial_numerator",
        "score_workspace",
    ):
        if forbidden in source_text:
            raise RuntimeError(f"forbidden_mechanism_present:{forbidden}")
    os.environ["TORCH_CUDA_ARCH_LIST"] = "9.0a"
    build_directory = args.artifact_root / "build"
    build_directory.mkdir(parents=True, exist_ok=True)
    extension = load(
        name=f"packed_m384_streaming_{args.source_sha256[:12]}",
        sources=[str(args.source.resolve())],
        extra_cuda_cflags=["-O3", "-lineinfo", "-arch=sm_90a"],
        build_directory=str(build_directory.resolve()),
        verbose=True,
    )
    resources = resource_usage(Path(extension.__file__), args.artifact_root)
    install_control_import_stubs()
    control = load_module("packed_m384_streaming_control", args.control)
    candidate = CandidateAdapter(extension)
    atomic(
        invocation,
        {
            "schema_version": 1,
            "phase": "science_started",
            "candidate_cuda_invocation_started": True,
            "started_unix_s": time.time(),
        },
    )
    rows = [
        evaluate(
            control,
            candidate,
            local=True,
            head_dim=256,
            kv_heads=16,
            prefix=1024,
            seed=args.seed,
            repetitions=args.repetitions,
        ),
        evaluate(
            control,
            candidate,
            local=False,
            head_dim=512,
            kv_heads=4,
            prefix=4214,
            seed=args.seed + 1,
            repetitions=args.repetitions,
        ),
    ]
    resources_gate = (
        int(resources["maximum_registers_per_thread"]) <= 64
        and int(resources["maximum_stack_bytes"]) == 0
    )
    correct = all(
        row["candidate_vs_fp64"]["all_finite"]
        and row["gates"]["numerical"]
        and row["graph_replay_bitwise"]
        and row["unchanged_output_consumer_square_sum"] > 0.0
        for row in rows
    )
    fast = all(row["gates"]["timing"] for row in rows)
    terminal = {
        "schema_version": 1,
        "type": "packed_m384_streaming_cluster_component_result",
        "result": (
            "component_positive"
            if correct and fast and resources_gate
            else "typed_none"
        ),
        "correct": correct,
        "fast": fast,
        "compiled_resources_gate": resources_gate,
        "rows": rows,
        "compiled_resources": resources,
        "identity": {
            "source_sha256": digest(args.source),
            "control_sha256": digest(args.control),
            "extension_sha256": digest(Path(extension.__file__)),
            "gpu": torch.cuda.get_device_name(),
            "capability": list(torch.cuda.get_device_capability()),
            "torch": torch.__version__,
        },
    }
    terminal_path = (
        args.artifact_root / "PACKED_M384_STREAMING_COMPONENT_RESULT.json"
    )
    atomic(terminal_path, terminal)
    atomic(
        invocation,
        {
            "schema_version": 1,
            "phase": "scientific_terminal_recorded",
            "candidate_cuda_invocation_started": True,
            "terminal": terminal_path.name,
        },
    )
    print(json.dumps(terminal, indent=2, sort_keys=True))
    return 0 if terminal["result"] == "component_positive" else 2


if __name__ == "__main__":
    raise SystemExit(main())
