from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from livetune.knobs import VARIANT_KEY
from livetune.metrics import Window
from livetune.variants import STOCK
from livetune.policy import Policy, Rule, Shape

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Action:
    rule: str
    settings: dict[str, Any]
    reason: str


@dataclass
class _Probation:
    rule: str
    previous: str
    started: float
    slo_before: bool
    verdicts: list[bool] = field(default_factory=list)


@dataclass
class Controller:
    policy: Policy
    dwell: int = 2
    cooldown_s: float = 20.0
    probation_s: float = 45.0
    penalty_s: float = 600.0
    smoothing: float = 0.5
    min_requests: float = 2.0
    variant_dwell: int = 6
    variant_cooldown_s: float = 600.0
    margin: float = 0.15
    current: str | None = None
    applied: dict[str, Any] = field(default_factory=dict)
    shape: Shape | None = None
    _candidate: str | None = None
    _candidate_windows: int = 0
    _last_change: float = float("-inf")
    _last_variant_change: float = float("-inf")
    _probation: _Probation | None = None
    _recent_slo: list[bool] = field(default_factory=list)
    _penalties: dict[str, float] = field(default_factory=dict)

    def forget(self) -> None:
        self.current, self.applied, self._probation = None, {}, None

    def observe(self, window: Window) -> Shape:
        prompt = window.prompt_per_request
        if self.shape is None:
            self.shape = Shape(window.demand, prompt if prompt is not None else 0.0)
        else:
            a = self.smoothing
            self.shape = Shape(
                a * window.demand + (1 - a) * self.shape.demand,
                a * prompt + (1 - a) * self.shape.prompt_tokens if prompt is not None else self.shape.prompt_tokens,
            )
        return self.shape

    def _slo(self, window: Window) -> bool | None:
        if window.requests < self.min_requests and window.generation_tokens <= 0:
            return None
        return self.policy.slo.met(window.tps_per_user, window.ttft_p90)

    def step(self, window: Window, now: float) -> Action | None:
        shape = self.observe(window)
        verdict = self._slo(window)
        if self.current is None:
            return self._change(self.policy.select(shape), now, "initial", verdict)

        rollback = self._judge_probation(verdict, now)
        if rollback is not None:
            return rollback
        if verdict is not None:
            self._recent_slo = (self._recent_slo + [verdict])[-6:]

        target = self._robust_target(shape)
        penalised = target is not None and self._penalties.get(target.name, float("-inf")) > now
        if target is None or target.name == self.current or penalised:
            self._candidate, self._candidate_windows = None, 0
            return None
        if target.name == self._candidate:
            self._candidate_windows += 1
        else:
            self._candidate, self._candidate_windows = target.name, 1
        if self._candidate_windows < self.dwell or now - self._last_change < self.cooldown_s:
            return None
        # Switching variants recaptures CUDA graphs and stalls decoding for seconds.
        if self._switches_variant(target) and (
            self._candidate_windows < self.variant_dwell or now - self._last_variant_change < self.variant_cooldown_s
        ):
            return None
        return self._change(target, now, f"shape demand={shape.demand:.1f} prompt={shape.prompt_tokens:.0f}", verdict)

    def _robust_target(self, shape: Shape) -> Rule | None:
        # None near a box edge: a shape within ±margin of here would pick another rule.
        target = self.policy.select(shape)
        for factor in (1 + self.margin, 1 / (1 + self.margin)):
            if self.policy.select(Shape(shape.demand * factor, shape.prompt_tokens * factor)).name != target.name:
                return None
        return target

    def _judge_probation(self, verdict: bool | None, now: float) -> Action | None:
        probation = self._probation
        if probation is None:
            return None
        if verdict is not None:
            probation.verdicts.append(verdict)
        if now - probation.started < self.probation_s:
            return None
        self._probation = None
        failures = probation.verdicts.count(False)
        if probation.slo_before and probation.verdicts and failures * 2 > len(probation.verdicts):
            self._penalties[probation.rule] = now + self.penalty_s
            logger.warning("rule %s failed the SLO in %d/%d windows; rolling back", probation.rule, failures, len(probation.verdicts))
            return self._change(self.policy.rule(probation.previous), now, f"rollback from {probation.rule}", None, probation=False)
        return None

    def _switches_variant(self, rule: Rule) -> bool:
        return VARIANT_KEY in rule.settings and rule.settings[VARIANT_KEY] != self.applied.get(VARIANT_KEY, STOCK)

    def _change(self, rule: Rule, now: float, reason: str, verdict: bool | None, probation: bool = True) -> Action:
        if self._switches_variant(rule):
            self._last_variant_change = now
        previous = self.current
        diff = {key: value for key, value in rule.settings.items() if self.applied.get(key, object()) != value}
        slo_before = all(self._recent_slo[-3:]) if self._recent_slo else bool(verdict)
        self.current, self._last_change = rule.name, now
        self._candidate, self._candidate_windows = None, 0
        self.applied.update(rule.settings)
        if probation and previous is not None:
            self._probation = _Probation(rule.name, previous, now, slo_before)
        self._recent_slo = []
        return Action(rule.name, diff, reason)


def run(
    controller: Controller,
    scrape: Callable[[], Any],
    apply: Callable[[dict[str, Any]], None],
    window_of: Callable[[Any, Any], Window],
    interval_s: float = 5.0,
    log: Callable[[dict[str, Any]], None] = lambda event: None,
    stop: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    previous = scrape()
    while not stop():
        sleep(interval_s)
        if stop():
            break
        current = scrape()
        win = window_of(previous, current)
        previous = current
        now = clock()
        action = controller.step(win, now)
        event: dict[str, Any] = {
            "t": now,
            "demand": round(win.demand, 2),
            "prompt": win.prompt_per_request,
            "tps_per_user": win.tps_per_user,
            "ttft_p90": win.ttft_p90,
            "output_tps": round(win.output_tps, 1),
            "rule": controller.current,
        }
        if action is not None:
            event["action"] = {"rule": action.rule, "settings": action.settings, "reason": action.reason}
            if action.settings:
                started = clock()
                try:
                    apply(action.settings)
                    event["action"]["apply_s"] = round(clock() - started, 3)
                except Exception as exc:
                    event["action"]["error"] = f"{type(exc).__name__}: {exc}"
                    logger.exception("applying %s failed", action.rule)
                    controller.forget()
        log(event)
