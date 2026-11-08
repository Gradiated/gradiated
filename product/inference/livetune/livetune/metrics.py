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
ITL = "sglang:inter_token_latency_seconds"
TTFT = "sglang:time_to_first_token_seconds"


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
    itl_p50: float | None
    itl_p90: float | None
    ttft_p90: float | None

    @property
    def demand(self) -> float:
        return self.running + self.queued

    @property
    def prompt_per_request(self) -> float | None:
        return self.prompt_tokens / self.requests if self.requests > 0 else None

    @property
    def cache_hit(self) -> float | None:
        return self.cached_tokens / self.prompt_tokens if self.prompt_tokens > 0 else None

    @property
    def tps_per_user(self) -> float | None:
        return 1.0 / self.itl_p50 if self.itl_p50 else None

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

    itl, ttft = histogram(ITL), histogram(TTFT)
    return Window(
        seconds=later.t - earlier.t,
        running=later.values.get(RUNNING, 0.0),
        queued=later.values.get(QUEUED, 0.0),
        requests=delta(REQUESTS),
        prompt_tokens=delta(PROMPT_TOKENS),
        generation_tokens=delta(GENERATION_TOKENS),
        cached_tokens=delta(CACHED_TOKENS),
        itl_p50=itl.quantile(0.5) if itl else None,
        itl_p90=itl.quantile(0.9) if itl else None,
        ttft_p90=ttft.quantile(0.9) if ttft else None,
    )
