"""Turn what a server is doing into experiments worth running.

The advisor reads three kinds of evidence: utilization over metric windows, the traffic mix from
per-request records, and per-batch counters. Each rule names a lever, the values to try and the
measurement that motivated it. It proposes; it does not apply. Live levers go to ``tune``, which
measures them against the startup settings. Restart levers need a canary with new launch flags.
Code levers (forward variants, kernels) go to the variant loop with the hot shapes as targets.
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from livetune.knobs import KNOBS, SCHEDULE_POLICIES
from livetune.metrics import Window


@dataclass(frozen=True)
class Proposal:
    tier: str  # "live", "restart" or "code"
    lever: str
    values: tuple[Any, ...]
    why: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Evidence:
    windows: Sequence[Window]
    traffic: Mapping[str, Any]  # trace.summarize
    batches: Mapping[str, float]  # trace.batch_deltas over the same span
    settings: Mapping[str, Any]  # live settings
    startup: Mapping[str, Any]
    kv_capacity: int = 0
    page_size: int = 1

    def mean(self, attribute: str) -> float:
        values = [getattr(w, attribute) for w in self.windows]
        values = [v for v in values if v is not None]
        return statistics.fmean(values) if values else 0.0

    def share(self, key: str, of: str) -> float | None:
        total = self.batches.get(of, 0.0)
        return self.batches.get(key, 0.0) / total if total else None


def _prefix_order(e: Evidence) -> list[Proposal]:
    families = e.traffic.get("families", {})
    sharing = families.get("requests_sharing", 0.0)
    queue = e.traffic.get("queue_s_p90") or 0.0
    policy = e.settings.get("schedule_policy")
    if sharing < 0.3 or queue < 0.5 or policy is None or SCHEDULE_POLICIES[policy] in ("lpm", "dfs-weight"):
        return []
    return [Proposal("live", "schedule_policy", (SCHEDULE_POLICIES.index("lpm"), SCHEDULE_POLICIES.index("dfs-weight")),
                     "requests queue and most share a prefix; a cache-aware order admits a family together and raises hits",
                     {"requests_sharing": sharing, "queue_s_p90": queue, "cache_hit": e.traffic.get("cache_hit")})]


def _retraction(e: Evidence) -> list[Proposal]:
    retracted = e.traffic.get("retracted_share", 0.0)
    current = e.settings.get("schedule_conservativeness", 1.0)
    if retracted < 0.01:
        return []
    return [Proposal("live", "schedule_conservativeness", tuple(round(current * f, 2) for f in (1.3, 1.6) if current * f <= KNOBS["schedule_conservativeness"].maximum),
                     "requests are retracted, which recomputes their KV; reserving more decode headroom admits fewer",
                     {"retracted_share": retracted})]


def _admission(e: Evidence) -> list[Proposal]:
    queue = e.traffic.get("queue_s_p90") or 0.0
    free = e.mean("kv_free_share")
    busy = e.mean("forward_share")
    out = []
    if queue > 1.0 and busy < 0.85:
        cap, startup_cap = e.settings.get("max_running_requests"), e.startup.get("max_running_requests")
        if cap is not None and startup_cap is not None and cap < startup_cap:
            out.append(Proposal("live", "max_running_requests", tuple(sorted({min(startup_cap, cap * 2), startup_cap})),
                                "requests wait while the GPU has slack; the running cap holds them back",
                                {"queue_s_p90": queue, "forward_share": round(busy, 3)}))
        prefill, startup_prefill = e.settings.get("max_prefill_tokens"), e.startup.get("max_prefill_tokens")
        if prefill is not None and startup_prefill is not None and prefill < startup_prefill and free > 0.2:
            out.append(Proposal("live", "max_prefill_tokens", (startup_prefill,),
                                "requests wait for prefill while KV has room; larger prefill batches admit them sooner",
                                {"queue_s_p90": queue, "kv_free_share": round(free, 3)}))
    return out


def _long_prefill(e: Evidence) -> list[Proposal]:
    bands = e.traffic.get("bands", {})
    long_share = sum(b["share"] for name, b in bands.items() if name in ("16-64k", ">=64k"))
    chunk = e.settings.get("chunked_prefill_size")
    if long_share < 0.2 or chunk is None or (e.traffic.get("cache_hit") or 0.0) > 0.7:
        return []
    page = max(e.page_size, 1)
    values = tuple(v for v in (chunk // 2, chunk // 4) if v >= page and v % page == 0)
    return [Proposal("live", "chunked_prefill_size", values,
                     "long uncached prompts prefill in large chunks that stall every running decode; smaller chunks trade TTFT for steadier decode",
                     {"long_prompt_share": round(long_share, 3), "cache_hit": e.traffic.get("cache_hit")})] if values else []


def _streaming(e: Evidence) -> list[Proposal]:
    decode = e.batches.get("decode_batches", 0.0)
    rps = e.traffic.get("arrival_rps") or 0.0
    interval = e.settings.get("stream_interval", 1)
    if interval > 1 or rps < 5 or not decode:
        return []
    return [Proposal("live", "stream_interval", (2, 4),
                     "many concurrent streams each get a detokenize and IPC message per token; batching tokens per chunk cuts that work",
                     {"arrival_rps": rps})]


def _graphs(e: Evidence) -> list[Proposal]:
    share = e.share("decode_graph_batches", "decode_batches")
    if share is None or share > 0.9:
        return []
    mean_bs = e.batches.get("decode_requests", 0.0) / max(e.batches.get("decode_batches", 1.0), 1.0)
    return [Proposal("restart", "cuda_graph_max_bs_decode", (int(mean_bs * 1.5),),
                     "decode batches run without a CUDA graph, so each step pays kernel launch overhead",
                     {"graph_share": round(share, 3), "mean_decode_batch": round(mean_bs, 1)})]


def _spec(e: Evidence) -> list[Proposal]:
    accept = e.traffic.get("spec_accept_p50")
    if not accept or accept >= 1.6:
        return []
    return [Proposal("restart", "speculative_num_draft_tokens", ("lower", "disable at high load"),
                     "drafts are rarely accepted, so verification work is mostly wasted",
                     {"spec_accept_p50": accept})]


def _hot_shapes(e: Evidence) -> list[Proposal]:
    # Where forward time goes is where a kernel or forward variant pays off.
    decode_s, prefill_s = e.batches.get("decode_seconds", 0.0), e.batches.get("extend_seconds", 0.0)
    total = decode_s + prefill_s
    if total <= 0 or e.mean("forward_share") < 0.5:
        return []
    mean_bs = e.batches.get("decode_requests", 0.0) / max(e.batches.get("decode_batches", 1.0), 1.0)
    mean_extend = e.batches.get("extend_tokens", 0.0) / max(e.batches.get("extend_batches", 1.0), 1.0)
    target = "decode" if decode_s >= prefill_s else "prefill"
    return [Proposal("code", f"{target}_forward_variant", (),
                     f"{target} takes most forward time; a variant tuned for these shapes is the next lever after scheduling",
                     {"decode_time_share": round(decode_s / total, 3), "mean_decode_batch": round(mean_bs, 1),
                      "mean_extend_tokens": round(mean_extend, 1), "prompt_tokens_p50": e.traffic.get("prompt_tokens", {}).get("p50"),
                      "cache_hit": e.traffic.get("cache_hit")})]


RULES = (_prefix_order, _retraction, _admission, _long_prefill, _streaming, _graphs, _spec, _hot_shapes)


def advise(evidence: Evidence) -> list[Proposal]:
    proposals = [p for rule in RULES for p in rule(evidence)]
    order = {"live": 0, "restart": 1, "code": 2}
    return sorted(proposals, key=lambda p: order[p.tier])


def as_grid(proposals: Sequence[Proposal]) -> dict[str, list[Any]]:
    """The live proposals as a ``tune`` grid: each lever with the values to try."""
    grid: dict[str, list[Any]] = {}
    for p in proposals:
        if p.tier == "live" and p.lever in KNOBS:
            grid.setdefault(p.lever, [])
            grid[p.lever].extend(v for v in p.values if v not in grid[p.lever])
    return grid


def to_json(proposals: Sequence[Proposal]) -> list[dict[str, Any]]:
    return [asdict(p) for p in proposals]
