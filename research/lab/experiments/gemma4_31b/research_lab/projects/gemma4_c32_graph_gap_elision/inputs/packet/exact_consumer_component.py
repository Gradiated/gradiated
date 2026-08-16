#!/usr/bin/env python3
"""Production-shaped H200 component and exact decision consumer."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import os
import pathlib
import statistics
import types

import torch
from safetensors import safe_open

from grouped_lm_head import (
    BATCH,
    DEPTHS,
    HIDDEN,
    VOCAB,
    grouped_get_logits,
    project_decode_shapes,
)


WEIGHT_KEY = "model.language_model.embed_tokens.weight"


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


def processor_and_metadata():
    from sglang.srt.layers.logits_processor import LogitsMetadata, LogitsProcessor
    from sglang.srt.model_executor.forward_batch_info import ForwardMode

    processor = object.__new__(LogitsProcessor)
    torch.nn.Module.__init__(processor)
    processor.logit_scale = None
    processor.use_attn_tp_group = False
    processor.use_fp32_lm_head = False
    processor.do_tensor_parallel_all_gather = False
    processor.do_tensor_parallel_all_gather_dp_attn = False
    processor.final_logit_softcapping = 30.0
    processor.vocab_size = VOCAB

    def projection(self, hidden_states, lm_head, embedding_bias=None):
        del self, embedding_bias
        return torch.matmul(
            hidden_states.to(lm_head.weight.dtype), lm_head.weight.T
        )

    processor._compute_lm_head = types.MethodType(projection, processor)
    metadata = LogitsMetadata(forward_mode=ForwardMode.TARGET_VERIFY)
    return LogitsProcessor, processor, metadata


def accepted_prefixes(target_ids: torch.Tensor) -> list[int]:
    proposals = target_ids.clone()
    proposals[:, 5] = (proposals[:, 5] + 1) % VOCAB
    return [
        next(
            (
                depth
                for depth in range(DEPTHS)
                if int(proposals[request, depth])
                != int(target_ids[request, depth])
            ),
            DEPTHS,
        )
        for request in range(BATCH)
    ]


def event_time(operation) -> float:
    start = torch.cuda.Event(enable_timing=True)
    end = torch.cuda.Event(enable_timing=True)
    start.record()
    value = operation()
    end.record()
    end.synchronize()
    del value
    return float(start.elapsed_time(end))


def distribution(operation, warmups: int, repeats: int) -> list[float]:
    for _ in range(warmups):
        value = operation()
        del value
    torch.cuda.synchronize()
    return [event_time(operation) for _ in range(repeats)]


def profiler_summary(control, candidate) -> list[dict]:
    from torch.profiler import ProfilerActivity, profile

    with profile(activities=[ProfilerActivity.CPU, ProfilerActivity.CUDA]) as trace:
        control_value = control()
        candidate_value = candidate()
        torch.cuda.synchronize()
        del control_value, candidate_value
    rows = []
    for event in trace.key_averages():
        device_time = float(
            getattr(event, "self_device_time_total", 0.0)
            or getattr(event, "self_cuda_time_total", 0.0)
        )
        if device_time > 0:
            rows.append(
                {
                    "name": event.key,
                    "count": int(event.count),
                    "self_device_time_us": device_time,
                }
            )
    return sorted(rows, key=lambda row: row["self_device_time_us"], reverse=True)[
        :24
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--repeats", type=int, default=9)
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic(
        invocation,
        {
            "schema_version": 1,
            "pre_science": True,
            "candidate_cuda_invocation_started": False,
            "scientific_invocation_started": False,
        },
    )
    torch.manual_seed(8490)
    torch.cuda.manual_seed_all(8490)
    weight = load_weight(args.weight)
    hidden_states = torch.randn(
        (BATCH * DEPTHS, HIDDEN), device="cuda", dtype=torch.bfloat16
    )
    lm_head = types.SimpleNamespace(weight=weight)
    LogitsProcessor, processor, metadata = processor_and_metadata()
    original = LogitsProcessor._get_logits

    def control():
        return project_decode_shapes(
            original,
            processor,
            hidden_states,
            lm_head,
            metadata,
            None,
            DEPTHS,
        )

    def candidate():
        return grouped_get_logits(processor, hidden_states, lm_head, metadata)

    atomic(
        invocation,
        {
            "schema_version": 1,
            "pre_science": False,
            "candidate_cuda_invocation_started": True,
            "scientific_invocation_started": True,
        },
    )
    candidate_smoke = candidate()
    control_logits = control()
    candidate_logits = candidate()
    replay_logits = candidate()
    torch.cuda.synchronize()

    control_values, control_ids = torch.topk(control_logits, k=2, dim=-1)
    candidate_values, candidate_ids = torch.topk(candidate_logits, k=2, dim=-1)
    replay_values, replay_ids = torch.topk(replay_logits, k=2, dim=-1)
    control_targets = control_ids[:, 0].reshape(BATCH, DEPTHS)
    candidate_targets = candidate_ids[:, 0].reshape(BATCH, DEPTHS)
    replay_targets = replay_ids[:, 0].reshape(BATCH, DEPTHS)
    target_ids_exact = bool(torch.equal(control_targets, candidate_targets))
    top_two_ids_exact = bool(torch.equal(control_ids, candidate_ids))
    replay_exact = bool(
        torch.equal(candidate_ids, replay_ids)
        and torch.equal(candidate_values, replay_values)
    )
    accepted_control = accepted_prefixes(control_targets)
    accepted_candidate = accepted_prefixes(candidate_targets)
    accepted_replay = accepted_prefixes(replay_targets)
    difference = (candidate_logits - control_logits).float()
    control_norm = torch.linalg.vector_norm(control_logits.float())
    numerical = {
        "max_abs": float(difference.abs().max().item()),
        "relative_l2": float(
            (torch.linalg.vector_norm(difference) / control_norm).item()
        ),
        "top_two_ids_exact": top_two_ids_exact,
        "target_ids_exact": target_ids_exact,
        "accepted_target_decisions_exact": (
            accepted_control == accepted_candidate == accepted_replay
        ),
        "candidate_replay_exact": replay_exact,
        "control_top_two_ids_sha256": tensor_hash(control_ids),
        "candidate_top_two_ids_sha256": tensor_hash(candidate_ids),
        "candidate_top_two_values_sha256": tensor_hash(candidate_values),
        "replay_top_two_values_sha256": tensor_hash(replay_values),
    }
    del candidate_smoke, control_logits, candidate_logits, replay_logits
    del control_values, control_ids, candidate_values, candidate_ids
    del replay_values, replay_ids, difference
    torch.cuda.empty_cache()

    control_ms = distribution(control, warmups=3, repeats=args.repeats)
    candidate_ms = distribution(candidate, warmups=3, repeats=args.repeats)
    profile_rows = profiler_summary(control, candidate)
    control_median = statistics.median(control_ms)
    candidate_median = statistics.median(candidate_ms)
    positive = candidate_median < control_median
    pass_value = (
        target_ids_exact
        and top_two_ids_exact
        and numerical["accepted_target_decisions_exact"]
        and replay_exact
        and positive
    )
    result = {
        "schema_version": 1,
        "classification": "production_shaped_exact_consumer_component",
        "component_pass": pass_value,
        "hardware": torch.cuda.get_device_name(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "triton": __import__("triton").__version__,
        "geometry": {
            "depths": DEPTHS,
            "batch": BATCH,
            "hidden": HIDDEN,
            "vocab": VOCAB,
            "dtype": "bfloat16",
            "layout": "request-major hidden; tied weight [vocab,hidden]",
        },
        "source": {
            "candidate": str(pathlib.Path(__file__).with_name("grouped_lm_head.py")),
            "candidate_sha256": sha256(
                pathlib.Path(__file__).with_name("grouped_lm_head.py")
            ),
            "consumer": "SGLang LogitsProcessor._get_logits",
            "consumer_source_sha256": (
                "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14"
            ),
            "weight_file": str(args.weight),
            "weight_file_sha256": sha256(args.weight),
            "weight_key": WEIGHT_KEY,
        },
        "numerical": numerical,
        "accepted_prefixes": {
            "control": accepted_control,
            "candidate": accepted_candidate,
            "replay": accepted_replay,
        },
        "timing_ms": {
            "control_samples": control_ms,
            "candidate_samples": candidate_ms,
            "control_median": control_median,
            "candidate_median": candidate_median,
            "fractional_change": candidate_median / control_median - 1.0,
        },
        "launch_telemetry": profile_rows,
    }
    atomic(args.artifact_root / "COMPONENT_RESULT.json", result)
    atomic(args.artifact_root / "COMPONENT_TERMINAL.json", result)
    return 0 if pass_value else 2


if __name__ == "__main__":
    raise SystemExit(main())
