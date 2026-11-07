"""Parallelism cost model (TKCC Appendix D) for DeepSeek V4.1 Flash decode.

Per layer, decode time is ``max(compute, bytes / HBM BW) + collectives``;
the step adds the LM head and a fixed per-step overhead that only the
measured forward-pass tier can supply. Expert imbalance follows the paper:
``R_e = 1 - (1 - pi_e)^B`` unique-expert probabilities, Poisson-binomial
per-rank counts, and the expected maximum over ranks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Callable, Iterable, Sequence

MiB = 2**20
GiB = 2**30


@dataclass(frozen=True)
class ModelSpec:
    """Byte and FLOP inputs; defaults are read from the DeepSeek V4.1 Flash checkpoint headers."""

    layers: int = 40
    hidden: int = 5120
    heads: int = 64
    head_dim: int = 512
    window: int = 128
    sparse_topk: int = 512
    compress_ratios: tuple[int, ...] = (0, 0) + (2,) * 18 + (1,) * 20
    index_layers: tuple[int, ...] = (2, 8, 14, 20, 24, 28, 32, 36)
    candidate_source: int = 20
    candidate_entries: int = 2048 * 8
    index_heads: int = 32
    index_dim: int = 128
    experts: int = 384
    topk: int = 6
    expert_bytes: float = 6885.0 * MiB / 384
    expert_params: float = 3 * 5120 * 2304
    attn_bytes: float = 120.9 * MiB
    attn_params: float = 120.9e6
    indexer_bytes: float = 5.3 * MiB
    shared_bytes: float = 33.8 * MiB
    shared_params: float = 3 * 5120 * 2304
    replicated_layer_bytes: float = 7.6 * MiB
    head_bytes: float = 1.233 * GiB
    head_params: float = 129280 * 5120
    kv_entry_bytes: float = 656.0
    index_entry_bytes: float = 132.0
    act_bytes: int = 2
    weights_total_bytes: float = 475.27 * GiB
    engram_bytes: float = 189.13 * GiB


@dataclass(frozen=True)
class ChipSpec:
    name: str
    hbm_bytes: float
    hbm_bw: float
    flops_fp8: float
    flops_fp4: float
    link_bw: float
    collective_alpha: Callable[[str, int], float] = field(default=lambda kind, n: 3e-6, compare=False)
    collective_curve: Callable[[str, int, float], float] | None = field(default=None, compare=False)
    step_overhead_s: float = 0.0
    source: str = "theoretical"


B300_SPEC = ChipSpec(
    name="B300",
    hbm_bytes=275040 * MiB,
    hbm_bw=8.0e12,
    flops_fp8=4.5e15,
    flops_fp4=13.5e15,
    link_bw=900e9,
)


@dataclass(frozen=True)
class Scheme:
    chips: int
    attn_tp: int
    moe: str  # "tp" or "ep"

    @property
    def attn_dp(self) -> int:
        return self.chips // self.attn_tp

    @property
    def label(self) -> str:
        attn = f"TP{self.attn_tp}" if self.attn_dp == 1 else f"DP{self.attn_dp}xTP{self.attn_tp}"
        return f"attn {attn} / MoE {self.moe.upper()}{self.chips}"


def admissible(model: ModelSpec, scheme: Scheme, chip: ChipSpec, max_chips: int) -> bool:
    if scheme.chips > max_chips or scheme.chips < 1:
        return False
    if scheme.chips % scheme.attn_tp or model.heads % scheme.attn_tp:
        return False
    if scheme.moe == "ep" and model.experts % scheme.chips:
        return False
    if scheme.moe == "tp" and (model.expert_params // 3) % scheme.chips:
        return False
    return weight_bytes_per_chip(model, scheme) < 0.92 * chip.hbm_bytes


def enumerate_schemes(model: ModelSpec, chip: ChipSpec, max_chips: int) -> list[Scheme]:
    schemes = []
    for chips in range(1, max_chips + 1):
        for attn_tp in range(1, chips + 1):
            for moe in ("tp", "ep"):
                if moe == "ep" and chips == 1:
                    continue
                scheme = Scheme(chips, attn_tp, moe)
                if admissible(model, scheme, chip, max_chips):
                    schemes.append(scheme)
    return schemes


def weight_bytes_per_chip(model: ModelSpec, scheme: Scheme) -> float:
    per_layer = (
        model.attn_bytes / scheme.attn_tp
        + model.shared_bytes / scheme.attn_tp
        + model.replicated_layer_bytes
        + model.experts * model.expert_bytes / scheme.chips
    )
    indexers = len(model.index_layers) * model.indexer_bytes / scheme.attn_tp
    return model.layers * per_layer + indexers + 2 * model.head_bytes / scheme.chips + model.engram_bytes / scheme.chips


def zipf_routing(experts: int, topk: int, skew: float) -> list[float]:
    """pi(i) = min(1, c / i^a) with sum pi = topk; a = 0 is uniform."""
    if skew == 0:
        return [topk / experts] * experts
    lo, hi = 0.0, float(topk * experts)
    for _ in range(200):
        c = (lo + hi) / 2
        total = sum(min(1.0, c / (i + 1) ** skew) for i in range(experts))
        if total > topk:
            hi = c
        else:
            lo = c
    return [min(1.0, lo / (i + 1) ** skew) for i in range(experts)]


def _poisson_binomial_cdf(probs: Sequence[float]) -> list[float]:
    dist = [1.0]
    for p in probs:
        nxt = [0.0] * (len(dist) + 1)
        for count, mass in enumerate(dist):
            nxt[count] += mass * (1 - p)
            nxt[count + 1] += mass * p
        dist = nxt
    cdf, running = [], 0.0
    for mass in dist:
        running += mass
        cdf.append(min(running, 1.0))
    return cdf


def _binomial_cdf(trials: int, p: float) -> list[float]:
    if trials == 0:
        return [1.0]
    cdf, running = [], 0.0
    log_p = math.log(p) if p > 0 else -math.inf
    log_q = math.log1p(-p) if p < 1 else -math.inf
    for k in range(trials + 1):
        if p in (0.0, 1.0):
            mass = 1.0 if (p == 0 and k == 0) or (p == 1 and k == trials) else 0.0
        else:
            mass = math.exp(math.lgamma(trials + 1) - math.lgamma(k + 1) - math.lgamma(trials - k + 1) + k * log_p + (trials - k) * log_q)
        running += mass
        cdf.append(min(running, 1.0))
    return cdf


def expected_max(cdfs: Iterable[list[float]]) -> float:
    cdfs = list(cdfs)
    top = max(len(c) for c in cdfs)
    total = 0.0
    for x in range(top):
        prod = 1.0
        for cdf in cdfs:
            prod *= cdf[x] if x < len(cdf) else 1.0
        total += 1.0 - prod
    return total


def expert_load(pi: Sequence[float], tokens: int, ranks: int, topk: int) -> tuple[float, float]:
    """Return (E[max unique experts on a rank], E[max (token, expert) pairs on a rank])."""
    per_rank = len(pi) // ranks
    unique_cdfs, pair_cdfs = [], []
    for rank in range(ranks):
        local = pi[rank * per_rank : (rank + 1) * per_rank]
        unique_cdfs.append(_poisson_binomial_cdf([1 - (1 - p) ** tokens for p in local]))
        pair_cdfs.append(_binomial_cdf(tokens * topk, sum(local) / topk))
    return expected_max(unique_cdfs), expected_max(pair_cdfs)


def unique_experts(pi: Sequence[float], tokens: int) -> float:
    return sum(1 - (1 - p) ** tokens for p in pi)


def collective_time(chip: ChipSpec, kind: str, n: int, size: float) -> float:
    if n <= 1:
        return 0.0
    if chip.collective_curve is not None:
        return chip.collective_curve(kind, n, size)
    factor = 2 * (n - 1) / n if kind == "all_reduce" else (n - 1) / n
    return chip.collective_alpha(kind, n) + size * factor / chip.link_bw


@dataclass(frozen=True)
class StepEstimate:
    scheme: Scheme
    batch: int
    context: int
    step_s: float
    memory_s: float
    compute_s: float
    comm_s: float
    fits: bool

    @property
    def tps_per_user(self) -> float:
        return 1.0 / self.step_s

    @property
    def aggregate_tps(self) -> float:
        return self.batch / self.step_s


def decode_step(model: ModelSpec, chip: ChipSpec, scheme: Scheme, batch: int, context: int, pi: Sequence[float] | None = None) -> StepEstimate:
    pi = list(pi) if pi is not None else zipf_routing(model.experts, model.topk, 0.0)
    local_tokens = math.ceil(batch / scheme.attn_dp)
    if scheme.moe == "ep":
        max_unique, max_pairs = expert_load(pi, batch, scheme.chips, model.topk)
        expert_mem = max_unique * model.expert_bytes
        expert_flops = 2 * max_pairs * model.expert_params
    else:
        expert_mem = unique_experts(pi, batch) * model.expert_bytes / scheme.chips
        expert_flops = 2 * batch * model.topk * model.expert_params / scheme.chips
    memory = compute = comm = layers_time = 0.0
    hidden_bytes = model.hidden * model.act_bytes
    for layer in range(model.layers):
        ratio = model.compress_ratios[layer]
        entries = model.window + (min(math.ceil(context / ratio), model.sparse_topk) if ratio else 0)
        kv = local_tokens * entries * model.kv_entry_bytes
        index = 0.0
        index_flops = 0.0
        if layer in model.index_layers:
            scored = math.ceil(context / ratio) if ratio else 0
            if layer > model.candidate_source and ratio == 1:
                scored = min(scored, model.candidate_entries)
            index = local_tokens * scored * model.index_entry_bytes + model.indexer_bytes / scheme.attn_tp
            index_flops = 2 * local_tokens * scored * model.index_heads * model.index_dim / scheme.attn_tp
        attn_mem = model.attn_bytes / scheme.attn_tp + kv + index
        attn_flops = 2 * local_tokens * model.attn_params / scheme.attn_tp + 2 * local_tokens * entries * (model.heads / scheme.attn_tp) * 2 * model.head_dim + index_flops
        shared_mem = model.shared_bytes / scheme.attn_tp
        shared_flops = 2 * local_tokens * model.shared_params / scheme.attn_tp
        layer_mem = attn_mem + shared_mem + expert_mem + model.replicated_layer_bytes
        layer_flops_fp8 = attn_flops + shared_flops
        layer_compute = layer_flops_fp8 / chip.flops_fp8 + expert_flops / chip.flops_fp4
        memory += layer_mem / chip.hbm_bw
        compute += layer_compute
        layer_comm = collective_time(chip, "all_reduce", scheme.attn_tp, local_tokens * hidden_bytes)
        if scheme.moe == "ep":
            dispatch = batch * model.topk * model.hidden * 1 / scheme.chips
            combine = batch * model.topk * hidden_bytes / scheme.chips
            layer_comm += collective_time(chip, "all_to_all", scheme.chips, dispatch)
            layer_comm += collective_time(chip, "all_to_all", scheme.chips, combine)
        else:
            if scheme.attn_dp > 1:
                layer_comm += collective_time(chip, "all_gather", scheme.chips, batch * hidden_bytes)
                layer_comm += collective_time(chip, "reduce_scatter", scheme.chips, batch * hidden_bytes)
            else:
                layer_comm += collective_time(chip, "all_reduce", scheme.chips, batch * hidden_bytes)
        comm += layer_comm
        layers_time += max(layer_mem / chip.hbm_bw, layer_compute)
    head = max(model.head_bytes / scheme.chips / chip.hbm_bw, 2 * batch * model.head_params / scheme.chips / chip.flops_fp8)
    step = layers_time + comm + head + chip.step_overhead_s
    entries_per_request = sum(model.window + (math.ceil(context / r) if r else 0) for r in model.compress_ratios)
    kv_bytes = batch * entries_per_request * model.kv_entry_bytes
    fits = weight_bytes_per_chip(model, scheme) + kv_bytes / scheme.attn_dp < 0.92 * chip.hbm_bytes
    return StepEstimate(scheme, batch, context, step, memory, compute, comm, fits)


def rank_schemes(model: ModelSpec, chip: ChipSpec, batch: int, context: int, max_chips: int, pi: Sequence[float] | None = None) -> list[StepEstimate]:
    estimates = [decode_step(model, chip, s, batch, context, pi) for s in enumerate_schemes(model, chip, max_chips)]
    return sorted((e for e in estimates if e.fits), key=lambda e: -e.tps_per_user)


def tokens_per_minute_per_chip(model: ModelSpec, chip: ChipSpec, scheme: Scheme, isl: int, osl: int, tps_sla: float, pi: Sequence[float] | None = None, prefill_tokens_per_s: float = 0.0) -> float:
    """Paper eq. 6 for a single replica: largest batch meeting the per-user TPS SLA."""
    best = 0
    for batch in (1, 2, 4, 8, 16, 32, 48, 64, 96, 128, 192, 256):
        estimate = decode_step(model, chip, scheme, batch, isl + osl // 2, pi)
        if estimate.fits and estimate.tps_per_user >= tps_sla:
            best = batch
    if best == 0:
        return 0.0
    step = decode_step(model, chip, scheme, best, isl + osl // 2, pi).step_s
    chip_s_decode = scheme.chips * step * osl / best
    chip_s_prefill = scheme.chips * isl / prefill_tokens_per_s if prefill_tokens_per_s else 0.0
    return (isl + osl) * 60 / (chip_s_decode + chip_s_prefill)


def with_overhead(chip: ChipSpec, overhead_s: float, source: str) -> ChipSpec:
    return replace(chip, step_overhead_s=overhead_s, source=source)


def calibrated_chip(micro_rows: list[dict], base: ChipSpec = B300_SPEC) -> ChipSpec:
    """Measured tier: HBM copy bandwidth and log-log interpolated collective curves."""
    bw = next((r["bw"] for r in micro_rows if r["kind"] == "hbm_copy"), base.hbm_bw)
    curves: dict[tuple[str, int], list[tuple[float, float]]] = {}
    for row in micro_rows:
        if row["kind"] in ("all_reduce", "all_to_all"):
            curves.setdefault((row["kind"], row["n"]), []).append((row["bytes"], row["s"]))
    for points in curves.values():
        points.sort()

    def curve(kind: str, n: int, size: float) -> float:
        key = ("all_reduce" if kind != "all_to_all" else "all_to_all", n)
        points = curves.get(key)
        if not points:
            factor = 2 * (n - 1) / n if kind == "all_reduce" else (n - 1) / n
            return base.collective_alpha(kind, n) + size * factor / base.link_bw
        if size <= points[0][0]:
            return points[0][1]
        for (s0, t0), (s1, t1) in zip(points, points[1:]):
            if size <= s1:
                w = (math.log(size) - math.log(s0)) / (math.log(s1) - math.log(s0))
                return math.exp(math.log(t0) + w * (math.log(t1) - math.log(t0)))
        (s0, t0), (s1, t1) = points[-2], points[-1]
        return t1 + (size - s1) * (t1 - t0) / (s1 - s0)

    return replace(base, hbm_bw=bw, collective_curve=curve, source="measured-micro")


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser()
    parser.add_argument("--micro", help="micro.json from tkcc.micro")
    parser.add_argument("--overhead-us", type=float, default=0.0, help="fixed per-step overhead from a measured forward pass")
    parser.add_argument("--context", type=int, default=32768)
    parser.add_argument("--skew", type=float, default=0.0, help="Zipf exponent for expert popularity")
    parser.add_argument("--batches", default="1,8,32")
    args = parser.parse_args()
    model = ModelSpec()
    chip = B300_SPEC
    if args.micro:
        chip = calibrated_chip(json.load(open(args.micro)))
    chip = replace(chip, step_overhead_s=args.overhead_us * 1e-6)
    pi = zipf_routing(model.experts, model.topk, args.skew)
    out = {"chip": chip.source, "overhead_us": args.overhead_us, "skew": args.skew, "rankings": {}}
    for batch in (int(b) for b in args.batches.split(",")):
        out["rankings"][batch] = [
            {"scheme": e.scheme.label, "tps_per_user": round(e.tps_per_user, 1), "aggregate_tps": round(e.aggregate_tps, 1),
             "memory_ms": round(e.memory_s * 1e3, 3), "comm_ms": round(e.comm_s * 1e3, 3)}
            for e in rank_schemes(model, chip, batch, args.context, 4, pi)
        ]
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
