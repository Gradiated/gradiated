from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping, Sequence

from livetune.loadgen import Phase
from livetune.policy import Policy, Rule, Slo


@dataclass(frozen=True)
class Profile:
    name: str
    users: int
    prompt_tokens: int
    output_tokens: int
    shared_prefix: float = 0.0
    # Open-loop load has no fixed user count, so a running cap may always bind; users is then the
    # demand the traffic produced, which places the policy rule where that traffic lands.
    open_loop: bool = False

    def phase(self, seconds: float) -> Phase:
        return Phase(self.users, self.prompt_tokens, self.output_tokens, seconds, self.shared_prefix, self.name)


def score(summary: Mapping[str, Any], slo: Slo) -> tuple[int, float]:
    # (feasible, value): any SLO-feasible result outranks every infeasible one.
    if summary.get("errors") or not summary.get("completed"):
        return (0, -math.inf)
    # Tuning judges both halves of the SLO: a result missing either is inconclusive.
    if summary.get("tps_per_user_p50") is None or summary.get("ttft_p90") is None:
        return (0, -math.inf)
    met = slo.met(summary.get("tps_per_user_p50"), summary.get("ttft_p90"))
    if met:
        return (1, float(summary["output_tps"]))
    tps = summary.get("tps_per_user_p50") or 0.0
    ttft = summary.get("ttft_p90") or math.inf
    closeness = min(tps / slo.min_tps_per_user, slo.max_ttft_p90_s / ttft)
    return (0, closeness)


Measure = Callable[[Profile, dict[str, Any]], dict[str, Any]]


def trace_profile(arrivals: Sequence[Any]) -> dict[str, Any]:
    """One profile standing for a recorded trace, placed at the demand the trace produced.

    Lengths are per-request means, the statistic the controller observes from metric windows, so the
    rule tuned here covers the shape the controller will see; a median sits far from it when a few
    long requests skew the mix.
    """
    from livetune.trace import concurrency, observed_cache_hit

    if not arrivals:
        raise ValueError("the trace has no requests")
    # Requests already running when the window began load the server but are not its workload.
    measured = [a for a in arrivals if not getattr(a, "warmup", False)] or list(arrivals)
    return {
        "name": "trace",
        "users": concurrency(arrivals),
        "open_loop": True,
        "prompt_tokens": round(statistics.fmean(a.prompt_tokens for a in measured)),
        "output_tokens": round(statistics.fmean(a.output_tokens for a in measured)),
        # The cache hit production recorded, which is what the controller will observe, not the
        # sharing replay could reach from a cold cache.
        "shared_prefix": observed_cache_hit(arrivals),
    }


def binding(knob: str, value: Any, profile: Profile) -> bool:
    # A running cap at or above the closed-loop user count never limits anything.
    return knob != "max_running_requests" or profile.open_loop or value < profile.users


def merged(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def median(key: str, higher_is_better: bool = True) -> float | None:
        # With an even count, take the worse of the two middle values, so one lucky run of two cannot carry a setting.
        values = [s.get(key) for s in summaries]
        # A repetition that did not measure a metric makes the merged metric inconclusive too.
        if not values or any(v is None for v in values):
            return None
        values.sort(reverse=not higher_is_better)
        return values[(len(values) - 1) // 2]

    return {
        "completed": min(s.get("completed", 0) for s in summaries),
        # A median like the rest: one transient failure in one repetition must not sink a setting for good.
        "errors": median("errors", higher_is_better=False),
        "output_tps": median("output_tps"),
        "tps_per_user_p50": median("tps_per_user_p50"),
        "ttft_p90": median("ttft_p90", higher_is_better=False),
        "measurements": len(summaries),
    }


def _wins(candidate: Mapping[str, Any], incumbent: Mapping[str, Any], slo: Slo, min_gain: float) -> bool:
    new, old = score(candidate, slo), score(incumbent, slo)
    return new[0] > old[0] or (new[0] == old[0] and new[1] > old[1] * (1 + min_gain if old[1] > 0 else 1))


def tune_profile(
    profile: Profile,
    start: dict[str, Any],
    grid: Mapping[str, Sequence[Any]],
    slo: Slo,
    measure: Measure,
    min_gain: float = 0.02,
    confirm_rounds: int = 2,
) -> dict[str, Any]:
    best_settings = dict(start)
    best = measure(profile, best_settings)
    trials = [{"settings": dict(best_settings), "summary": best}]
    for knob, values in grid.items():
        for value in values:
            if value == best_settings.get(knob) or not binding(knob, value, profile):
                continue
            candidate = {**best_settings, knob: value}
            summary = measure(profile, candidate)
            trials.append({"settings": candidate, "summary": summary})
            if _wins(summary, best, slo, min_gain):
                best_settings, best = candidate, summary

    if best_settings != start:
        # One short window can flatter a setting; repeat both, interleaved, and compare medians.
        runs = {"start": [trials[0]["summary"]], "best": [best]}
        for round_ in range(confirm_rounds):
            order = [("start", start), ("best", best_settings)]
            for label, settings in order if round_ % 2 else reversed(order):
                summary = measure(profile, settings)
                trials.append({"settings": dict(settings), "summary": summary, "confirm": True})
                runs[label].append(summary)
        if not _wins(merged(runs["best"]), merged(runs["start"]), slo, min_gain):
            best_settings = dict(start)
        best = merged(runs["best" if best_settings != start else "start"])
    return {"profile": asdict(profile), "settings": best_settings, "summary": best, "trials": trials}


EVIDENCE_REACH = 1.25


def _cells(levels: Sequence[float]) -> list[tuple[float | None, float]]:
    """(measured level, upper edge) for each cell in order; a level of None is a gap no measurement reaches.

    A measurement covers at most EVIDENCE_REACH above and below itself, meeting its neighbour halfway
    where their reaches overlap. What lies beyond every reach gets the startup settings.
    """
    ordered = sorted(set(levels))
    cells: list[tuple[float | None, float]] = [(None, ordered[0] / EVIDENCE_REACH)]
    for a, b in zip(ordered, ordered[1:]):
        if a * EVIDENCE_REACH >= b / EVIDENCE_REACH:
            cells.append((a, min(max((a + b) / 2, b / EVIDENCE_REACH), a * EVIDENCE_REACH)))
        else:
            cells += [(a, a * EVIDENCE_REACH), (None, b / EVIDENCE_REACH)]
    return cells + [(ordered[-1], ordered[-1] * EVIDENCE_REACH)]


def _profile_of(name: str, phase: Mapping[str, Any], open_loop: bool = False) -> Profile:
    return Profile(name, phase["users"], phase["prompt_tokens"], phase["output_tokens"], phase.get("shared_prefix", 0.0), open_loop)


def best_from_trials(trials: Sequence[Mapping[str, Any]], slo: Slo, start: Mapping[str, Any], min_gain: float = 0.02) -> list[dict[str, Any]]:
    # Repeats merge by median; a non-startup setting needs two measurements to be chosen.
    by_profile: dict[str, list[Mapping[str, Any]]] = {}
    for trial in trials:
        by_profile.setdefault(trial["profile"], []).append(trial)
    results = []
    for name, rows in by_profile.items():
        profiles = {_profile_of(name, row["summary"]["phase"], row.get("open_loop", False)) for row in rows}
        if len(profiles) != 1:
            raise ValueError(f"profile {name!r} was measured with different workloads; give each workload its own name")
        (profile,) = profiles
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            settings = dict(row["settings"])
            if all(binding(k, v, profile) or v == start.get(k) for k, v in settings.items()):
                groups.setdefault(json.dumps(settings, sort_keys=True), []).append(row["summary"])
        recorded = rows[0]["settings"].keys()
        startup_key = json.dumps({k: v for k, v in start.items() if k in recorded}, sort_keys=True)
        best_key = startup_key
        best = merged(groups[startup_key])
        for key, summaries in groups.items():
            if key != startup_key and len(summaries) >= 2 and _wins(merged(summaries), best, slo, min_gain):
                best_key, best = key, merged(summaries)
        results.append({"profile": asdict(profile), "settings": json.loads(best_key), "summary": best})
    return results


# Coarse guards on the dimensions rules do not select on: live cache hit and output length are noisy
# over a few windows, so a rule keeps its settings near its profile and yields well away from it.
CACHE_HIT_MARGIN = 0.2
OUTPUT_REACH = 2.0


def _workload(profile: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    workload: dict[str, tuple[float, float]] = {}
    if "shared_prefix" in profile:
        # A shared prefix of fraction f is served from the prefix cache for all but the first request.
        f = profile["shared_prefix"]
        workload["cache_hit"] = (max(f - CACHE_HIT_MARGIN, 0.0), min(f + CACHE_HIT_MARGIN, 1.0))
    if "output_tokens" in profile:
        workload["output_tokens"] = (profile["output_tokens"] / OUTPUT_REACH, profile["output_tokens"] * OUTPUT_REACH)
    return workload


def check_distinguishable(profiles: Sequence[Mapping[str, Any]]) -> None:
    # Rules select on prompt length and demand only; other workload differences cannot be told apart.
    shapes = [(p["prompt_tokens"], p["users"]) for p in profiles]
    duplicates = sorted({shape for shape in shapes if shapes.count(shape) > 1})
    if duplicates:
        raise ValueError(f"profiles share a (prompt_tokens, users) shape the policy cannot distinguish: {duplicates}")


def build_policy(results: Sequence[Mapping[str, Any]], slo: Slo, provenance: Mapping[str, Any], start: Mapping[str, Any],
                 variants: Mapping[str, dict[str, str]] | None = None) -> Policy:
    """One rule per profile, reaching only near its measurement; everywhere else the startup settings apply."""
    check_distinguishable([r["profile"] for r in results])
    rules: list[Rule] = []
    for prompt, prompt_edge in _cells([r["profile"]["prompt_tokens"] for r in results]):
        if prompt is None:
            rules.append(Rule(f"startup-prompt-{prompt_edge:g}", math.inf, prompt_edge, dict(start)))
            continue
        rows = {r["profile"]["users"]: r for r in results if r["profile"]["prompt_tokens"] == prompt}
        for users, edge in _cells(list(rows)):
            if users is None:
                rules.append(Rule(f"startup-prompt-{prompt:g}-users-{edge:g}", edge, prompt_edge, dict(start)))
                continue
            row = rows[users]
            evidence = {k: row["summary"].get(k) for k in ("output_tps", "tps_per_user_p50", "ttft_p90", "errors")}
            rules.append(Rule(row["profile"]["name"], edge, prompt_edge, dict(row["settings"]), evidence, _workload(row["profile"])))
        rules.append(Rule(f"beyond-{rows[max(rows)]['profile']['name']}", math.inf, prompt_edge, dict(start)))
    rules.sort(key=lambda rule: (rule.max_prompt_tokens, rule.max_demand))
    rules.append(Rule("unmeasured", math.inf, math.inf, dict(start)))
    return Policy(slo, tuple(rules), dict(provenance), dict(variants or {}))
