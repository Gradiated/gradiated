from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Shape:
    demand: float
    prompt_tokens: float
    # Secondary dimensions; None until measured, and then they do not constrain selection.
    cache_hit: float | None = None
    output_tokens: float | None = None


@dataclass(frozen=True)
class Slo:
    min_tps_per_user: float
    max_ttft_p90_s: float

    def met(self, tps_per_user: float | None, ttft_p90: float | None) -> bool | None:
        # None: the window carried too little traffic to judge.
        if tps_per_user is None and ttft_p90 is None:
            return None
        if tps_per_user is not None and tps_per_user < self.min_tps_per_user:
            return False
        if ttft_p90 is not None and ttft_p90 > self.max_ttft_p90_s:
            return False
        return True


@dataclass(frozen=True)
class Rule:
    name: str
    max_demand: float
    max_prompt_tokens: float
    settings: dict[str, Any]
    evidence: dict[str, Any] = field(default_factory=dict)
    # Inclusive [low, high] ranges of secondary shape dimensions the rule's measurement covers.
    workload: dict[str, tuple[float, float]] = field(default_factory=dict)

    def contains(self, shape: Shape) -> bool:
        return shape.demand <= self.max_demand and shape.prompt_tokens <= self.max_prompt_tokens

    def fits_workload(self, shape: Shape) -> bool:
        for key, (low, high) in self.workload.items():
            value = getattr(shape, key)
            if value is not None and not low <= value <= high:
                return False
        return True


@dataclass(frozen=True)
class Policy:
    slo: Slo
    rules: tuple[Rule, ...]
    provenance: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.rules:
            raise ValueError("a policy needs at least one rule")
        last = self.rules[-1]
        if not (math.isinf(last.max_demand) and math.isinf(last.max_prompt_tokens)) or last.workload:
            raise ValueError("the last rule must be a catch-all (infinite bounds)")
        names = [rule.name for rule in self.rules]
        if len(set(names)) != len(names):
            raise ValueError("rule names must be unique")

    def select(self, shape: Shape) -> Rule:
        # The first box containing the shape decides. Boxes carry only upper bounds, so a rule whose
        # workload does not fit hands over to the catch-all, never to a later box measured elsewhere.
        for rule in self.rules:
            if rule.contains(shape):
                return rule if rule.fits_workload(shape) else self.rules[-1]
        return self.rules[-1]

    def rule(self, name: str) -> Rule:
        return next(rule for rule in self.rules if rule.name == name)

    def to_json(self) -> str:
        def bound(value: float) -> float | str:
            return "inf" if math.isinf(value) else value

        rules = [{**asdict(rule), "max_demand": bound(rule.max_demand), "max_prompt_tokens": bound(rule.max_prompt_tokens)} for rule in self.rules]
        return json.dumps({"slo": asdict(self.slo), "rules": rules, "provenance": self.provenance}, indent=1)

    @classmethod
    def from_json(cls, text: str) -> "Policy":
        data = json.loads(text)
        rules = tuple(
            Rule(
                name=r["name"],
                max_demand=float(r["max_demand"]),
                max_prompt_tokens=float(r["max_prompt_tokens"]),
                settings=dict(r["settings"]),
                evidence=dict(r.get("evidence", {})),
                workload={key: (float(low), float(high)) for key, (low, high) in r.get("workload", {}).items()},
            )
            for r in data["rules"]
        )
        return cls(Slo(**data["slo"]), rules, dict(data.get("provenance", {})))

    @classmethod
    def load(cls, path: str | Path) -> "Policy":
        return cls.from_json(Path(path).read_text())
