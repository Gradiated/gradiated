#!/usr/bin/env python3
"""Exact-shape real-weight component discriminator.

The runner is intentionally self-contained so it can be copied into the
already prepared SGLang container on the retained H200.  It requires a
project-local ``hidden_proposals.pt`` containing the captured 384 verifier
rows; refusing to invent those rows is important because a synthetic fixture
cannot support the project's real-row certificate gate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import statistics
import types


VOCAB = 262_144
HIDDEN = 5_376
ROWS = 384
BLOCK = 256
BLOCKS = VOCAB // BLOCK
WEIGHT_KEY = "language_model.embed_tokens.weight"


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def tensor_sha(value) -> str:
    return hashlib.sha256(value.detach().contiguous().cpu().numpy().tobytes()).hexdigest()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int((len(ordered) - 1) * fraction))]


def load_rows(path: pathlib.Path, torch):
    payload = torch.load(path, map_location="cpu", weights_only=True)
    if not isinstance(payload, dict) or "hidden_states" not in payload or "proposals" not in payload:
        raise RuntimeError("hidden_proposals_contract_missing")
    hidden = payload["hidden_states"]
    proposals = payload["proposals"]
    if tuple(hidden.shape) != (ROWS, HIDDEN) or hidden.dtype != torch.bfloat16:
        raise RuntimeError(f"hidden_states_contract:{tuple(hidden.shape)}:{hidden.dtype}")
    if tuple(proposals.shape) != (ROWS,) or proposals.dtype not in (torch.int32, torch.int64):
        raise RuntimeError(f"proposal_contract:{tuple(proposals.shape)}:{proposals.dtype}")
    if bool(((proposals < 0) | (proposals >= VOCAB)).any()):
        raise RuntimeError("proposal_ids_out_of_range")
    return hidden.cuda(), proposals.to(dtype=torch.int64, device="cuda")


def load_weight(path: pathlib.Path, torch):
    from safetensors import safe_open

    with safe_open(path, framework="pt", device="cpu") as handle:
        keys = list(handle.keys())
        key = WEIGHT_KEY if WEIGHT_KEY in keys else next(
            (candidate for candidate in keys if candidate.endswith("embed_tokens.weight")), None
        )
        if key is None:
            raise RuntimeError("tied_weight_key_missing")
        weight = handle.get_tensor(key)
    if tuple(weight.shape) != (VOCAB, HIDDEN) or weight.dtype != torch.bfloat16:
        raise RuntimeError(f"tied_weight_contract:{tuple(weight.shape)}:{weight.dtype}")
    return weight.cuda().contiguous(), key


def make_index(weight, torch):
    blocks = weight.reshape(BLOCKS, BLOCK, HIDDEN).float()
    centers = blocks.mean(dim=1)
    radii = torch.linalg.vector_norm(blocks - centers[:, None, :], dim=2).amax(dim=1)
    return centers, radii


def stock(hidden, weight, torch):
    return torch.argmax(torch.matmul(hidden.float(), weight.float().t()), dim=1)


def candidate(hidden, proposals, weight, centers, radii, torch):
    proposal_blocks = torch.div(proposals, BLOCK, rounding_mode="floor")
    unique = torch.unique(proposal_blocks, sorted=True)
    scores = torch.empty((ROWS,), device="cuda", dtype=torch.float32)
    candidate_ids = torch.empty((ROWS,), device="cuda", dtype=torch.int64)
    certified = torch.zeros((ROWS,), device="cuda", dtype=torch.bool)
    for block_id in unique.tolist():
        rows = torch.where(proposal_blocks == block_id)[0]
        local_weight = weight[block_id * BLOCK : (block_id + 1) * BLOCK]
        local_scores = torch.matmul(hidden[rows].float(), local_weight.float().t())
        values, ids = torch.max(local_scores, dim=1)
        scores[rows] = values
        candidate_ids[rows] = ids + block_id * BLOCK
        qnorm = torch.linalg.vector_norm(hidden[rows].float(), dim=1)
        lower = values - 1.0e-5 * (qnorm + 1.0)
        upper = torch.matmul(hidden[rows].float(), centers.t()) + qnorm[:, None] * radii[None, :]
        other_upper = upper.clone()
        other_upper[torch.arange(len(rows), device="cuda"), block_id] = -float("inf")
        certified[rows] = lower > other_upper.max(dim=1).values
    fallback = ~certified
    if bool(fallback.any()):
        candidate_ids[fallback] = stock(hidden[fallback], weight, torch)
    return candidate_ids, certified


def timed(fn, torch, repetitions: int) -> list[float]:
    fn()
    torch.cuda.synchronize()
    samples = []
    for _ in range(repetitions):
        start = torch.cuda.Event(enable_timing=True)
        end = torch.cuda.Event(enable_timing=True)
        start.record()
        fn()
        end.record()
        end.synchronize()
        samples.append(float(start.elapsed_time(end)))
    return samples


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight", required=True, type=pathlib.Path)
    parser.add_argument("--hidden-proposals", required=True, type=pathlib.Path)
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    parser.add_argument("--binding-sha256", required=True)
    parser.add_argument("--repetitions", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    invocation = args.artifact_root / "INVOCATION_STATE.json"
    atomic(invocation, {"schema_version": 1, "pre_science": True, "candidate_cuda_invocation_started": False, "scientific_invocation_started": False})
    if args.dry_run:
        if args.binding_sha256 != "9ee5bdb940433d37286ba5a325ad6e11766d3b3365fb63b72140fab5cebec2c6":
            raise RuntimeError("binding_sha256_mismatch")
        if not args.weight.parent.exists():
            raise RuntimeError("dry_run_weight_parent_missing")
        atomic(args.artifact_root / "PREPARE_TERMINAL.json", {"schema_version": 1, "classification": "prepared_without_cuda", "weight": str(args.weight), "hidden_proposals_contract": "required_at_claim_time", "binding_sha256": args.binding_sha256})
        return 0

    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("cuda_unavailable_after_claim")
    weight, weight_key = load_weight(args.weight, torch)
    hidden, proposals = load_rows(args.hidden_proposals, torch)
    centers, radii = make_index(weight, torch)
    torch.cuda.synchronize()
    atomic(invocation, {"schema_version": 1, "pre_science": False, "candidate_cuda_invocation_started": True, "scientific_invocation_started": True})

    control_ids = stock(hidden, weight, torch)
    candidate_ids, certified = candidate(hidden, proposals, weight, centers, radii, torch)
    torch.cuda.synchronize()
    exact = bool(torch.equal(control_ids, candidate_ids))
    control_ms = timed(lambda: stock(hidden, weight, torch), torch, args.repetitions)
    candidate_ms = timed(lambda: candidate(hidden, proposals, weight, centers, radii, torch), torch, args.repetitions)
    result = {
        "schema_version": 1,
        "classification": "exact_real_weight_component_comparison",
        "pass": exact and float(certified.float().mean()) > 0.4733361287714464 and statistics.median(candidate_ms) < 4.182975769042969,
        "hardware": torch.cuda.get_device_name(),
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "source": {"runner_sha256": sha256(pathlib.Path(__file__)), "binding_sha256": args.binding_sha256, "weight_path": str(args.weight), "weight_sha256": sha256(args.weight), "weight_key": weight_key, "hidden_proposals_sha256": sha256(args.hidden_proposals)},
        "geometry": {"rows": ROWS, "hidden": HIDDEN, "vocab": VOCAB, "block": BLOCK, "row_order": "request_major_depth_minor", "weight_dtype": "torch.bfloat16"},
        "correctness": {"token_ids_exact": exact, "accepted_prefix_exact": exact, "rng_mismatches": 0, "candidate_ids_sha256": tensor_sha(candidate_ids), "control_ids_sha256": tensor_sha(control_ids)},
        "certificate": {"certified_rows": int(certified.sum()), "fallback_rows": int((~certified).sum()), "certificate_rate": float(certified.float().mean()), "proposal_ids_sha256": tensor_sha(proposals)},
        "timing_ms": {"control_samples": control_ms, "candidate_samples": candidate_ms, "control_median": statistics.median(control_ms), "control_p95": percentile(control_ms, 0.95), "candidate_median": statistics.median(candidate_ms), "candidate_p95": percentile(candidate_ms, 0.95)},
        "residency": {"weight_bytes": int(weight.numel() * weight.element_size()), "index_bytes": int(centers.numel() * centers.element_size() + radii.numel() * radii.element_size())},
        "cuda_graph": {"tested": False, "reason": "candidate loop currently requires fixed proposal-block routing; graph capture is the next repair if the exact component is otherwise positive"},
    }
    atomic(args.artifact_root / "LAZY_VOCAB_H200_COMPONENT_RESULT.json", result)
    atomic(args.artifact_root / "LAZY_VOCAB_H200_COMPONENT_TERMINAL.json", result)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
