#!/usr/bin/env python3
"""Later exact H200 CUDA-graph discriminator for the buffer-direct grouped head."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import statistics
import types

import torch
from safetensors import safe_open

from exact_consumer_component import (
    WEIGHT_KEY,
    accepted_prefixes,
    processor_and_metadata,
)
from grouped_lm_head import (
    BATCH,
    DEPTHS,
    HIDDEN,
    LOGITS_PROCESSOR_SHA256,
    VOCAB,
    grouped_get_logits_buffer_direct,
    project_decode_shapes,
)


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def tensor_hash(value: torch.Tensor) -> str:
    return hashlib.sha256(
        value.detach().contiguous().cpu().view(torch.uint8).numpy().tobytes()
    ).hexdigest()


def load_weight(path: pathlib.Path) -> torch.Tensor:
    with safe_open(path, framework="pt", device="cpu") as handle:
        if WEIGHT_KEY not in handle.keys():
            raise RuntimeError(f"bound_weight_key_missing:{WEIGHT_KEY}")
        value = handle.get_tensor(WEIGHT_KEY)
    if tuple(value.shape) != (VOCAB, HIDDEN) or value.dtype != torch.bfloat16:
        raise RuntimeError(f"bound_weight_contract:{tuple(value.shape)}:{value.dtype}")
    return value.to("cuda", non_blocking=False).contiguous()


def capture(operation):
    operation()
    torch.cuda.synchronize()
    graph = torch.cuda.CUDAGraph()
    with torch.cuda.graph(graph):
        returned = operation()
    return graph, returned


def replay_distribution(graph: torch.cuda.CUDAGraph, repeats: int) -> list[float]:
    for _ in range(3):
        graph.replay()
    torch.cuda.synchronize()
    samples = []
    for _ in range(repeats):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        graph.replay()
        end.record()
        end.synchronize()
        samples.append(float(start.elapsed_time(end)))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--repeats", type=int, default=9)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation_path = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "pre_science": True,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
        },
    )

    from sglang.srt.layers import logits_processor

    consumer_path = pathlib.Path(logits_processor.__file__)
    consumer_sha256 = sha256(consumer_path)
    if consumer_sha256 != LOGITS_PROCESSOR_SHA256:
        raise RuntimeError(f"bound_consumer_source_mismatch:{consumer_sha256}")

    torch.manual_seed(8510)
    torch.cuda.manual_seed_all(8510)
    weight = load_weight(args.weight)
    hidden_states = torch.randn(
        (BATCH * DEPTHS, HIDDEN), device="cuda", dtype=torch.bfloat16
    )
    lm_head = types.SimpleNamespace(weight=weight)
    LogitsProcessor, processor, control_metadata = processor_and_metadata()
    _, _, candidate_metadata = processor_and_metadata()
    control_buffer = torch.empty(
        (BATCH * DEPTHS, VOCAB), device="cuda", dtype=torch.float32
    )
    candidate_buffer = torch.empty_like(control_buffer)
    control_metadata.next_token_logits_buffer = control_buffer
    candidate_metadata.next_token_logits_buffer = candidate_buffer
    original = LogitsProcessor._get_logits

    def control():
        return project_decode_shapes(
            original,
            processor,
            hidden_states,
            lm_head,
            control_metadata,
            None,
            DEPTHS,
        )

    def candidate():
        return grouped_get_logits_buffer_direct(
            processor, hidden_states, lm_head, candidate_metadata
        )

    atomic(
        invocation_path,
        {
            "schema_version": 1,
            "pre_science": False,
            "candidate_cuda_invocation_started": True,
            "scientific_invocation_started": True,
        },
    )
    candidate()
    torch.cuda.synchronize()
    control_graph, control_return = capture(control)
    candidate_graph, candidate_return = capture(candidate)
    control_graph.replay()
    candidate_graph.replay()
    torch.cuda.synchronize()
    control_logits = control_buffer.clone()
    candidate_logits = candidate_buffer.clone()
    candidate_graph.replay()
    torch.cuda.synchronize()
    replay_logits = candidate_buffer.clone()

    control_values, control_ids = torch.topk(control_logits, k=2, dim=-1)
    candidate_values, candidate_ids = torch.topk(candidate_logits, k=2, dim=-1)
    replay_values, replay_ids = torch.topk(replay_logits, k=2, dim=-1)
    control_targets = control_ids[:, 0].reshape(BATCH, DEPTHS)
    candidate_targets = candidate_ids[:, 0].reshape(BATCH, DEPTHS)
    replay_targets = replay_ids[:, 0].reshape(BATCH, DEPTHS)
    difference = (candidate_logits - control_logits).float()
    control_norm = torch.linalg.vector_norm(control_logits.float())
    numerical = {
        "max_abs": float(difference.abs().max().item()),
        "relative_l2": float(
            (torch.linalg.vector_norm(difference) / control_norm).item()
        ),
        "top_two_ids_exact": bool(torch.equal(control_ids, candidate_ids)),
        "top_two_values_exact": bool(torch.equal(control_values, candidate_values)),
        "target_ids_exact": bool(torch.equal(control_targets, candidate_targets)),
        "accepted_target_decisions_exact": (
            accepted_prefixes(control_targets)
            == accepted_prefixes(candidate_targets)
            == accepted_prefixes(replay_targets)
        ),
        "candidate_replay_exact": bool(
            torch.equal(candidate_ids, replay_ids)
            and torch.equal(candidate_values, replay_values)
        ),
    }
    buffer_contract = {
        "returned_same_object": candidate_return is candidate_buffer,
        "captured_return_same_object": candidate_return is candidate_buffer,
        "data_ptr": candidate_buffer.data_ptr(),
        "dtype": str(candidate_buffer.dtype),
        "shape": list(candidate_buffer.shape),
        "stride": list(candidate_buffer.stride()),
        "control_return_same_object": control_return is control_buffer,
    }
    control_ms = replay_distribution(control_graph, args.repeats)
    candidate_ms = replay_distribution(candidate_graph, args.repeats)
    passed = (
        numerical["max_abs"] == 0.0
        and numerical["relative_l2"] == 0.0
        and numerical["top_two_ids_exact"]
        and numerical["top_two_values_exact"]
        and numerical["target_ids_exact"]
        and numerical["accepted_target_decisions_exact"]
        and numerical["candidate_replay_exact"]
        and buffer_contract["returned_same_object"]
        and buffer_contract["captured_return_same_object"]
        and tuple(candidate_buffer.shape) == (BATCH * DEPTHS, VOCAB)
        and candidate_buffer.dtype == torch.float32
        and tuple(candidate_buffer.stride()) == (VOCAB, 1)
    )
    result = {
        "schema_version": 1,
        "classification": "exact_h200_graph_safe_buffer_discriminator",
        "pass": passed,
        "hardware": torch.cuda.get_device_name(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "triton": __import__("triton").__version__,
        "source": {
            "candidate_path": str(
                pathlib.Path(__file__).with_name("grouped_lm_head.py")
            ),
            "candidate_sha256": sha256(
                pathlib.Path(__file__).with_name("grouped_lm_head.py")
            ),
            "candidate_symbol": "grouped_get_logits_buffer_direct",
            "kernel_symbol": "depth_interleaved_grouped_lm_head",
            "consumer_path": str(consumer_path),
            "consumer_symbol": (
                "sglang.srt.layers.logits_processor.LogitsProcessor._get_logits"
            ),
            "consumer_sha256": consumer_sha256,
            "weight_path": str(args.weight),
            "weight_sha256": sha256(args.weight),
            "weight_key": WEIGHT_KEY,
        },
        "geometry": {
            "batch": BATCH,
            "depths": DEPTHS,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "hidden_dtype": "torch.bfloat16",
            "weight_dtype": "torch.bfloat16",
            "buffer_dtype": "torch.float32",
            "row_order": "request_major_depth_minor",
        },
        "buffer_contract": buffer_contract,
        "numerical": numerical,
        "hashes": {
            "control_top_two_ids": tensor_hash(control_ids),
            "candidate_top_two_ids": tensor_hash(candidate_ids),
            "control_top_two_values": tensor_hash(control_values),
            "candidate_top_two_values": tensor_hash(candidate_values),
            "replay_top_two_values": tensor_hash(replay_values),
        },
        "timing_ms": {
            "control_graph_replay_samples": control_ms,
            "candidate_graph_replay_samples": candidate_ms,
            "control_median": statistics.median(control_ms),
            "candidate_median": statistics.median(candidate_ms),
            "fractional_change": (
                statistics.median(candidate_ms) / statistics.median(control_ms)
                - 1.0
            ),
        },
    }
    atomic(args.artifact_root / "GRAPH_SAFE_BUFFER_RESULT.json", result)
    atomic(args.artifact_root / "GRAPH_SAFE_BUFFER_TERMINAL.json", result)
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
