"""Staged rollout: one production replica runs a candidate policy before the fleet does.

Replay on a canary decides which settings win. The stage checks the winner on real traffic,
where prompt content, long-lived cache state and fleet routing differ from any replay. The
staged replica and its peers serve the same traffic at the same time, so they are compared
window for window. The candidate is promoted only if the staged replica is no worse.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Iterable, Sequence

from livetune.metrics import Window
from livetune.policy import Slo


@dataclass(frozen=True)
class Side:
    windows: int
    judged: int  # windows that measured both halves of the SLO
    slo_met: float | None  # share of judged windows meeting the SLO
    tps_per_user: float | None  # median over windows
    ttft_p90: float | None  # median over windows
    demand: float  # mean running + queued
    prompt_tokens: float | None = None  # mean per request, over windows that saw requests
    output_tokens: float | None = None
    cache_hit: float | None = None

    @classmethod
    def of(cls, windows: Sequence[Window], slo: Slo) -> "Side":
        verdicts = [slo.met(w.tps_per_user, w.ttft_p90) for w in windows if w.tps_per_user is not None and w.ttft_p90 is not None]
        rates = [w.tps_per_user for w in windows if w.tps_per_user is not None]
        ttfts = [w.ttft_p90 for w in windows if w.ttft_p90 is not None]
        return cls(
            windows=len(windows),
            judged=len(verdicts),
            slo_met=sum(map(bool, verdicts)) / len(verdicts) if verdicts else None,
            tps_per_user=statistics.median(rates) if rates else None,
            ttft_p90=statistics.median(ttfts) if ttfts else None,
            demand=statistics.fmean(w.demand for w in windows) if windows else 0.0,
            prompt_tokens=_mean(w.prompt_per_request for w in windows),
            output_tokens=_mean(w.output_per_request for w in windows),
            cache_hit=_mean(w.cache_hit for w in windows),
        )


def _mean(values: Iterable[float | None]) -> float | None:
    present = [v for v in values if v is not None]
    return statistics.fmean(present) if present else None


SHAPE_RATIO = 1.3  # prompt and output lengths may differ by up to this factor
CACHE_HIT_GAP = 0.15  # and the cache-hit rate by up to this much


def _shape_differs(s: Side, p: Side) -> str | None:
    for name in ("prompt_tokens", "output_tokens"):
        a, b = getattr(s, name), getattr(p, name)
        if a and b and not 1 / SHAPE_RATIO <= a / b <= SHAPE_RATIO:
            return f"{name} per request {a:.0f} against {b:.0f}"
    if s.cache_hit is not None and p.cache_hit is not None and abs(s.cache_hit - p.cache_hit) > CACHE_HIT_GAP:
        return f"cache hit {s.cache_hit:.2f} against {p.cache_hit:.2f}"
    return None


@dataclass(frozen=True)
class Verdict:
    decision: str  # "promote", "revert" or "inconclusive"
    reason: str
    stage: Side
    peers: Side


def judge(stage: Sequence[Window], peers: Sequence[Window], slo: Slo, tolerance: float = 0.05, min_windows: int = 12) -> Verdict:
    """Promote when the staged replica meets the SLO as often as its peers and is not slower."""
    s, p = Side.of(stage, slo), Side.of(peers, slo)

    def verdict(decision: str, reason: str) -> Verdict:
        return Verdict(decision, reason, s, p)

    # Only windows that measured both per-user speed and TTFT count as evidence, on both sides.
    if s.judged < min_windows or p.judged < min_windows:
        return verdict("inconclusive", f"too few windows measured the SLO: {s.judged} staged, {p.judged} peers")
    # A router can starve or flood one replica; outcomes under different load are not comparable.
    if p.demand > 0 and not 0.7 <= s.demand / p.demand <= 1.3:
        return verdict("inconclusive", f"staged demand {s.demand:.1f} differs from peers {p.demand:.1f}")
    # The same load of a different workload costs differently; such a comparison judges the traffic, not the policy.
    if (shape := _shape_differs(s, p)) is not None:
        return verdict("inconclusive", f"the workloads differ: {shape}")
    if s.slo_met < p.slo_met - tolerance:
        return verdict("revert", f"met the SLO in {s.slo_met:.0%} of windows against {p.slo_met:.0%} for peers")
    if s.tps_per_user is not None and p.tps_per_user is not None and s.tps_per_user < p.tps_per_user * (1 - tolerance):
        return verdict("revert", f"per-user speed {s.tps_per_user:.1f} against {p.tps_per_user:.1f} for peers")
    if s.ttft_p90 is not None and p.ttft_p90 is not None and s.ttft_p90 > p.ttft_p90 * (1 + tolerance) and s.ttft_p90 > slo.max_ttft_p90_s:
        return verdict("revert", f"TTFT p90 {s.ttft_p90:.2f}s against {p.ttft_p90:.2f}s for peers, beyond the SLO")
    return verdict("promote", "no worse than its peers on the same traffic")
