from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

_LINE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(\S+)")
_LE = re.compile(r'le="([^"]+)"')

RUNNING = "sglang:num_running_reqs"
QUEUED = "sglang:num_queue_reqs"
PROMPT_TOKENS = "sglang:prompt_tokens_total"
GENERATION_TOKENS = "sglang:generation_tokens_total"
CACHED_TOKENS = "sglang:cached_tokens_total"
REQUESTS = "sglang:num_requests_total"
# One observation per finished request, (tokens - 1) / (finish - first token): the per-user rate
# loadgen measures, timed on the server so it does not depend on stream chunking. Token-level ITL
# would weight fast, long streams by their token counts. With speculative decoding the first step
# can emit several tokens, so this reads slightly above the client's figure.
REQUEST_TPOT = "sglang:request_time_per_output_token_seconds"
TTFT = "sglang:time_to_first_token_seconds"
QUEUE_TIME = "sglang:queue_time_seconds"
KV_USED = "sglang:kv_used_tokens"
KV_EVICTABLE = "sglang:kv_evictable_tokens"
KV_AVAILABLE = "sglang:kv_available_tokens"
EVICTION_SECONDS = "sglang:eviction_duration_seconds_sum"
EVICTED_TOKENS = "sglang:evicted_tokens_total"
RETRACTED = "sglang:num_retracted_reqs"
STAGE_SECONDS = "sglang:scheduler_stage_seconds_total"
SCHEDULERS = "livetune:schedulers"
_TP_RANK = re.compile(r'tp_rank="([^"]+)"')
_CATEGORY = re.compile(r'category="([^"]+)"')
# Every TP rank reports these; one rank's view is the scheduler's, and summing would count it once per rank.
_RANK0_ONLY = {KV_USED, KV_EVICTABLE, KV_AVAILABLE, EVICTION_SECONDS, EVICTED_TOKENS, RETRACTED, STAGE_SECONDS}


@dataclass(frozen=True)
class Histogram:
    buckets: tuple[tuple[float, float], ...]  # (upper bound, cumulative count), ascending
    count: float

    def minus(self, earlier: "Histogram") -> "Histogram":
        old = dict(earlier.buckets)
        return Histogram(tuple((le, c - old.get(le, 0.0)) for le, c in self.buckets), self.count - earlier.count)

    def quantile(self, q: float) -> float | None:
        if self.count <= 0:
            return None
        rank = q * self.count
        lower_bound, lower_count = 0.0, 0.0
        for upper, cumulative in self.buckets:
            if cumulative >= rank:
                if math.isinf(upper):
                    return lower_bound
                share = (rank - lower_count) / max(cumulative - lower_count, 1e-12)
                return lower_bound + (upper - lower_bound) * share
            lower_bound, lower_count = upper, cumulative
        return lower_bound


@dataclass(frozen=True)
class Scrape:
    t: float
    values: dict[str, float]
    histograms: dict[str, Histogram] = field(default_factory=dict)


def parse(text: str, t: float) -> Scrape:
    # Series are summed across label sets; scheduler gauges are exported by TP rank 0 only.
    values: dict[str, float] = {}
    buckets: dict[str, dict[float, float]] = {}
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _LINE.match(line)
        if not match:
            continue
        name, labels, raw = match.groups()
        try:
            value = float(raw)
        except ValueError:
            continue
        if name in _RANK0_ONLY and labels and (rank := _TP_RANK.search(labels)) and rank.group(1) != "0":
            continue
        if name == STAGE_SECONDS and labels and (category := _CATEGORY.search(labels)):
            name = f"{name}:{category.group(1)}"
            if category.group(1) == "run_batch":
                # One run_batch series per data-parallel scheduler (its TP rank 0).
                values[SCHEDULERS] = values.get(SCHEDULERS, 0.0) + 1
        if name.endswith("_bucket") and labels:
            le = _LE.search(labels)
            if le:
                bound = math.inf if le.group(1) in ("+Inf", "inf") else float(le.group(1))
                series = buckets.setdefault(name[: -len("_bucket")], {})
                series[bound] = series.get(bound, 0.0) + value
            continue
        values[name] = values.get(name, 0.0) + value
    histograms = {
        name: Histogram(tuple(sorted(series.items())), values.get(f"{name}_count", max(series.values(), default=0.0)))
        for name, series in buckets.items()
    }
    return Scrape(t, values, histograms)


@dataclass(frozen=True)
class Window:
    seconds: float
    running: float
    queued: float
    requests: float
    prompt_tokens: float
    generation_tokens: float
    cached_tokens: float
    request_tpot_p50: float | None
    ttft_p90: float | None
    # Utilization: gauges at the end of the window, and seconds or tokens spent within it.
    kv_used: float = 0.0
    kv_evictable: float = 0.0
    kv_available: float = 0.0
    eviction_s: float = 0.0
    evicted_tokens: float = 0.0
    forward_s: float = 0.0  # scheduler time in run_batch
    retracted: float = 0.0
    queue_p90: float | None = None
    schedulers: float = 1.0  # data-parallel schedulers whose seconds are summed above

    @property
    def kv_free_share(self) -> float | None:
        total = self.kv_used + self.kv_evictable + self.kv_available
        return self.kv_available / total if total > 0 else None

    # Shares of each scheduler's wall time: summed seconds from N data-parallel schedulers are divided by N.
    @property
    def eviction_share(self) -> float:
        return self.eviction_s / (self.seconds * self.schedulers) if self.seconds > 0 else 0.0

    @property
    def forward_share(self) -> float:
        return self.forward_s / (self.seconds * self.schedulers) if self.seconds > 0 else 0.0

    @property
    def demand(self) -> float:
        return self.running + self.queued

    @property
    def prompt_per_request(self) -> float | None:
        return self.prompt_tokens / self.requests if self.requests > 0 else None

    @property
    def output_per_request(self) -> float | None:
        return self.generation_tokens / self.requests if self.requests > 0 else None

    @property
    def cache_hit(self) -> float | None:
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens > 0 else None

    @property
    def tps_per_user(self) -> float | None:
        return 1.0 / self.request_tpot_p50 if self.request_tpot_p50 else None

    @property
    def output_tps(self) -> float:
        return self.generation_tokens / self.seconds if self.seconds > 0 else 0.0


def window(earlier: Scrape, later: Scrape) -> Window:
    def delta(name: str) -> float:
        return max(later.values.get(name, 0.0) - earlier.values.get(name, 0.0), 0.0)

    def histogram(name: str) -> Histogram | None:
        if name not in later.histograms:
            return None
        if name not in earlier.histograms:
            return later.histograms[name]
        return later.histograms[name].minus(earlier.histograms[name])

    tpot, ttft, queue = histogram(REQUEST_TPOT), histogram(TTFT), histogram(QUEUE_TIME)
    return Window(
        seconds=later.t - earlier.t,
        running=later.values.get(RUNNING, 0.0),
        queued=later.values.get(QUEUED, 0.0),
        requests=delta(REQUESTS),
        prompt_tokens=delta(PROMPT_TOKENS),
        generation_tokens=delta(GENERATION_TOKENS),
        cached_tokens=delta(CACHED_TOKENS),
        request_tpot_p50=tpot.quantile(0.5) if tpot else None,
        ttft_p90=ttft.quantile(0.9) if ttft else None,
        kv_used=later.values.get(KV_USED, 0.0),
        kv_evictable=later.values.get(KV_EVICTABLE, 0.0),
        kv_available=later.values.get(KV_AVAILABLE, 0.0),
        eviction_s=delta(EVICTION_SECONDS),
        evicted_tokens=delta(EVICTED_TOKENS),
        forward_s=delta(f"{STAGE_SECONDS}:run_batch"),
        retracted=later.values.get(RETRACTED, 0.0),
        queue_p90=queue.quantile(0.9) if queue else None,
        schedulers=max(later.values.get(SCHEDULERS, 1.0), 1.0),
    )
