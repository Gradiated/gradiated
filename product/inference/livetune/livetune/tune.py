from __future__ import annotations

import json
import math
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

    def phase(self, seconds: float) -> Phase:
        return Phase(self.users, self.prompt_tokens, self.output_tokens, seconds, self.shared_prefix, self.name)


def score(summary: Mapping[str, Any], slo: Slo) -> tuple[int, float]:
    # (feasible, value): any SLO-feasible result outranks every infeasible one.
    if summary.get("errors") or not summary.get("completed"):
        return (0, -math.inf)
    met = slo.met(summary.get("tps_per_user_p50"), summary.get("ttft_p90"))
    if met:
        return (1, float(summary["output_tps"]))
    tps = summary.get("tps_per_user_p50") or 0.0
    ttft = summary.get("ttft_p90") or math.inf
    closeness = min(tps / slo.min_tps_per_user, slo.max_ttft_p90_s / ttft)
    return (0, closeness)


Measure = Callable[[Profile, dict[str, Any]], dict[str, Any]]


def binding(knob: str, value: Any, profile: Profile) -> bool:
    # A running cap at or above the closed-loop user count never limits anything.
    return knob != "max_running_requests" or value < profile.users


def merged(summaries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    def median(key: str) -> float | None:
        values = sorted(v for v in (s.get(key) for s in summaries) if v is not None)
        return values[len(values) // 2] if values else None

    return {
        "completed": min(s.get("completed", 0) for s in summaries),
        "errors": sum(s.get("errors", 0) for s in summaries),
        "output_tps": median("output_tps"),
        "tps_per_user_p50": median("tps_per_user_p50"),
        "ttft_p90": median("ttft_p90"),
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


def _midpoints(levels: Sequence[float]) -> list[float]:
    ordered = sorted(set(levels))
    return [(a + b) / 2 for a, b in zip(ordered, ordered[1:])] + [math.inf]


def best_from_trials(trials: Sequence[Mapping[str, Any]], slo: Slo, start: Mapping[str, Any], min_gain: float = 0.02) -> list[dict[str, Any]]:
    # Repeats merge by median; a non-startup setting needs two measurements to be chosen.
    by_profile: dict[str, list[Mapping[str, Any]]] = {}
    for trial in trials:
        by_profile.setdefault(trial["profile"], []).append(trial)
    results = []
    for name, rows in by_profile.items():
        phase = rows[0]["summary"]["phase"]
        profile = Profile(name, phase["users"], phase["prompt_tokens"], phase["output_tokens"], phase.get("shared_prefix", 0.0))
        groups: dict[str, list[Mapping[str, Any]]] = {}
        for row in rows:
            settings = dict(row["settings"])
            if all(binding(k, v, profile) or v == start.get(k) for k, v in settings.items()):
                groups.setdefault(json.dumps(settings, sort_keys=True), []).append(row["summary"])
        startup_key = json.dumps(dict(start), sort_keys=True)
        best_key = startup_key
        best = merged(groups[startup_key])
        for key, summaries in groups.items():
            if key != startup_key and len(summaries) >= 2 and _wins(merged(summaries), best, slo, min_gain):
                best_key, best = key, merged(summaries)
        results.append({"profile": asdict(profile), "settings": json.loads(best_key), "summary": best})
    return results


def build_policy(results: Sequence[Mapping[str, Any]], slo: Slo, provenance: Mapping[str, Any]) -> Policy:
    # One rule per profile; box edges sit halfway between neighbouring profiles.
    prompts = sorted({r["profile"]["prompt_tokens"] for r in results})
    prompt_edges = dict(zip(prompts, _midpoints(prompts)))
    rules: list[Rule] = []
    for prompt in prompts:
        rows = sorted((r for r in results if r["profile"]["prompt_tokens"] == prompt), key=lambda r: r["profile"]["users"])
        demand_edges = _midpoints([r["profile"]["users"] for r in rows])
        for row, edge in zip(rows, demand_edges):
            summary = row["summary"]
            rules.append(
                Rule(
                    name=row["profile"]["name"],
                    max_demand=edge,
                    max_prompt_tokens=prompt_edges[prompt],
                    settings=dict(row["settings"]),
                    evidence={k: summary.get(k) for k in ("output_tps", "tps_per_user_p50", "ttft_p90", "errors")},
                )
            )
    rules.sort(key=lambda rule: (rule.max_prompt_tokens, rule.max_demand))
    last = rules[-1]
    if not (math.isinf(last.max_demand) and math.isinf(last.max_prompt_tokens)):
        rules.append(Rule("fallback", math.inf, math.inf, dict(last.settings)))
    return Policy(slo, tuple(rules), dict(provenance))
