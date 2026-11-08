from __future__ import annotations

import logging
import time
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass, field, replace
from typing import Any, Callable

from livetune.knobs import VARIANT_KEY
from livetune.metrics import Window
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
    demand_decay: float = 0.8
    min_requests: float = 2.0
    variant_dwell: int = 6
    variant_cooldown_s: float = 600.0
    margin: float = 0.15
    # Off in observe mode: nothing was applied, so live SLO results say nothing about the rule.
    judge_changes: bool = True
    # Settings a rule omits fall back to these, so every rule, and every rollback, sets the same keys.
    startup: dict[str, Any] = field(default_factory=dict)
    current: str | None = None
    applied: dict[str, Any] = field(default_factory=dict)
    shape: Shape | None = None
    _candidate: str | None = None
    _candidate_windows: int = 0
    _deferred_windows: int = 0
    _last_change: float = float("-inf")
    _last_variant_change: float = float("-inf")
    _probation: _Probation | None = None
    _recent_slo: list[bool] = field(default_factory=list)
    _penalties: dict[str, float] = field(default_factory=dict)

    def forget(self) -> None:
        self.current, self.applied, self._probation = None, {}, None

    def observe(self, window: Window) -> Shape | None:
        prompt = window.prompt_per_request
        if self.shape is None:
            # Prompt length is unknown until a request arrives; do not guess a shape.
            if prompt is None:
                return None
            self.shape = Shape(window.demand, prompt, window.cache_hit, window.output_per_request)
            return self.shape

        def smooth(new: float | None, old: float | None) -> float | None:
            if new is None or old is None:
                return old if new is None else new
            return self.smoothing * new + (1 - self.smoothing) * old

        # Closed-loop clients finish in waves, so a scrape can land in a gap: rise at once, decay slowly.
        demand = max(window.demand, self.demand_decay * self.shape.demand)
        self.shape = Shape(
            demand,
            smooth(prompt, self.shape.prompt_tokens),
            smooth(window.cache_hit, self.shape.cache_hit),
            smooth(window.output_per_request, self.shape.output_tokens),
        )
        return self.shape

    def _slo(self, window: Window) -> bool | None:
        if window.requests < self.min_requests and window.generation_tokens <= 0:
            return None
        return self.policy.slo.met(window.tps_per_user, window.ttft_p90)

    def step(self, window: Window, now: float) -> Action | None:
        shape = self.observe(window)
        if shape is None:
            return None
        verdict = self._slo(window)
        if self.current is None:
            return self._change(self.policy.select(shape), now, "initial", verdict, defer_variant=True)

        rollback = self._judge_probation(verdict, now)
        if rollback is not None:
            return rollback
        if verdict is not None:
            self._recent_slo = (self._recent_slo + [verdict])[-6:]

        target = self._robust_target(shape)
        if target.name == self.current and self._switches_variant(target):
            # The rule's variant was held back: it waits for the same dwell and cooldown as any switch.
            self._deferred_windows += 1
            if self._deferred_windows >= self.variant_dwell and now - self._last_variant_change >= self.variant_cooldown_s:
                return self._change(target, now, "deferred variant", verdict, probation=False)
            return None
        self._deferred_windows = 0
        if target.name == self.current or self._penalties.get(target.name, float("-inf")) > now:
            self._candidate, self._candidate_windows = None, 0
            return None
        if target.name == self._candidate:
            self._candidate_windows += 1
        else:
            self._candidate, self._candidate_windows = target.name, 1
        if self._candidate_windows < self.dwell or now - self._last_change < self.cooldown_s:
            return None
        # One change at a time: a rule is judged before another replaces it.
        if self._probation is not None:
            return None
        # Switching variants recaptures CUDA graphs and stalls decoding for seconds.
        if self._switches_variant(target) and (
            self._candidate_windows < self.variant_dwell or now - self._last_variant_change < self.variant_cooldown_s
        ):
            return None
        return self._change(target, now, f"shape demand={shape.demand:.1f} prompt={shape.prompt_tokens:.0f}", verdict)

    def _robust_target(self, shape: Shape) -> Rule:
        # Hysteresis: keep the current rule while the shape is within ±margin of its box.
        # Only the current rule gets this slack, so a shape far from it always moves.
        target = self.policy.select(shape)
        if target.name == self.current:
            return target
        factors = (1 / (1 + self.margin), 1.0, 1 + self.margin)
        for d in factors:
            for p in factors:
                if self.policy.select(replace(shape, demand=shape.demand * d, prompt_tokens=shape.prompt_tokens * p)).name == self.current:
                    return self.policy.rule(self.current)
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

    def _settings(self, rule: Rule) -> dict[str, Any]:
        return {**self.startup, **rule.settings}

    def _switches_variant(self, rule: Rule) -> bool:
        # An unknown variant (nothing applied yet, or forgotten after a failure) counts as a switch.
        settings = self._settings(rule)
        return VARIANT_KEY in settings and settings[VARIANT_KEY] != self.applied.get(VARIANT_KEY)

    def _change(self, rule: Rule, now: float, reason: str, verdict: bool | None, probation: bool = True, defer_variant: bool = False) -> Action:
        previous = self.current
        settings = self._settings(rule)
        if defer_variant and self._switches_variant(rule):
            # The first rule, or the re-apply after a failure (when the switch may be what failed):
            # set the other knobs now; the variant follows after its dwell and cooldown.
            settings.pop(VARIANT_KEY, None)
        diff = {key: value for key, value in settings.items() if self.applied.get(key, object()) != value}
        if VARIANT_KEY in diff:
            self._last_variant_change = now
        slo_before = all(self._recent_slo[-3:]) if self._recent_slo else bool(verdict)
        self.current, self._last_change = rule.name, now
        self._candidate, self._candidate_windows, self._deferred_windows = None, 0, 0
        self.applied.update(settings)
        # Only a change that sent something can be judged; a rule with the same settings is not one.
        if probation and self.judge_changes and previous is not None and diff:
            self._probation = _Probation(rule.name, previous, now, slo_before)
        self._recent_slo = []
        return Action(rule.name, diff, reason)


def run(
    controller: Controller,
    scrape: Callable[[], Any],
    apply: Callable[[dict[str, Any]], dict[str, Any] | None],
    window_of: Callable[[Any, Any], Window],
    interval_s: float = 5.0,
    log: Callable[[dict[str, Any]], None] = lambda event: None,
    stop: Callable[[], bool] = lambda: False,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    wall: Callable[[], float] = time.time,
    step_lock: AbstractContextManager[Any] | None = None,
) -> None:
    # step_lock is held from scrape to log, so a reader holding it never sees a window half done.
    lock = step_lock if step_lock is not None else nullcontext()
    previous = None
    while not stop():
        if previous is not None:
            sleep(interval_s)
            if stop():
                break
        with lock:
            try:
                current = scrape()
            except Exception as exc:
                # A failed scrape loses one window; the next good scrape starts a fresh one.
                log({"t": clock(), "wall": wall(), "error": f"{type(exc).__name__}: {exc}"})
                current = None
            if current is not None and previous is not None:
                _step(controller, window_of(previous, current), apply, log, clock(), wall())
        if current is None:
            sleep(interval_s)
        previous = current


def _step(controller: Controller, win: Window, apply: Callable[[dict[str, Any]], dict[str, Any] | None],
          log: Callable[[dict[str, Any]], None], now: float, wall: float) -> None:
    action = controller.step(win, now)
    # Stamped before applying, so an event belongs to the window it started in however long the apply takes.
    event: dict[str, Any] = {
        "t": now,
        "wall": wall,
        "demand": round(win.demand, 2),
        "prompt": win.prompt_per_request,
        "cache_hit": None if win.cache_hit is None else round(win.cache_hit, 3),
        "output_per_request": None if win.output_per_request is None else round(win.output_per_request, 1),
        "tps_per_user": win.tps_per_user,
        "ttft_p90": win.ttft_p90,
        "output_tps": round(win.output_tps, 1),
        "rule": controller.current,
    }
    if action is not None:
        event["action"] = {"rule": action.rule, "settings": action.settings, "reason": action.reason}
    if controller.current is not None:
        # Re-assert the whole rule every window: a restarted server comes back on its startup
        # settings, and apply sends only what differs from the live state.
        started = time.monotonic()
        try:
            sent = apply(dict(controller.applied))
        except Exception as exc:
            event.setdefault("action", {"rule": controller.current, "reason": "reconcile"})["error"] = f"{type(exc).__name__}: {exc}"
            logger.exception("applying %s failed", controller.current)
            controller.forget()
        else:
            if action is not None:
                event["action"]["apply_s"] = round(time.monotonic() - started, 3)
            elif sent:
                event["reconciled"] = sent
    log(event)
