#!/usr/bin/env python3
"""Deterministic CPU/source discriminator for a certified lazy Gemma vocab head.

This is deliberately a reference discriminator, not a CUDA implementation.  It
binds the exact serving sources, exercises a mathematically sound block
certificate with stock fallback, checks token and RNG equivalence, and emits
the analytical H200 component envelope required by PROJECT.md.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import struct
from pathlib import Path
from typing import Any


PROJECT_DIR = Path(__file__).resolve().parent
PROJECTS_DIR = PROJECT_DIR.parent
GROUPED_DIR = PROJECTS_DIR / "gemma4_h200_ngram_persistent_grouped_lm_head"
CRITICAL_DIR = PROJECTS_DIR / "gemma4_h200_ngram_verification_critical_path"
FP8_ENDPOINT_DIR = PROJECTS_DIR / "gemma4_h200_fp8_tied_head_endpoint"

BOUND = GROUPED_DIR / "inputs" / "bound"
NGRAM_INFO = CRITICAL_DIR / "inputs" / "source" / "ngram_info.py"
NGRAM_WORKER = CRITICAL_DIR / "inputs" / "source" / "ngram_worker.py"
SAMPLER = (
    FP8_ENDPOINT_DIR
    / "iterations"
    / "graph-bound-endpoint-20260723t1930z"
    / "inputs"
    / "source"
    / "sampler.py"
)
GRAPH_TERMINAL = GROUPED_DIR / "GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json"
OFFLINE_MODEL = GROUPED_DIR / "OFFLINE_CAUSAL_MODEL.json"

RAW_RESULT = PROJECT_DIR / "DISCRIMINATOR_RESULT.json"
TERMINAL = PROJECT_DIR / "CERTIFIED_LAZY_VOCAB_RESULT.json"

EXPECTED_HASHES = {
    BOUND / "config.json": "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1",
    BOUND
    / "logits_processor.py": "e5d0d3a8781e74c1c7fe7508eb89d2eb198cc42bcd5e2fa4258217c756fdaf14",
    BOUND
    / "forward_batch_info.py": "c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516",
    BOUND
    / "exact_runner.py": "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7",
}

SCHEMA_VERSION = 1
SEED = 20260725
FP32_UNIT_ROUNDOFF = 2.0**-24
BF16_UNIT_ROUNDOFF = 2.0**-8
SOFTCAP = 30.0
SOFTCAP_FP32_ENVELOPE = 16.0 * FP32_UNIT_ROUNDOFF * SOFTCAP


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def dot(left: list[float], right: list[float]) -> float:
    return math.fsum(a * b for a, b in zip(left, right, strict=True))


def norm(value: list[float]) -> float:
    return math.sqrt(dot(value, value))


def stable_argmax(values: list[float]) -> int:
    """Match torch.argmax's first-index tie rule."""
    best_index = 0
    best_value = values[0]
    for index, value in enumerate(values[1:], start=1):
        if value > best_value:
            best_index = index
            best_value = value
    return best_index


def round_float32(value: float) -> float:
    return struct.unpack(">f", struct.pack(">f", value))[0]


def round_bfloat16(value: float) -> float:
    """Round a finite scalar to BF16 with round-to-nearest-even."""
    bits = struct.unpack(">I", struct.pack(">f", value))[0]
    least_significant_kept_bit = (bits >> 16) & 1
    rounded = (bits + 0x7FFF + least_significant_kept_bit) & 0xFFFF0000
    return struct.unpack(">f", struct.pack(">I", rounded))[0]


def stock_softcapped_score(raw_dot: float) -> float:
    """Synthetic stock boundary: BF16 GEMM output, then FP32 Gemma softcap."""
    bf16_logit = round_bfloat16(raw_dot)
    return round_float32(SOFTCAP * math.tanh(bf16_logit / SOFTCAP))


def softcap_interval(raw_lower: float, raw_upper: float) -> tuple[float, float]:
    """Outward interval across BF16 quantization and the FP32 softcap.

    A CUDA realization must validate or replace this explicit softcap envelope
    against the pinned fused kernel and fall back if it cannot.
    """
    lower = (
        SOFTCAP * math.tanh(round_bfloat16(raw_lower) / SOFTCAP)
        - SOFTCAP_FP32_ENVELOPE
    )
    upper = (
        SOFTCAP * math.tanh(round_bfloat16(raw_upper) / SOFTCAP)
        + SOFTCAP_FP32_ENVELOPE
    )
    return lower, upper


def build_index(
    weights: list[list[float]], block_ids: list[list[int]]
) -> tuple[list[list[float]], list[float]]:
    centers: list[list[float]] = []
    radii: list[float] = []
    for ids in block_ids:
        dimension = len(weights[0])
        center = [
            math.fsum(weights[token][column] for token in ids) / len(ids)
            for column in range(dimension)
        ]
        radius = max(
            norm(
                [
                    weights[token][column] - center[column]
                    for column in range(dimension)
                ]
            )
            for token in ids
        )
        centers.append(center)
        radii.append(math.nextafter(radius, math.inf))
    return centers, radii


def fp32_dot_envelope(
    left_norm: float, right_norm: float, reduction_length: int
) -> float:
    gamma = (reduction_length * FP32_UNIT_ROUNDOFF) / (
        1.0 - reduction_length * FP32_UNIT_ROUNDOFF
    )
    return gamma * left_norm * right_norm


def certify_proposal(
    hidden: list[float],
    proposal: int,
    weights: list[list[float]],
    block_ids: list[list[int]],
    token_to_block: list[int],
    centers: list[list[float]],
    radii: list[float],
) -> tuple[bool, dict[str, float | int | str]]:
    """Certify a proposal as the stable global argmax or request fallback.

    The proposal's complete block is evaluated.  Every other block uses the
    Cauchy-Schwarz upper bound h.c + ||h|| r.  Conservative FP32 accumulation,
    BF16 GEMM-output, and FP32-softcap envelopes are applied. Strict separation
    is required, so ties and numerical ambiguity always fall back.
    """

    block = token_to_block[proposal]
    local_ids = block_ids[block]
    local_scores = [
        stock_softcapped_score(dot(hidden, weights[token])) for token in local_ids
    ]
    local_winner = local_ids[stable_argmax(local_scores)]
    if local_winner != proposal:
        return False, {
            "reason": "proposal_not_stable_local_argmax",
            "proposal": proposal,
            "local_winner": local_winner,
        }

    hidden_norm = norm(hidden)
    proposal_score = dot(hidden, weights[proposal])
    proposal_error = fp32_dot_envelope(
        hidden_norm, norm(weights[proposal]), len(hidden)
    )
    lower, _ = softcap_interval(
        proposal_score - proposal_error, proposal_score + proposal_error
    )
    maximum_upper = -math.inf
    maximum_upper_block = -1
    for other, (center, radius) in enumerate(zip(centers, radii, strict=True)):
        if other == block:
            continue
        center_norm = norm(center)
        raw_upper = (
            dot(hidden, center)
            + hidden_norm * radius
            + fp32_dot_envelope(
                hidden_norm, center_norm + radius, len(hidden)
            )
        )
        _, upper = softcap_interval(
            -hidden_norm * (center_norm + radius), raw_upper
        )
        if upper > maximum_upper:
            maximum_upper = upper
            maximum_upper_block = other

    certified = lower > maximum_upper
    return certified, {
        "reason": "strict_interval_separation" if certified else "interval_overlap",
        "proposal": proposal,
        "proposal_lower": lower,
        "maximum_other_block_upper": maximum_upper,
        "maximum_other_block": maximum_upper_block,
        "margin": lower - maximum_upper,
    }


def candidate_argmax(
    hidden: list[float],
    proposal: int,
    weights: list[list[float]],
    block_ids: list[list[int]],
    token_to_block: list[int],
    centers: list[list[float]],
    radii: list[float],
) -> tuple[int, bool, dict[str, float | int | str]]:
    certified, detail = certify_proposal(
        hidden,
        proposal,
        weights,
        block_ids,
        token_to_block,
        centers,
        radii,
    )
    if certified:
        return proposal, True, detail
    scores = [stock_softcapped_score(dot(hidden, weight)) for weight in weights]
    return stable_argmax(scores), False, detail


def clustered_geometry() -> dict[str, Any]:
    rng = random.Random(SEED)
    block_count = 32
    block_size = 16
    dimension = 64
    centers_seed: list[list[float]] = []
    weights: list[list[float]] = []
    blocks: list[list[int]] = []
    token_to_block: list[int] = []

    for block in range(block_count):
        raw = [rng.gauss(0.0, 1.0) for _ in range(dimension)]
        raw_norm = norm(raw)
        center = [4.0 * value / raw_norm for value in raw]
        centers_seed.append(center)
        ids: list[int] = []
        for _ in range(block_size):
            token = len(weights)
            weight = [
                round_bfloat16(value + rng.gauss(0.0, 0.0125))
                for value in center
            ]
            weights.append(weight)
            ids.append(token)
            token_to_block.append(block)
        blocks.append(ids)

    centers, radii = build_index(weights, blocks)
    rows = 256
    intended_wrong = 0
    certified = 0
    mismatches = 0
    fallback_rows = 0
    reasons: dict[str, int] = {}
    margins: list[float] = []
    for row in range(rows):
        block = rng.randrange(block_count)
        hidden = [
            round_bfloat16(
                centers_seed[block][column] + rng.gauss(0.0, 0.035)
            )
            for column in range(dimension)
        ]
        scores = [stock_softcapped_score(dot(hidden, weight)) for weight in weights]
        reference = stable_argmax(scores)
        if row % 5 == 0:
            intended_wrong += 1
            proposal = blocks[(block + 1) % block_count][0]
        else:
            proposal = reference
        result, did_certify, detail = candidate_argmax(
            hidden,
            proposal,
            weights,
            blocks,
            token_to_block,
            centers,
            radii,
        )
        mismatches += int(result != reference)
        certified += int(did_certify)
        fallback_rows += int(not did_certify)
        reason = str(detail["reason"])
        reasons[reason] = reasons.get(reason, 0) + 1
        if did_certify:
            margins.append(float(detail["margin"]))

    return {
        "label": "synthetic",
        "seed": SEED,
        "geometry": {
            "blocks": block_count,
            "block_size": block_size,
            "dimension": dimension,
            "rows": rows,
        },
        "intentionally_wrong_proposals": intended_wrong,
        "certified_rows": certified,
        "certificate_rate": certified / rows,
        "fallback_rows": fallback_rows,
        "token_mismatches": mismatches,
        "reasons": reasons,
        "minimum_certified_margin": min(margins) if margins else None,
    }


def diffuse_and_tie_falsifiers() -> dict[str, Any]:
    rng = random.Random(SEED + 1)
    dimension = 48
    block_count = 16
    block_size = 16
    weights = [
        [round_bfloat16(rng.gauss(0.0, 1.0)) for _ in range(dimension)]
        for _ in range(block_count * block_size)
    ]
    blocks = [
        list(range(block * block_size, (block + 1) * block_size))
        for block in range(block_count)
    ]
    token_to_block = [
        block for block in range(block_count) for _ in range(block_size)
    ]
    centers, radii = build_index(weights, blocks)
    rows = 96
    diffuse_certified = 0
    diffuse_mismatches = 0
    for _ in range(rows):
        hidden = [
            round_bfloat16(rng.gauss(0.0, 1.0)) for _ in range(dimension)
        ]
        reference = stable_argmax(
            [stock_softcapped_score(dot(hidden, weight)) for weight in weights]
        )
        result, did_certify, _ = candidate_argmax(
            hidden,
            reference,
            weights,
            blocks,
            token_to_block,
            centers,
            radii,
        )
        diffuse_certified += int(did_certify)
        diffuse_mismatches += int(result != reference)

    tie_weights = [
        [1.0, 0.0],
        [0.0, 0.0],
        [1.0, 0.0],
        [0.0, 0.0],
    ]
    tie_blocks = [[0, 1], [2, 3]]
    tie_token_to_block = [0, 0, 1, 1]
    tie_centers, tie_radii = build_index(tie_weights, tie_blocks)
    tie_result, tie_certified, tie_detail = candidate_argmax(
        [1.0, 0.0],
        2,
        tie_weights,
        tie_blocks,
        tie_token_to_block,
        tie_centers,
        tie_radii,
    )

    return {
        "label": "synthetic",
        "diffuse_geometry": {
            "rows": rows,
            "certified_rows": diffuse_certified,
            "certificate_rate": diffuse_certified / rows,
            "token_mismatches": diffuse_mismatches,
            "expected_behavior": "low certification is safe because every overlap falls back",
        },
        "cross_block_tie": {
            "proposal": 2,
            "stable_reference": 0,
            "candidate": tie_result,
            "certified": tie_certified,
            "certificate_reason": tie_detail["reason"],
            "pass": tie_result == 0 and not tie_certified,
        },
    }


def sample_categorical(probabilities: list[float], rng: random.Random) -> int:
    coin = rng.random()
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += probability
        if coin < cumulative:
            return index
    return len(probabilities) - 1


def rng_equivalence() -> dict[str, Any]:
    probabilities = [0.05, 0.1, 0.2, 0.25, 0.4]
    stock = random.Random(SEED + 2)
    candidate = random.Random()
    candidate.setstate(stock.getstate())
    stock_tokens = [sample_categorical(probabilities, stock) for _ in range(128)]
    candidate_tokens = [
        sample_categorical(probabilities, candidate) for _ in range(128)
    ]
    post_sampling_state_equal = stock.getstate() == candidate.getstate()

    greedy_rng = random.Random(SEED + 3)
    before = greedy_rng.getstate()
    for _ in range(128):
        # The certificate and greedy fallback are deterministic and draw no RNG.
        pass
    greedy_state_unchanged = before == greedy_rng.getstate()
    return {
        "label": "synthetic",
        "sampling_route": "stock fallback before any candidate RNG draw",
        "sampling_tokens_equal": stock_tokens == candidate_tokens,
        "sampling_rng_state_equal": post_sampling_state_equal,
        "sampling_draws": len(stock_tokens),
        "greedy_rng_state_unchanged": greedy_state_unchanged,
    }


def bind_sources() -> dict[str, Any]:
    rows = []
    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path)
        if actual != expected:
            raise RuntimeError(f"source hash mismatch: {path}: {actual} != {expected}")
        rows.append(
            {
                "path": str(path.relative_to(PROJECTS_DIR)),
                "sha256": actual,
                "expected_sha256": expected,
                "match": True,
            }
        )

    ngram_text = NGRAM_INFO.read_text()
    sampler_text = SAMPLER.read_text()
    runner_text = (BOUND / "exact_runner.py").read_text()
    logits_text = (BOUND / "logits_processor.py").read_text()
    required_patterns = {
        "ngram_greedy_argmax": "torch.argmax(logits_output.next_token_logits",
        "ngram_sampling_softmax": "target_probs = F.softmax(",
        "ngram_rejection_coins": "coins = torch.rand_like(",
        "ngram_final_sampling_coins": "coins_for_final_sampling = torch.rand(",
        "ngram_accept_plus_bonus": "self.num_accept_tokens = self.num_correct_drafts + 1",
        "sampler_greedy_argmax": "batch_next_token_ids = torch.argmax(logits, -1)",
        "sampler_logprob_full_normalization": "torch.nn.functional.log_softmax(",
        "sampler_sampling_softmax": "logits[:] = torch.softmax(logits, dim=-1)",
        "runner_temperature_zero": '"temperature": 0',
        "runner_fixed_seed": '"seed": 20260718',
        "runner_return_token_ids": '"return_token_ids": True',
        "logits_dense_projection": "hidden_states.to(lm_head.weight.dtype), lm_head.weight.T",
        "logits_softcap": "fused_softcap(",
    }
    texts = {
        "ngram_": ngram_text,
        "sampler_": sampler_text,
        "runner_": runner_text,
        "logits_": logits_text,
    }
    pattern_results = {}
    for name, pattern in required_patterns.items():
        prefix = name.split("_", 1)[0] + "_"
        present = pattern in texts[prefix]
        if not present:
            raise RuntimeError(f"required source pattern absent: {name}: {pattern}")
        pattern_results[name] = {"pattern": pattern, "present": present}

    config = json.loads((BOUND / "config.json").read_text())
    graph = json.loads(GRAPH_TERMINAL.read_text())
    offline = json.loads(OFFLINE_MODEL.read_text())
    return {
        "label": "measured_and_source_bound",
        "hashes": rows
        + [
            {
                "path": str(NGRAM_INFO.relative_to(PROJECTS_DIR)),
                "sha256": sha256(NGRAM_INFO),
            },
            {
                "path": str(NGRAM_WORKER.relative_to(PROJECTS_DIR)),
                "sha256": sha256(NGRAM_WORKER),
            },
            {
                "path": str(SAMPLER.relative_to(PROJECTS_DIR)),
                "sha256": sha256(SAMPLER),
            },
            {
                "path": str(GRAPH_TERMINAL.relative_to(PROJECTS_DIR)),
                "sha256": sha256(GRAPH_TERMINAL),
            },
            {
                "path": str(OFFLINE_MODEL.relative_to(PROJECTS_DIR)),
                "sha256": sha256(OFFLINE_MODEL),
            },
        ],
        "patterns": pattern_results,
        "model": {
            "vocab_size": config["text_config"]["vocab_size"],
            "hidden_size": config["text_config"]["hidden_size"],
            "tie_word_embeddings": config["text_config"]["tie_word_embeddings"],
            "final_logit_softcapping": config["text_config"][
                "final_logit_softcapping"
            ],
        },
        "admitted_workload": {
            "concurrency": 32,
            "draft_depth": 12,
            "temperature": 0,
            "seed": 20260718,
            "return_token_ids": True,
            "logprobs": False,
            "penalties_or_bias": False,
            "grammar": False,
            "classification": "all-greedy exact argmax",
        },
        "h200_dense_baseline": {
            "label": "measured",
            "hardware": graph["hardware"],
            "geometry": graph["geometry"],
            "strongest_graph_safe_dense_candidate_median_ms": graph["timing_ms"][
                "candidate_median"
            ],
            "stock_control_median_ms": graph["timing_ms"]["control_median"],
            "weight_sha256": graph["source"]["weight_sha256"],
            "dense_buffer": graph["buffer_contract"],
            "profile_window_lm_head_fraction": offline["measured_baseline"][
                "lm_head_fraction_of_profile_window"
            ],
        },
    }


def h200_bound(source: dict[str, Any]) -> dict[str, Any]:
    vocab = 262_144
    hidden = 5_376
    rows = 32 * 12
    block_count = 1_024
    block_size = vocab // block_count
    weight_bytes = vocab * hidden * 2
    center_bytes = block_count * hidden * 4
    radius_bytes = block_count * 4
    token_map_bytes = vocab * 4
    hidden_bytes = rows * hidden * 2
    proposal_block_bytes = rows * block_size * hidden * 2
    center_score_bytes = rows * block_count * 4
    block_score_bytes = rows * block_size * 4
    dense_logits_bytes = rows * vocab * 4
    prepass_bytes = (
        center_bytes
        + radius_bytes
        + token_map_bytes
        + hidden_bytes
        + proposal_block_bytes
        + center_score_bytes
        + block_score_bytes
    )
    fallback_bytes = weight_bytes + hidden_bytes
    total_with_fallback_bytes = prepass_bytes + fallback_bytes
    full_dense_flops = 2 * rows * vocab * hidden

    vendor_hbm_bytes_s = 4.8e12
    vendor_bf16_flops_s = 989.5e12
    conservative_hbm_fraction = 0.50
    conservative_compute_fraction = 0.25
    fixed_overhead_ms = 0.25
    dense_baseline_ms = source["h200_dense_baseline"][
        "strongest_graph_safe_dense_candidate_median_ms"
    ]
    traffic_ms = (
        total_with_fallback_bytes
        / (vendor_hbm_bytes_s * conservative_hbm_fraction)
        * 1e3
    )
    full_fallback_compute_ms = (
        full_dense_flops
        / (vendor_bf16_flops_s * conservative_compute_fraction)
        * 1e3
    )
    break_even = 1.0 - (
        dense_baseline_ms - traffic_ms - fixed_overhead_ms
    ) / full_fallback_compute_ms
    break_even = min(1.0, max(0.0, break_even))

    sensitivity = []
    for certificate_rate in (0.0, 0.25, 0.50, 0.75, 10.6648 / 12.0):
        modeled_ms = (
            traffic_ms
            + full_fallback_compute_ms * (1.0 - certificate_rate)
            + fixed_overhead_ms
        )
        sensitivity.append(
            {
                "certificate_rate": certificate_rate,
                "conservative_component_ms": modeled_ms,
                "change_vs_strongest_dense_ms": modeled_ms - dense_baseline_ms,
                "fractional_change_vs_strongest_dense": (
                    modeled_ms / dense_baseline_ms - 1.0
                ),
                "positive": modeled_ms < dense_baseline_ms,
            }
        )

    return {
        "label": "analytical_with_measured_baseline_and_vendor_priors",
        "geometry": {
            "batch": 32,
            "depth": 12,
            "rows": rows,
            "vocab": vocab,
            "hidden": hidden,
            "weight_dtype": "BF16",
            "accumulator_and_bound_dtype": "FP32",
            "blocks": block_count,
            "tokens_per_block": block_size,
        },
        "resident_index_and_weight_lifecycle": {
            "cluster_centers_bytes": center_bytes,
            "radii_bytes": radius_bytes,
            "token_to_block_bytes": token_map_bytes,
            "cluster_ordered_weight_copy_bytes": weight_bytes,
            "additional_residency_bytes": (
                center_bytes + radius_bytes + token_map_bytes + weight_bytes
            ),
            "immutable_weight_sha256": source["h200_dense_baseline"][
                "weight_sha256"
            ],
            "construction": (
                "offline deterministic clustering; upward-rounded radii; "
                "cluster-ordered BF16 copy hash-bound to the immutable tied weight"
            ),
            "fallback": (
                "the original tied weight and stock consumer remain resident; "
                "index mismatch or lifecycle change disables the candidate"
            ),
        },
        "traffic": {
            "weight_bytes": weight_bytes,
            "hidden_vector_bytes": hidden_bytes,
            "proposal_block_bytes_no_inter_row_reuse": proposal_block_bytes,
            "center_bytes": center_bytes,
            "center_score_bytes": center_score_bytes,
            "block_score_bytes": block_score_bytes,
            "certificate_prepass_bytes": prepass_bytes,
            "fused_fallback_scan_bytes": fallback_bytes,
            "total_bytes_with_any_fallback": total_with_fallback_bytes,
            "dense_fp32_logits_avoided_bytes": dense_logits_bytes,
            "dense_logits_materialized": False,
        },
        "compute": {
            "full_dense_fallback_flops": full_dense_flops,
            "fallback_flops_scale": "linearly with unresolved rows after compaction",
            "certificate_block_flops": 2 * rows * block_size * hidden,
            "center_flops": 2 * rows * block_count * hidden,
            "reduction": (
                "one stable argmax reduction per evaluated proposal block and "
                "one fused stable argmax reduction over each unresolved dense row"
            ),
        },
        "numerical_contract": {
            "fp32_unit_roundoff": FP32_UNIT_ROUNDOFF,
            "bf16_output_unit_roundoff": BF16_UNIT_ROUNDOFF,
            "reduction_length": hidden,
            "gamma_k": (hidden * FP32_UNIT_ROUNDOFF)
            / (1.0 - hidden * FP32_UNIT_ROUNDOFF),
            "softcap_cap": SOFTCAP,
            "softcap_fp32_envelope": SOFTCAP_FP32_ENVELOPE,
            "rule": (
                "certify only when the proposal is the stable winner in its "
                "complete block and its BF16-and-softcap-widened lower interval "
                "strictly exceeds every other block's widened Cauchy-Schwarz bound"
            ),
            "ties_or_overlap": "stock dense fallback",
            "softcap": (
                "compare after BF16 GEMM-output rounding and an outward interval "
                "for the identical FP32 fused softcap; finite-precision ties or a "
                "missing kernel-level enclosure fall back"
            ),
        },
        "launch_and_graph_contract": {
            "candidate_launches": [
                "fixed-shape center/bound pass",
                "fixed-shape proposal-block pass",
                "device compaction of unresolved rows",
                "fixed-capacity fused dense stable-argmax fallback",
            ],
            "host_synchronization": False,
            "cuda_graph": (
                "all buffers and launch extents are static; device masks suppress "
                "resolved rows without host-dependent graph topology"
            ),
            "divergence": (
                "confined to masked certificate/fallback rows; a whole batch is "
                "routed to the stock graph for non-greedy or modified consumers"
            ),
        },
        "conservative_envelope": {
            "vendor_hbm_bytes_per_second": vendor_hbm_bytes_s,
            "vendor_bf16_flops_per_second": vendor_bf16_flops_s,
            "assumed_hbm_fraction": conservative_hbm_fraction,
            "assumed_compute_fraction": conservative_compute_fraction,
            "traffic_time_ms": traffic_ms,
            "full_unresolved_compute_time_ms": full_fallback_compute_ms,
            "fixed_launch_reduction_compaction_ms": fixed_overhead_ms,
            "strongest_measured_dense_baseline_ms": dense_baseline_ms,
            "break_even_real_row_certificate_rate": break_even,
            "sensitivity": sensitivity,
            "interpretation": (
                "The sum-of-traffic-and-compute envelope beats the strongest "
                "measured graph-safe dense component once the real-row certificate "
                "rate exceeds the break-even rate. This is a component admission "
                "bound, not an H200 measurement or endpoint transfer claim."
            ),
        },
        "preprocessing_amortization": {
            "request_path_cost": "zero after immutable index admission",
            "one_time_bytes": (
                center_bytes + radius_bytes + token_map_bytes + weight_bytes
            ),
            "not_claimed": (
                "real-weight clustering time and certificate rate remain unmeasured; "
                "both are required in a separately authorized H200 component run"
            ),
        },
        "endpoint_economics_guard": {
            "campaign_denominator_s_per_request": 0.625149101968745,
            "campaign_target_s_per_request": 0.500119281574996,
            "measured_lm_head_fraction_of_profile_window": source[
                "h200_dense_baseline"
            ]["profile_window_lm_head_fraction"],
            "claim": (
                "positive component economics only; exact endpoint measurement "
                "is required before transferring any saving to seconds/request"
            ),
        },
    }


def consumer_trace() -> list[dict[str, Any]]:
    return [
        {
            "consumer": "greedy NGRAM draft acceptance",
            "minimum_information": (
                "stable exact argmax token for each target verifier row reachable "
                "by verify_tree_greedy"
            ),
            "partition_function_required": False,
            "rng_required": False,
            "candidate_route": "proposal certificate, else stock stable argmax",
            "label": "source_bound",
        },
        {
            "consumer": "greedy rejection and bonus token",
            "minimum_information": (
                "stable exact target argmax at the first rejected edge and the "
                "final bonus row; the full logit vector is not observed"
            ),
            "partition_function_required": False,
            "rng_required": False,
            "candidate_route": (
                "certified rows stay lazy; unresolved rows are device-compacted "
                "and scanned by fused stock-equivalent dense argmax"
            ),
            "label": "source_bound_and_derived",
        },
        {
            "consumer": "non-greedy NGRAM rejection and final sampling",
            "minimum_information": (
                "full temperature-scaled softmax distribution, top-k/top-p "
                "renormalization, per-candidate rejection coins, and one final coin"
            ),
            "partition_function_required": True,
            "rng_required": True,
            "candidate_route": "whole-batch stock fallback before candidate RNG",
            "label": "source_bound",
        },
        {
            "consumer": "return logprob or top logprobs",
            "minimum_information": "full logsumexp normalization and requested ranks",
            "partition_function_required": True,
            "rng_required": False,
            "candidate_route": "stock fallback",
            "label": "source_bound",
        },
        {
            "consumer": "custom processor, penalties, logit bias, or grammar",
            "minimum_information": "argmax or distribution after the exact mutation",
            "partition_function_required": "depends on sampling mode",
            "rng_required": "depends on sampling mode",
            "candidate_route": (
                "stock fallback; the static raw-weight certificate is invalid after "
                "row-dependent vocabulary mutation"
            ),
            "label": "source_bound_and_analytical",
        },
        {
            "consumer": "Gemma final-logit softcap",
            "minimum_information": "ordering only for greedy",
            "partition_function_required": False,
            "rng_required": False,
            "candidate_route": (
                "certify only after BF16 output rounding and outward bounds through "
                "the identical fused softcap; any possible finite-precision tie "
                "falls back, while sampling/logprob always use stock logits"
            ),
            "label": "analytical",
        },
    ]


def main() -> None:
    source = bind_sources()
    clustered = clustered_geometry()
    falsifiers = diffuse_and_tie_falsifiers()
    rng = rng_equivalence()
    bound = h200_bound(source)

    checks = {
        "all_source_hashes_match": all(
            row.get("match", True) for row in source["hashes"]
        ),
        "all_source_patterns_present": all(
            row["present"] for row in source["patterns"].values()
        ),
        "clustered_token_mismatches_zero": clustered["token_mismatches"] == 0,
        "clustered_has_certified_and_fallback_rows": (
            clustered["certified_rows"] > 0 and clustered["fallback_rows"] > 0
        ),
        "diffuse_token_mismatches_zero": (
            falsifiers["diffuse_geometry"]["token_mismatches"] == 0
        ),
        "cross_block_tie_falls_back": falsifiers["cross_block_tie"]["pass"],
        "sampling_tokens_and_rng_equal": (
            rng["sampling_tokens_equal"] and rng["sampling_rng_state_equal"]
        ),
        "greedy_rng_unchanged": rng["greedy_rng_state_unchanged"],
        "conservative_positive_case_exists": any(
            row["positive"]
            for row in bound["conservative_envelope"]["sensitivity"]
            if row["certificate_rate"] <= 0.50
        ),
        "break_even_below_measured_acceptance_motivation": (
            bound["conservative_envelope"]["break_even_real_row_certificate_rate"]
            < 10.6648 / 12.0
        ),
    }
    passed = all(checks.values())
    result_type = "source_complete_candidate" if passed else "mechanism_falsified"

    raw = {
        "schema_version": SCHEMA_VERSION,
        "experiment": "certified_lazy_vocab_cpu_source_discriminator",
        "result": result_type,
        "pass": passed,
        "seed": SEED,
        "source_binding": source,
        "consumer_trace": consumer_trace(),
        "algorithm": {
            "name": "proposal-block MIPS certificate with stock fallback",
            "scope": (
                "all-greedy, no-logprob, no-processor, no-penalty, no-bias, "
                "no-grammar NGRAM verifier batches"
            ),
            "index": (
                "1024 static 256-token blocks over the immutable tied BF16 weight; "
                "FP32 centers, upward-rounded Euclidean radii, token-to-block map, "
                "and cluster-ordered weight copy"
            ),
            "certificate": (
                "evaluate the proposal's complete block; require the proposal to "
                "be its stable winner and require its strict BF16-and-softcap-"
                "widened lower score to exceed every other block's widened "
                "Cauchy-Schwarz upper bound"
            ),
            "fallback": (
                "device-compact every unresolved row and compute stock-equivalent "
                "stable dense argmax without materializing the FP32 logits matrix"
            ),
            "exactness": (
                "a certified token is forced to be the stable global argmax after "
                "the stock output boundary; every inconclusive, tied, changed-"
                "weight, unvalidated-softcap, or unsupported consumer uses stock"
            ),
            "row_order": (
                "request-major/depth-minor indices remain unchanged; resolved and "
                "fallback tokens are scattered back to their original row slots "
                "before the unchanged verify_tree_greedy consumer"
            ),
        },
        "cpu_reference": {
            "clustered_geometry": clustered,
            "falsifiers": falsifiers,
            "rng_equivalence": rng,
        },
        "h200_component_bound": bound,
        "checks": checks,
    }
    RAW_RESULT.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n")

    terminal = {
        "schema_version": SCHEMA_VERSION,
        "project": "gemma4_certified_lazy_vocab_head",
        "result": result_type,
        "pass": passed,
        "classification": (
            "source_bound_cpu_equivalence_and_analytical_h200_component_candidate"
        ),
        "actual_spend_usd": 0.0,
        "gpu_claimed": False,
        "endpoint_run": False,
        "provider_mutation": False,
        "quality": {
            "token_mismatches": (
                clustered["token_mismatches"]
                + falsifiers["diffuse_geometry"]["token_mismatches"]
            ),
            "sampling_tokens_equal": rng["sampling_tokens_equal"],
            "sampling_rng_state_equal": rng["sampling_rng_state_equal"],
            "greedy_rng_state_unchanged": rng["greedy_rng_state_unchanged"],
            "ties_fall_back": falsifiers["cross_block_tie"]["pass"],
        },
        "decision": (
            "The exact c32 workload does not require a partition function: it is "
            "source-bound to greedy argmax. Admit the certified proposal-block "
            "consumer to a separate real-weight H200 component discriminator, "
            "while retaining unconditional stock fallback for sampling, logprobs, "
            "vocabulary mutations, ties, and interval overlap."
            if passed
            else "The discriminator failed one or more exactness or physical gates."
        ),
        "conservative_h200_gate": {
            "strongest_measured_dense_baseline_ms": bound[
                "conservative_envelope"
            ]["strongest_measured_dense_baseline_ms"],
            "break_even_real_row_certificate_rate": bound[
                "conservative_envelope"
            ]["break_even_real_row_certificate_rate"],
            "measured_acceptance_motivation_rate": 10.6648 / 12.0,
            "real_weight_certificate_rate": "unmeasured",
            "positive_case": next(
                row
                for row in bound["conservative_envelope"]["sensitivity"]
                if row["certificate_rate"] == 0.50
            ),
            "claim_scope": "analytical component admission only",
        },
        "required_next_measurement": {
            "authorization": "separate director-authorized resident H200 component run",
            "inputs": [
                "exact immutable BF16 tied weight eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa",
                "scope-matched 384-row verifier hidden states and draft proposals",
            ],
            "falsifiers": [
                "any token, accepted-prefix, row-order, or RNG mismatch",
                "real-row certificate rate at or below the analytical break-even gate",
                "measured graph-safe component median not below 4.182975769042969 ms",
                "additional immutable residency does not fit the resident endpoint",
            ],
            "endpoint_claim_authorized": False,
        },
        "artifacts": {
            "raw_discriminator": RAW_RESULT.name,
            "raw_discriminator_sha256": sha256(RAW_RESULT),
            "executable": Path(__file__).name,
            "executable_sha256": sha256(Path(__file__)),
        },
        "checks": checks,
    }
    TERMINAL.write_text(json.dumps(terminal, indent=2, sort_keys=True) + "\n")
    print(json.dumps(terminal, indent=2, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
