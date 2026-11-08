import hashlib
from dataclasses import replace as dataclasses_replace
import json
import math
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from livetune import controller as control  # noqa: E402
from livetune import cli, knobs, loadgen, metrics, tune, variants  # noqa: E402
from livetune.policy import Policy, Rule, Shape, Slo  # noqa: E402

STARTUP = {"max_running_requests": 64, "chunked_prefill_size": 8192, "max_prefill_tokens": 8192}


class KnobTest(unittest.TestCase):
    def test_accepts_values_inside_the_startup_envelope(self):
        out = knobs.validate_settings({"max_running_requests": 16, "chunked_prefill_size": 2048, "forward_variant": 0}, STARTUP, 256)
        self.assertEqual(out["max_running_requests"], 16)

    def test_rejects_out_of_range_unaligned_and_unknown_values(self):
        for bad in ({"max_running_requests": 65}, {"max_running_requests": 0}, {"chunked_prefill_size": 1000},
                    {"max_running_requests": 3.5}, {"max_running_requests": True}, {"tp_size": 2}):
            with self.subTest(bad=bad), self.assertRaises(knobs.InvalidSetting):
                knobs.validate_settings(bad, STARTUP, 256)

    def test_knob_unavailable_when_server_started_without_it(self):
        with self.assertRaises(knobs.InvalidSetting):
            knobs.validate_settings({"chunked_prefill_size": 256}, {**STARTUP, "chunked_prefill_size": None}, 256)


class VariantTest(unittest.TestCase):
    def test_patcher_restores_instance_class_and_module_state(self):
        class Layer:
            def forward(self):
                return "stock"

        layer, module = Layer(), types.ModuleType("fake_kernels")
        module.kernel = lambda: "stock"
        patch = variants.Patcher()
        patch(layer, "forward", lambda: "fast")
        patch(Layer, "added", 1)
        patch(module, "kernel", lambda: "fast")
        patch(module, "kernel", lambda: "faster")
        self.assertEqual((layer.forward(), module.kernel()), ("fast", "faster"))
        self.assertEqual(patch.undo(), 4)
        self.assertEqual((layer.forward(), module.kernel()), ("stock", "stock"))
        self.assertFalse(hasattr(Layer, "added"))

    def test_register_and_resolve_by_id_with_pinned_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = variants.register(tmp, "fused", "def install(m, p, c): pass\n")
            second = variants.register(tmp, "other", "def install(m, p, c): pass\n")
            self.assertEqual((first, second), (1, 2))
            self.assertEqual(variants.register(tmp, "fused", "def install(m, p, c): return 1\n"), 1)
            self.assertEqual(variants.resolve(1, tmp).name, "fused")
            (Path(tmp) / "fused.py").write_text("tampered")
            with self.assertRaises(variants.VariantError):
                variants.resolve(1, tmp)
            for bad in (0, -1, 3, True, "1"):
                with self.subTest(bad=bad), self.assertRaises(variants.VariantError):
                    variants.resolve(bad, tmp)
            with self.assertRaises(variants.VariantError):
                variants.register(tmp, "../escape", "")

    def test_failed_install_undoes_partial_patches(self):
        model = types.SimpleNamespace(value=1)
        code = "def install(model, patch, ctx):\n    patch(model, 'value', 2)\n    raise RuntimeError('boom')\n"
        with self.assertRaises(RuntimeError):
            variants.install(variants.VariantSource("bad", code, "0" * 64), model, {})
        self.assertEqual(model.value, 1)

    def test_install_and_uninstall(self):
        model = types.SimpleNamespace(value=1)
        code = "def install(model, patch, ctx):\n    patch(model, 'value', ctx['v'])\n"
        installed = variants.install(variants.VariantSource("v", code, "0" * 64), model, {"v": 5})
        self.assertEqual(model.value, 5)
        variants.uninstall(installed)
        self.assertEqual(model.value, 1)


METRICS_A = """# HELP x
sglang:num_running_reqs{tp_rank="0"} 4
sglang:num_queue_reqs{tp_rank="0"} 1
sglang:prompt_tokens_total{tp_rank="0"} 1000
sglang:generation_tokens_total{tp_rank="0"} 500
sglang:cached_tokens_total{tp_rank="0"} 100
sglang:num_requests_total{tp_rank="0"} 10
sglang:request_time_per_output_token_seconds_bucket{le="0.005"} 0
sglang:request_time_per_output_token_seconds_bucket{le="0.01"} 50
sglang:request_time_per_output_token_seconds_bucket{le="+Inf"} 100
sglang:request_time_per_output_token_seconds_count 100
"""
METRICS_B = METRICS_A.replace("1000", "5000").replace("generation_tokens_total{tp_rank=\"0\"} 500", "generation_tokens_total{tp_rank=\"0\"} 2500") \
    .replace("cached_tokens_total{tp_rank=\"0\"} 100", "cached_tokens_total{tp_rank=\"0\"} 2100").replace("num_requests_total{tp_rank=\"0\"} 10", "num_requests_total{tp_rank=\"0\"} 14") \
    .replace('le="0.01"} 50', 'le="0.01"} 450').replace('le="+Inf"} 100', 'le="+Inf"} 500').replace("seconds_count 100", "seconds_count 500")


class MetricsTest(unittest.TestCase):
    def test_window_reports_mix_load_and_latency(self):
        win = metrics.window(metrics.parse(METRICS_A, 0.0), metrics.parse(METRICS_B, 10.0))
        self.assertEqual((win.demand, win.requests, win.prompt_per_request), (5.0, 4.0, 1000.0))
        self.assertAlmostEqual(win.cache_hit, 0.5)
        self.assertAlmostEqual(win.output_tps, 200.0)
        self.assertTrue(0.005 < win.request_tpot_p50 <= 0.01)
        self.assertAlmostEqual(win.tps_per_user, 1 / win.request_tpot_p50)

    def test_real_sglang_scrapes_from_a_four_user_2k_prompt_load(self):
        fixtures = Path(__file__).parent / "fixtures"
        earlier = metrics.parse((fixtures / "sglang_metrics_a.txt").read_text(), 0.0)
        later = metrics.parse((fixtures / "sglang_metrics_b.txt").read_text(), 10.0)
        win = metrics.window(earlier, later)
        self.assertEqual(win.running, 4.0)
        self.assertGreater(win.requests, 0)
        self.assertAlmostEqual(win.prompt_per_request, 2000, delta=1)
        self.assertIsNone(win.tps_per_user)  # this capture predates the per-request histogram
        self.assertTrue(0 < win.ttft_p90 < 2, win.ttft_p90)

    def test_real_sglang_per_request_decode_rate(self):
        fixtures = Path(__file__).parent / "fixtures"
        earlier = metrics.parse((fixtures / "sglang_request_tpot_a.txt").read_text(), 0.0)
        later = metrics.parse((fixtures / "sglang_request_tpot_b.txt").read_text(), 15.0)
        win = metrics.window(earlier, later)
        self.assertGreater(win.requests, 0)
        self.assertTrue(50 < win.tps_per_user < 500, win.tps_per_user)

    def test_quantile_interpolates_and_handles_empty(self):
        hist = metrics.Histogram(((1.0, 0.0), (2.0, 10.0), (math.inf, 10.0)), 10.0)
        self.assertAlmostEqual(hist.quantile(0.5), 1.5)
        self.assertIsNone(metrics.Histogram((), 0.0).quantile(0.5))


def _policy():
    return Policy(
        Slo(min_tps_per_user=50, max_ttft_p90_s=5),
        (
            Rule("light", 4, math.inf, {"max_running_requests": 8}),
            Rule("busy", math.inf, math.inf, {"max_running_requests": 32}),
        ),
    )


def _window(demand, tps=100.0, ttft=1.0, requests=5):
    return metrics.Window(10, demand, 0, requests, requests * 1000, 1000, 0, 1 / tps, ttft)


class PolicyTest(unittest.TestCase):
    def test_rules_yield_to_startup_outside_their_measured_cache_hit_and_output_length(self):
        tuned = Rule("agentic", 48, math.inf, {"max_running_requests": 32}, workload={"cache_hit": (0.6, 1.0), "output_tokens": (128, 512)})
        policy = Policy(Slo(50, 5), (tuned, Rule("startup", math.inf, math.inf, {"max_running_requests": 64})))
        self.assertEqual(policy.select(Shape(40, 24000, 0.8, 256)).name, "agentic")
        self.assertEqual(policy.select(Shape(40, 24000)).name, "agentic")  # not yet measured: no constraint
        self.assertEqual(policy.select(Shape(40, 24000, 0.1, 256)).name, "startup")
        self.assertEqual(policy.select(Shape(40, 24000, 0.8, 4000)).name, "startup")
        self.assertEqual(Policy.from_json(policy.to_json()), policy)

    def test_a_workload_miss_falls_back_to_the_catch_all_not_a_later_box(self):
        short = Rule("u2-short", 2.5, math.inf, {"max_running_requests": 2}, workload={"output_tokens": (50, 200)})
        long = Rule("u3-long", 3.5, math.inf, {"max_running_requests": 3}, workload={"output_tokens": (500, 2000)})
        policy = Policy(Slo(50, 5), (short, long, Rule("startup", math.inf, math.inf, {"max_running_requests": 64})))
        self.assertEqual(policy.select(Shape(2, 1000, None, 1000)).name, "startup")
        self.assertEqual(policy.select(Shape(3, 1000, None, 1000)).name, "u3-long")


    def test_select_first_matching_box_and_json_roundtrip(self):
        policy = _policy()
        self.assertEqual(policy.select(Shape(2, 100)).name, "light")
        self.assertEqual(policy.select(Shape(20, 100)).name, "busy")
        self.assertEqual(Policy.from_json(policy.to_json()), policy)

    def test_a_workload_miss_falls_back_to_the_catch_all_not_a_later_box(self):
        short = Rule("u2-short", 2.5, math.inf, {"max_running_requests": 2}, workload={"output_tokens": (50, 200)})
        long = Rule("u3-long", 3.5, math.inf, {"max_running_requests": 3}, workload={"output_tokens": (500, 2000)})
        policy = Policy(Slo(50, 5), (short, long, Rule("startup", math.inf, math.inf, {"max_running_requests": 64})))
        self.assertEqual(policy.select(Shape(2, 1000, None, 1000)).name, "startup")
        self.assertEqual(policy.select(Shape(3, 1000, None, 1000)).name, "u3-long")

    def test_rejects_policies_without_catch_all_or_duplicate_names(self):
        with self.assertRaises(ValueError):
            Policy(Slo(1, 1), (Rule("a", 4, math.inf, {}),))
        with self.assertRaises(ValueError):
            Policy(Slo(1, 1), (Rule("a", 4, 9, {}), Rule("a", math.inf, math.inf, {})))


class ControllerTest(unittest.TestCase):
    def test_initial_rule_then_dwell_and_cooldown_before_switching(self):
        ctl = control.Controller(_policy(), dwell=2, cooldown_s=20, smoothing=1.0)
        first = ctl.step(_window(2), 0)
        self.assertEqual((first.rule, first.settings), ("light", {"max_running_requests": 8}))
        self.assertIsNone(ctl.step(_window(10), 5))
        self.assertIsNone(ctl.step(_window(10), 10))  # dwell met, cooldown not
        switch = ctl.step(_window(10), 25)
        self.assertEqual((switch.rule, switch.settings), ("busy", {"max_running_requests": 32}))

    def test_demand_holds_through_completion_waves_and_decays_when_load_drops(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        ctl.step(_window(56), 0)
        ctl.step(_window(0), 5)
        self.assertGreater(ctl.shape.demand, 40)
        for t in range(10, 80, 5):
            ctl.step(_window(2), t)
        self.assertLess(ctl.shape.demand, 4)

    def test_no_initial_rule_until_a_prompt_length_is_seen(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        quiet = metrics.Window(10, 3, 0, 0, 0, 500, 0, 0.01, None)
        self.assertIsNone(ctl.step(quiet, 0))
        self.assertIsNone(ctl.current)
        self.assertEqual(ctl.step(_window(2), 5).rule, "light")

    def test_oscillating_load_settles_instead_of_flapping(self):
        ctl = control.Controller(_policy(), dwell=2, cooldown_s=0, smoothing=1.0)
        ctl.step(_window(2), 0)
        actions = [ctl.step(_window(demand), t * 5) for t, demand in enumerate([10, 2, 10, 2, 10, 2, 10, 2], start=1)]
        self.assertEqual([a.rule for a in actions if a], ["busy"])

    def test_rollback_when_slo_breaks_after_change_and_penalty_applies(self):
        ctl = control.Controller(_policy(), dwell=1, cooldown_s=0, probation_s=30, penalty_s=100, smoothing=1.0)
        ctl.step(_window(2), 0)
        ctl.step(_window(2), 5)
        self.assertEqual(ctl.step(_window(10), 10).rule, "busy")
        self.assertIsNone(ctl.step(_window(10, tps=20), 20))
        rollback = ctl.step(_window(10, tps=20), 45)
        self.assertEqual((rollback.rule, rollback.reason), ("light", "rollback from busy"))
        self.assertIsNone(ctl.step(_window(10), 60))  # busy is penalised, light stays
        self.assertEqual(ctl.step(_window(10), 150).rule, "busy")

    def test_a_rule_on_probation_is_judged_before_another_replaces_it(self):
        policy = Policy(Slo(50, 5), (Rule("light", 4, math.inf, {"max_running_requests": 8}), Rule("mid", 12, math.inf, {"max_running_requests": 16}),
                                     Rule("busy", math.inf, math.inf, {"max_running_requests": 32})))
        ctl = control.Controller(policy, dwell=1, cooldown_s=0, probation_s=30, smoothing=1.0, demand_decay=0)
        ctl.step(_window(2), 0)
        ctl.step(_window(2), 5)
        self.assertEqual(ctl.step(_window(8), 10).rule, "mid")
        self.assertIsNone(ctl.step(_window(30, tps=20), 15))  # traffic moved on, but "mid" is still on probation
        rollback = ctl.step(_window(30, tps=20), 40)
        self.assertEqual((rollback.rule, rollback.reason), ("light", "rollback from mid"))

    def test_rollback_restores_keys_the_previous_rule_left_at_startup(self):
        policy = Policy(Slo(50, 5), (Rule("light", 4, math.inf, {"max_running_requests": 8}), Rule("busy", math.inf, math.inf, {"chunked_prefill_size": 2048})))
        ctl = control.Controller(policy, dwell=1, cooldown_s=0, probation_s=30, smoothing=1.0, startup=dict(STARTUP))
        self.assertEqual(ctl.step(_window(2), 0).settings, {**STARTUP, "max_running_requests": 8})
        ctl.step(_window(2), 5)
        self.assertEqual(ctl.step(_window(10), 10).settings, {"max_running_requests": 64, "chunked_prefill_size": 2048})
        ctl.step(_window(10, tps=20), 20)
        rollback = ctl.step(_window(10, tps=20), 45)
        self.assertEqual(rollback.settings, {"max_running_requests": 8, "chunked_prefill_size": 8192})

    def test_a_change_that_sends_nothing_starts_no_probation(self):
        policy = Policy(Slo(50, 5), (Rule("a", 4, math.inf, {"max_running_requests": 64}), Rule("b", 12, math.inf, {"max_running_requests": 64}),
                                     Rule("c", math.inf, math.inf, {"max_running_requests": 16})))
        ctl = control.Controller(policy, dwell=1, cooldown_s=0, probation_s=45, smoothing=1.0, demand_decay=0)
        ctl.step(_window(2), 0)
        self.assertEqual(ctl.step(_window(8), 5).settings, {})
        self.assertEqual(ctl.step(_window(30), 10).rule, "c")  # not held behind a probation of "b"

    def test_probation_runs_from_when_the_change_went_live(self):
        ctl = control.Controller(_policy(), dwell=1, cooldown_s=0, probation_s=30, smoothing=1.0)
        ctl.step(_window(2), 0)
        ctl.step(_window(2), 5)
        self.assertEqual(ctl.step(_window(10), 10).rule, "busy")
        ctl.applied_at(50)  # a slow apply (a variant recapture) finished at t=50
        self.assertIsNone(ctl.step(_window(10, tps=20), 55))
        self.assertIsNone(ctl.step(_window(10, tps=20), 75))  # 25 s after going live: still on probation
        self.assertEqual(ctl.step(_window(10, tps=20), 85).reason, "rollback from busy")

    def test_run_loop_takes_a_fresh_baseline_after_applying_a_change(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        scraped, pairs = [], []

        def scrape():
            scraped.append(len(scraped))
            return scraped[-1]

        def window_of(a, b):
            pairs.append((a, b))
            return _window(2)

        control.run(ctl, scrape, lambda settings: settings, window_of, stop=lambda: len(scraped) > 3, clock=lambda: 0.0, sleep=lambda s: None)
        self.assertEqual(pairs[:2], [(0, 1), (2, 3)])  # scrape 2 is the post-apply baseline

    def test_a_window_without_a_per_request_rate_cannot_pass_probation(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        unfinished = metrics.Window(5, 10, 0, 5, 5000, 1000, 0, None, 1.0)
        self.assertIsNone(ctl._slo(unfinished))
        self.assertFalse(ctl._slo(metrics.Window(5, 10, 0, 5, 5000, 1000, 0, None, 9.0)))  # a measured miss still counts

    def test_no_rollback_if_slo_was_already_failing(self):
        ctl = control.Controller(_policy(), dwell=1, cooldown_s=0, probation_s=10, smoothing=1.0)
        ctl.step(_window(2, tps=20), 0)
        ctl.step(_window(2, tps=20), 5)
        ctl.step(_window(10, tps=20), 10)
        self.assertIsNone(ctl.step(_window(10, tps=20), 25))
        self.assertEqual(ctl.current, "busy")

    def test_shape_near_a_box_edge_keeps_the_current_rule(self):
        ctl = control.Controller(_policy(), dwell=1, cooldown_s=0, smoothing=1.0)
        ctl.step(_window(2), 0)
        self.assertIsNone(ctl.step(_window(4.4), 5))  # 4.4 / 1.15 < 4: within the margin of "light"
        self.assertEqual(ctl.step(_window(5), 10).rule, "busy")

    def test_a_shape_far_from_the_current_rule_moves_even_between_narrow_boxes(self):
        # Boxes narrower than the ±15% margin: no shape is robust to both neighbours, yet the
        # controller must not stay on a rule built for a third of the load.
        rules = [Rule(f"u{edge}", edge, math.inf, {"max_running_requests": edge}) for edge in (20, 28, 36, 48)]
        policy = Policy(Slo(50, 5), (*rules, Rule("beyond", math.inf, math.inf, {"max_running_requests": 64})))
        ctl = control.Controller(policy, dwell=2, cooldown_s=0, smoothing=1.0, demand_decay=0)
        ctl.step(_window(12), 0)
        moved = [ctl.step(_window(demand), t) for t, demand in zip(range(5, 60, 5), [40, 36, 35, 40, 36, 35, 40, 36, 35, 40, 36])]
        self.assertEqual([a.rule for a in moved if a], ["u36"])  # two windows at 35-36 pick u36; 40 is within its margin

    def test_a_failed_variant_switch_is_not_retried_every_window(self):
        policy = Policy(Slo(50, 5), (Rule("light", 4, math.inf, {"forward_variant": 0, "max_running_requests": 8}),
                                     Rule("busy", math.inf, math.inf, {"forward_variant": 2, "max_running_requests": 32})))
        ctl = control.Controller(policy, dwell=1, cooldown_s=0, variant_dwell=1, variant_cooldown_s=100, smoothing=1.0, demand_decay=0)
        ctl.step(_window(2), 0)
        self.assertEqual(ctl.step(_window(10), 100).settings, {"forward_variant": 2, "max_running_requests": 32})
        ctl.forget()  # the run loop's response to the switch failing
        # The knobs come back at once; the variant waits out its cooldown, then is retried once.
        self.assertEqual(ctl.step(_window(10), 105).settings, {"max_running_requests": 32})
        self.assertIsNone(ctl.step(_window(10), 150))
        self.assertEqual(ctl.step(_window(10), 200).settings, {"forward_variant": 2})
        self.assertIsNone(ctl.step(_window(10), 205))

    def test_observe_mode_does_not_judge_changes_it_never_applied(self):
        ctl = control.Controller(_policy(), dwell=1, cooldown_s=0, probation_s=10, smoothing=1.0, judge_changes=False)
        ctl.step(_window(2), 0)
        ctl.step(_window(2), 5)
        ctl.step(_window(10, tps=20), 10)
        self.assertIsNone(ctl.step(_window(10, tps=20), 25))
        self.assertEqual(ctl.current, "busy")

    def test_variant_switches_need_longer_dwell_and_cooldown(self):
        policy = Policy(Slo(50, 5), (Rule("light", 4, math.inf, {"forward_variant": 1}), Rule("busy", math.inf, math.inf, {"forward_variant": 0})))
        ctl = control.Controller(policy, dwell=1, cooldown_s=0, variant_dwell=3, variant_cooldown_s=100, smoothing=1.0, probation_s=1, demand_decay=0,
                                 applied={"forward_variant": 1})
        # The server already runs variant 1, so the initial rule switches nothing and starts no cooldown.
        self.assertEqual(ctl.step(_window(2), 0).settings, {})
        self.assertIsNone(ctl.step(_window(10), 5))
        self.assertIsNone(ctl.step(_window(10), 10))  # dwell 2 of 3
        self.assertEqual(ctl.step(_window(10), 15).rule, "busy")
        for t in (20, 25, 30):
            self.assertIsNone(ctl.step(_window(2), t))  # dwell met, variant cooldown (from t=15) not
        self.assertEqual(ctl.step(_window(2), 115).rule, "light")

    def test_a_first_rule_needing_another_variant_waits_for_variant_dwell(self):
        policy = Policy(Slo(50, 5), (Rule("light", math.inf, math.inf, {"forward_variant": 1, "max_running_requests": 8}),))
        ctl = control.Controller(policy, variant_dwell=3, smoothing=1.0, applied={"forward_variant": 0})
        self.assertEqual(ctl.step(_window(2), 0).settings, {"max_running_requests": 8})  # knobs at once, variant held
        self.assertIsNone(ctl.step(_window(2), 5))
        self.assertIsNone(ctl.step(_window(2), 10))
        self.assertEqual(ctl.step(_window(2), 15).settings, {"forward_variant": 1})

    def test_forget_reapplies_full_rule(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        ctl.step(_window(2), 0)
        ctl.forget()
        self.assertEqual(ctl.step(_window(2), 5).settings, {"max_running_requests": 8})

    def test_run_loop_applies_actions_and_forgets_on_failure(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        calls, events, scraped = [], [], []

        def scrape():
            scraped.append(len(scraped))
            return scraped[-1]

        def apply(settings):
            calls.append(settings)
            raise RuntimeError("server rejected")

        control.run(ctl, scrape, apply, lambda a, b: _window(2), log=events.append,
                    stop=lambda: len(scraped) > 3, clock=lambda: 0.0, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)  # each failure forgets state, so every window re-applies
        self.assertTrue(all("error" in e["action"] for e in events))

    def test_run_loop_reasserts_the_rule_after_a_server_restart(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        live = {"max_running_requests": 64}
        events, scraped = [], []

        def apply(settings):
            sent = {k: v for k, v in settings.items() if live.get(k) != v}
            live.update(sent)
            return sent

        def scrape():
            scraped.append(len(scraped))
            if len(scraped) == 3:
                live["max_running_requests"] = 64  # the server restarted on its startup settings
            return scraped[-1]

        control.run(ctl, scrape, apply, lambda a, b: _window(2), log=events.append,
                    stop=lambda: len(scraped) > 4, clock=lambda: 0.0, sleep=lambda s: None)
        self.assertEqual(events[0]["action"]["settings"], {"max_running_requests": 8})
        self.assertEqual([e.get("reconciled") for e in events[1:]], [{"max_running_requests": 8}, None])
        self.assertEqual(live["max_running_requests"], 8)

    def test_run_loop_stamps_events_before_applying_and_holds_the_step_lock(self):
        import threading

        ctl = control.Controller(_policy(), smoothing=1.0)
        lock, walls, events, held = threading.Lock(), iter([100.0, 200.0, 300.0]), [], []

        def apply(settings):
            held.append(lock.locked())
            return {}

        control.run(ctl, lambda: 0, apply, lambda a, b: _window(2), log=events.append, stop=lambda: len(events) >= 1,
                    clock=lambda: 0.0, sleep=lambda s: None, wall=lambda: next(walls), step_lock=lock)
        self.assertEqual((events[0]["wall"], held), (100.0, [True]))
        self.assertFalse(lock.locked())

    def test_run_loop_survives_a_failed_scrape(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        events, calls, results = [], [], iter([0, RuntimeError("metrics down"), 1, 2, 3])

        def scrape():
            item = next(results)
            if isinstance(item, Exception):
                raise item
            return item

        control.run(ctl, scrape, calls.append, lambda a, b: _window(2), log=events.append,
                    stop=lambda: len(calls) >= 1 and len(events) >= 2, clock=lambda: 0.0, sleep=lambda s: None)
        self.assertIn("metrics down", events[0]["error"])
        self.assertEqual(calls, [{"max_running_requests": 8}])

    def test_run_loop_does_nothing_once_stopped_during_sleep(self):
        ctl = control.Controller(_policy(), smoothing=1.0)
        stopped, calls = [], []
        control.run(ctl, lambda: 0, calls.append, lambda a, b: _window(2),
                    stop=lambda: bool(stopped), sleep=lambda s: stopped.append(True))
        self.assertEqual(calls, [])


class TuneTest(unittest.TestCase):
    slo = Slo(50, 5)

    def test_score_ranks_feasible_above_infeasible(self):
        good = {"completed": 3, "errors": 0, "output_tps": 100, "tps_per_user_p50": 60, "ttft_p90": 1}
        fast_but_slow_users = {"completed": 3, "errors": 0, "output_tps": 900, "tps_per_user_p50": 10, "ttft_p90": 1}
        self.assertGreater(tune.score(good, self.slo), tune.score(fast_but_slow_users, self.slo))
        self.assertEqual(tune.score({"completed": 0, "errors": 2}, self.slo)[0], 0)

    def test_a_result_without_a_per_user_rate_is_inconclusive(self):
        single_chunk = {"completed": 5, "errors": 0, "output_tps": 900, "tps_per_user_p50": None, "ttft_p90": 1}
        self.assertEqual(tune.score(single_chunk, self.slo), (0, -math.inf))

    def test_merged_repeats_take_the_worse_middle_value(self):
        runs = [{"output_tps": 100, "tps_per_user_p50": 60, "ttft_p90": 1.0}, {"output_tps": 180, "tps_per_user_p50": 90, "ttft_p90": 3.0}]
        merged = tune.merged(runs)
        self.assertEqual((merged["output_tps"], merged["tps_per_user_p50"], merged["ttft_p90"]), (100, 60, 3.0))
        self.assertEqual(tune.merged([*runs, {"output_tps": 150, "tps_per_user_p50": 70, "ttft_p90": 2.0}])["output_tps"], 150)

    def test_a_repetition_missing_a_metric_makes_the_merge_inconclusive(self):
        runs = [{"output_tps": 180, "tps_per_user_p50": 90, "ttft_p90": 1.0}, {"output_tps": 170, "tps_per_user_p50": None, "ttft_p90": 1.0}]
        self.assertEqual(tune.score(tune.merged([dict(r, completed=5, errors=0) for r in runs]), self.slo), (0, -math.inf))

    def test_coordinate_search_keeps_real_gains_only(self):
        def measure(profile, settings):
            tps = {8: 100, 16: 150, 32: 151}[settings["max_running_requests"]]
            return {"completed": 5, "errors": 0, "output_tps": tps, "tps_per_user_p50": 60, "ttft_p90": 1}

        result = tune.tune_profile(tune.Profile("p", 64, 1000, 100), {"max_running_requests": 8},
                                   {"max_running_requests": [8, 16, 32]}, self.slo, measure)
        self.assertEqual(result["settings"]["max_running_requests"], 16)
        self.assertEqual(len(result["trials"]), 3 + 4)  # search, then two interleaved confirmation rounds

    def test_a_lucky_single_window_does_not_survive_confirmation(self):
        calls = {"n": 0}

        def measure(profile, settings):
            calls["n"] += 1
            lucky = settings["max_running_requests"] == 24 and calls["n"] == 2
            tps = 180 if lucky else 100
            return {"completed": 5, "errors": 0, "output_tps": tps, "tps_per_user_p50": 60, "ttft_p90": 1}

        result = tune.tune_profile(tune.Profile("p", 48, 1000, 100), {"max_running_requests": 64},
                                   {"max_running_requests": [24]}, self.slo, measure)
        self.assertEqual(result["settings"]["max_running_requests"], 64)

    def test_non_binding_caps_are_never_tried_or_chosen(self):
        seen = []

        def measure(profile, settings):
            seen.append(settings["max_running_requests"])
            return {"completed": 5, "errors": 0, "output_tps": 100 + settings["max_running_requests"], "tps_per_user_p50": 90, "ttft_p90": 1}

        tune.tune_profile(tune.Profile("p", 16, 1000, 100), {"max_running_requests": 64}, {"max_running_requests": [8, 16, 32]}, self.slo, measure)
        self.assertEqual(seen, [64, 8])

    def test_best_from_trials_reselects_under_a_new_slo_and_keeps_startup_on_ties(self):
        phase = {"users": 48, "prompt_tokens": 24000, "output_tokens": 256, "shared_prefix": 0.8, "name": "a48", "seconds": 30}
        trials = [
            {"profile": "a48", "settings": {"max_running_requests": 64}, "summary": {"phase": phase, "completed": 9, "errors": 0, "output_tps": 1638, "tps_per_user_p50": 58.8, "ttft_p90": 5.4}},
            {"profile": "a48", "settings": {"max_running_requests": 24}, "summary": {"phase": phase, "completed": 9, "errors": 0, "output_tps": 1843, "tps_per_user_p50": 93.6, "ttft_p90": 6.1}},
        ]
        strict = tune.best_from_trials(trials, Slo(80, 4), {"max_running_requests": 64})
        self.assertEqual(tune.best_from_trials(trials, Slo(80, 10), {"max_running_requests": 64})[0]["settings"]["max_running_requests"], 64)
        trials.append(dict(trials[1]))  # a second measurement makes cap 24 eligible
        loose = tune.best_from_trials(trials, Slo(80, 10), {"max_running_requests": 64})
        self.assertEqual(loose[0]["settings"]["max_running_requests"], 24)
        self.assertEqual(strict[0]["profile"]["users"], 48)
        light = [dict(trials[0], profile="c4", summary=dict(trials[0]["summary"], phase=dict(phase, users=4))),
                 {"profile": "c4", "settings": {"max_running_requests": 8}, "summary": dict(trials[0]["summary"], phase=dict(phase, users=4), output_tps=1700)}]
        self.assertEqual(tune.best_from_trials(light, Slo(50, 10), {"max_running_requests": 64})[0]["settings"]["max_running_requests"], 64)

    def test_trials_reusing_a_profile_name_for_another_workload_are_refused(self):
        phase = {"users": 48, "prompt_tokens": 24000, "output_tokens": 256}
        summary = {"completed": 9, "errors": 0, "output_tps": 1638, "tps_per_user_p50": 58.8, "ttft_p90": 5.4}
        trials = [{"profile": "a", "settings": {"max_running_requests": 64}, "summary": dict(summary, phase=dict(phase, users=users))} for users in (48, 8)]
        with self.assertRaises(ValueError):
            tune.best_from_trials(trials, self.slo, {"max_running_requests": 64})

    def test_profiles_the_policy_cannot_tell_apart_are_refused(self):
        results = [{"profile": {"name": name, "users": 8, "prompt_tokens": 1000, "output_tokens": out}, "settings": {}, "summary": {}}
                   for name, out in (("short", 64), ("long", 1024))]
        with self.assertRaises(ValueError):
            tune.build_policy(results, self.slo, {}, {"max_running_requests": 64})

    def test_policy_boxes_sit_between_profiles_and_stop_near_the_evidence(self):
        results = [
            {"profile": {"name": f"u{u}-p{p}", "users": u, "prompt_tokens": p}, "settings": {"max_running_requests": u}, "summary": {}}
            for u in (1, 8, 32) for p in (1000, 30000)
        ]
        start = {"max_running_requests": 64}
        policy = tune.build_policy(results, self.slo, {}, start)
        self.assertEqual(policy.select(Shape(7, 900)).name, "u8-p1000")
        self.assertEqual(policy.select(Shape(1.2, 1200)).name, "u1-p1000")
        self.assertEqual(policy.select(Shape(35, 26000)).name, "u32-p30000")
        # Sparse levels leave gaps: 4.5 users is between the reach of 1 and of 8, 15,500 tokens between
        # the reach of 1,000 and of 30,000, so neither measurement is stretched across them.
        for unmeasured in (Shape(100, 20000), Shape(100, 900), Shape(2, 90000), Shape(4.5, 900), Shape(8, 15500), Shape(20, 900)):
            with self.subTest(unmeasured=unmeasured):
                self.assertEqual(policy.select(unmeasured).settings, start)

    def test_tuned_rules_carry_their_profile_cache_hit_and_output_range(self):
        results = [{"profile": {"name": "a", "users": 8, "prompt_tokens": 24000, "output_tokens": 256, "shared_prefix": 0.8},
                    "settings": {"max_running_requests": 8}, "summary": {}}]
        rule = tune.build_policy(results, self.slo, {}, {"max_running_requests": 64}).rule("a")
        self.assertEqual(rule.workload["output_tokens"], (128, 512))
        self.assertAlmostEqual(rule.workload["cache_hit"][0], 0.6)
        self.assertEqual(rule.workload["cache_hit"][1], 1.0)

    def test_neighbouring_measurements_meet_halfway_when_their_reaches_overlap(self):
        results = [{"profile": {"name": f"u{u}", "users": u, "prompt_tokens": 1000}, "settings": {"max_running_requests": u}, "summary": {}}
                   for u in (16, 24)]
        policy = tune.build_policy(results, self.slo, {}, {"max_running_requests": 64})
        self.assertEqual([policy.select(Shape(d, 1000)).name for d in (13, 19.9, 20.1, 30)], ["u16", "u16", "u24", "u24"])


class PolicyScopeTest(unittest.TestCase):
    def test_scope_mismatch_names_the_differing_launch_arguments(self):
        scope = {"server_args": {"speculative_num_steps": 3, "tp_size": 4}, "gpu": "B300"}
        self.assertEqual(cli._differences(scope, {**scope, "server_args": {"speculative_num_steps": 2, "tp_size": 4}}),
                         {"server_args.speculative_num_steps": (3, 2)})

    def test_kv_capacity_is_in_scope_within_a_tolerance(self):
        scope = {"server_args": {"tp_size": 4}, "kv_tokens": 1_000_000}
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(Policy(_policy().slo, _policy().rules, {"scope": scope}).to_json())
            near = types.SimpleNamespace(fingerprint=lambda: {**scope, "kv_tokens": 990_000})
            self.assertEqual(cli.load_policy(str(path), near, False).rules[0].name, "light")
            small = types.SimpleNamespace(fingerprint=lambda: {**scope, "kv_tokens": 600_000})
            with self.assertRaises(SystemExit):
                cli.load_policy(str(path), small, False)

    def test_policy_from_a_different_server_is_refused_unless_overridden(self):
        scope = {"model_path": "a", "tp_size": 4, "gpu": "B300"}
        live = types.SimpleNamespace(fingerprint=lambda: {**scope, "gpu": "H200"})
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            path.write_text(Policy(_policy().slo, _policy().rules, {"scope": scope}).to_json())
            with self.assertRaises(SystemExit):
                cli.load_policy(str(path), live, False)
            self.assertEqual(cli.load_policy(str(path), live, True).rules[0].name, "light")
            same = types.SimpleNamespace(fingerprint=lambda: dict(scope))
            self.assertEqual(cli.load_policy(str(path), same, False).rules[0].name, "light")


class FingerprintTest(unittest.TestCase):
    def _server(self, livetune):
        from livetune import server as server_module

        info = {"model_path": "m", "tp_size": 4, "speculative_num_steps": 3, "api_key": "x", "port": 30000, "dist_init_addr": "10.0.0.1:5000",
                "max_running_requests": 16, "random_seed": 7, "max_total_num_tokens": 123}
        replies = {"/server_info": {**info, "internal_states": [{"livetune": livetune}]},
                   "/model_info": {"model_path": "m2", "weight_version": "step-900", "is_generation": True}}

        class Fake(server_module.Server):
            def _request(self, path, body=None, timeout=None):
                return json.dumps(replies[path]).encode()

        return Fake("http://gpu-host:30000"), server_module

    def test_scope_names_the_gpu_the_server_reports_not_the_callers(self):
        server, _ = self._server({"gpu": "NVIDIA B300", "page_size": 256, "startup": STARTUP, "variant": None, "variants": {"1": "ab"}})
        scope = server.fingerprint()
        self.assertEqual((scope["gpu"], scope["page_size"], scope["startup"]), ("NVIDIA B300", 256, STARTUP))
        # Launch arguments are in scope, except secrets, per-replica addresses, random draws and the knobs livetune moves.
        self.assertEqual(scope["server_args"], {"model_path": "m", "speculative_num_steps": 3, "tp_size": 4})
        self.assertEqual((scope["kv_tokens"], scope["variants"]), (123, {"1": "ab"}))
        self.assertEqual(scope["model"], {"model_path": "m2", "weight_version": "step-900"})  # the weights serving now
        self.assertNotIn("variant", scope)  # the live variant is state, not scope

    def test_data_parallel_schedulers_must_share_one_scope(self):
        server, server_module = self._server({"gpu": "NVIDIA B300", "page_size": 256, "startup": STARTUP})
        info = json.loads(server._request("/server_info"))
        info["internal_states"].append({"livetune": {"gpu": "NVIDIA H200", "page_size": 256, "startup": STARTUP}})
        server._request = lambda path, body=None, timeout=None: json.dumps(info).encode()
        with self.assertRaises(server_module.UpdateFailed):
            server.fingerprint()

    def test_server_that_does_not_report_its_gpu_has_no_scope(self):
        server, server_module = self._server({"startup": STARTUP})
        with self.assertRaises(server_module.UpdateFailed):
            server.fingerprint()


class LoadSummaryTest(unittest.TestCase):
    def test_requests_cut_at_the_deadline_count_tokens_but_not_latency(self):
        result = loadgen.PhaseResult(loadgen.Phase(2, 100, 50, 10.0))
        result.requests = [
            loadgen.RequestRecord(0.0, ttft=0.5, tokens=50, decode_tps=100.0),
            loadgen.RequestRecord(5.0, ttft=9.0, tokens=20, decode_tps=4.0, cut=True),
            loadgen.RequestRecord(6.0, error="http 503"),
        ]
        summary = result.summary()
        self.assertEqual((summary["completed"], summary["errors"]), (1, 1))
        self.assertEqual((summary["tps_per_user_p50"], summary["ttft_p90"]), (100.0, 0.5))
        self.assertEqual(summary["output_tps"], 7.0)

    def test_percentiles_use_nearest_rank(self):
        result = loadgen.PhaseResult(loadgen.Phase(10, 100, 50, 10.0))
        result.requests = [loadgen.RequestRecord(0.0, ttft=float(i), tokens=2, decode_tps=float(i)) for i in range(1, 11)]
        summary = result.summary()
        self.assertEqual((summary["ttft_p90"], summary["tps_per_user_p10"], summary["ttft_p50"]), (9.0, 1.0, 5.0))

    def test_decode_rate_excludes_tokens_that_arrived_with_the_first_chunk(self):
        import asyncio

        clock = iter([0.0, 1.0, 2.0])
        chunks = [{"meta_info": {"completion_tokens": n}} for n in (4, 6, 10)]

        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            @property
            async def content(self):
                for chunk in chunks:
                    yield f"data: {json.dumps(chunk)}".encode()

        session = types.SimpleNamespace(post=lambda url, json: Response())
        record = loadgen.RequestRecord(0.0)
        saved = loadgen.time.perf_counter
        loadgen.time.perf_counter = lambda: next(clock)
        try:
            asyncio.run(loadgen._one(session, "http://x", [1], 10, record))
        finally:
            loadgen.time.perf_counter = saved
        self.assertEqual((record.tokens, record.decode_tps), (10, 3.0))  # the 6 tokens after the first chunk, over 2 s
        chunks[:] = [{"meta_info": {"completion_tokens": 10}}]
        clock = iter([0.0])
        single = loadgen.RequestRecord(0.0)
        loadgen.time.perf_counter = lambda: next(clock)
        try:
            asyncio.run(loadgen._one(session, "http://x", [1], 10, single))
        finally:
            loadgen.time.perf_counter = saved
        result = loadgen.PhaseResult(loadgen.Phase(1, 100, 10, 10.0), [single])
        self.assertEqual((single.decode_tps, result.summary()["completed"], result.summary()["tps_per_user_p50"]), (None, 1, None))

    def test_tokens_streamed_before_an_error_still_count(self):
        result = loadgen.PhaseResult(loadgen.Phase(1, 100, 50, 10.0))
        result.requests = [loadgen.RequestRecord(0.0, tokens=30, error="ClientPayloadError")]
        self.assertEqual(result.summary()["output_tps"], 3.0)

    def test_shared_prefix_longer_than_the_corpus_is_rejected(self):
        prompts = loadgen.PromptSource(list(range(2000)))
        self.assertEqual(len(prompts.prompt(1500, 0.5, 0)), 1500)
        with self.assertRaises(ValueError):
            prompts.prompt(5000, 0.5, 0)
        for bad in (-0.1, 1.5):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                prompts.prompt(100, bad, 0)


class ReplayReportTest(unittest.TestCase):
    def test_phase_report_lists_rules_and_reaction_time_inside_the_phase(self):
        events = [{"wall": 5, "rule": "light"}, {"wall": 112, "rule": "busy", "action": {"rule": "busy"}}, {"wall": 130, "rule": "busy"}, {"wall": 400, "rule": "light"}]
        summary = {"tps_per_user_p50": 90, "ttft_p90": 2}
        report = cli.phase_report(summary, events, 100, 60, _policy(), "controlled")
        self.assertEqual((report["rules"], report["first_switch_s"], report["slo_met"]), (["busy"], 12.0, True))
        self.assertTrue(report["valid"])
        unmeasured = cli.phase_report({"tps_per_user_p50": None, "ttft_p90": 1}, events, 100, 60, _policy(), "controlled")
        self.assertIsNone(unmeasured["slo_met"])
        events.append({"wall": 140, "rule": "busy", "action": {"rule": "busy", "reason": "reconcile", "error": "UpdateFailed: rejected"}})
        rejected = cli.phase_report(summary, events, 100, 60, _policy(), "controlled")
        self.assertEqual((rejected["apply_errors"], rejected["valid"]), (1, False))


class PluginTest(unittest.TestCase):
    def setUp(self):
        from livetune import sglang_plugin

        self.plugin = sglang_plugin
        parallel = types.SimpleNamespace(pp_size=1, tp_rank=0, tp_size=4, dp_size=1, pp_max_micro_batch_size=48)
        self.parallel = parallel
        # A stand-in for the parts of SGLang the plugin touches.
        config = types.SimpleNamespace(schedule_conservativeness=1.0, stream_interval=1)
        self.config, self.overrides = config, []

        class Context:
            def override(this, source, **values):
                self.overrides.append(values)
                for key, value in values.items():
                    setattr(config, key, value)

        runtime = types.ModuleType("sglang.srt.runtime_context")
        runtime.get_parallel = lambda: parallel
        runtime.get_schedule = runtime.get_serving = lambda: config
        runtime.get_context = lambda: Context()
        policy = types.ModuleType("sglang.srt.managers.schedule_policy")

        class SchedulePolicy:
            def __init__(this, name, tree_cache, hierarchical, priority, low_first):
                if name == "routing-key":
                    raise ValueError("routing-key needs routing keys")
                this.name = name

        policy.SchedulePolicy = SchedulePolicy
        tracker = types.ModuleType("sglang.srt.managers.scheduler_components.new_token_ratio_tracker")
        tracker.NewTokenRatioTracker = types.SimpleNamespace(from_config=lambda: types.SimpleNamespace(init=min(0.7 * config.schedule_conservativeness, 1.0)))
        modules = {"sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"), "sglang.srt.runtime_context": runtime,
                   "sglang.srt.managers.schedule_policy": policy, "sglang.srt.managers.scheduler_components.new_token_ratio_tracker": tracker}
        self._saved = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        self.model = types.SimpleNamespace(value=1)
        runner = types.SimpleNamespace(model=self.model)
        self.scheduler = types.SimpleNamespace(page_size=256, max_running_requests=64, chunked_prefill_size=8192, max_prefill_tokens=8192,
                                               schedule_policy="fcfs", max_queued_requests=None, max_total_num_tokens=1_000_000,
                                               tree_cache=None, enable_hierarchical_cache=False, enable_priority_scheduling=False,
                                               schedule_low_priority_values_first=False,
                                               tp_rank=0, tp_size=4, tp_worker=types.SimpleNamespace(model_runner=runner))

        os.environ["LIVETUNE_LIVE_VARIANTS"] = "1"
        self.addCleanup(os.environ.pop, "LIVETUNE_LIVE_VARIANTS", None)
        self.tuner = sglang_plugin.LiveTuner(self.scheduler)
        self.recaptures = []
        self.tuner._recapture = lambda runner: self.recaptures.append(runner)

    def tearDown(self):
        for name, module in self._saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module

    def test_knobs_update_scheduler_and_return_config_overrides(self):
        self.assertEqual(self.tuner.apply("max_running_requests", 16), {"pp_max_micro_batch_size": 16})
        self.assertEqual(self.tuner.apply("chunked_prefill_size", 2048), {"chunked_prefill_size": 2048})
        self.assertEqual(self.scheduler.chunked_prefill_size, 2048)
        state = self.tuner.readback()
        self.assertEqual(state["settings"]["max_running_requests"], 16)
        self.assertEqual(state["startup"]["chunked_prefill_size"], 8192)

    def test_startup_cap_restores_an_explicit_micro_batch_budget(self):
        self.assertEqual(self.tuner.apply("max_running_requests", 16), {"pp_max_micro_batch_size": 16})
        self.assertEqual(self.tuner.apply("max_running_requests", 64), {"pp_max_micro_batch_size": 48})
        self.assertEqual(self.tuner.readback()["pp_micro_batch_startup"], 48)

    def test_pipeline_caps_must_be_exact_multiples_of_pp_size(self):
        self.parallel.pp_size = 2
        self.tuner.validate("max_running_requests", 4)
        self.tuner.validate("max_running_requests", 64)  # the startup cap restores the startup budget
        for value in (1, 3):
            with self.subTest(value=value), self.assertRaises(knobs.InvalidSetting):
                self.tuner.validate("max_running_requests", value)
        self.assertEqual(self.tuner.apply("max_running_requests", 4), {"pp_max_micro_batch_size": 2})

    def test_scheduling_knobs_rebuild_the_objects_sglang_built_from_them_at_startup(self):
        self.assertEqual(self.tuner.startup["schedule_policy"], 0)
        lpm = knobs.SCHEDULE_POLICIES.index("lpm")
        self.tuner.validate("schedule_policy", lpm)
        self.assertEqual(self.tuner.apply("schedule_policy", lpm), {"schedule_policy": "lpm"})
        self.assertEqual((self.scheduler.policy.name, self.scheduler.schedule_policy), ("lpm", "lpm"))
        with self.assertRaises(ValueError):
            self.tuner.validate("schedule_policy", knobs.SCHEDULE_POLICIES.index("routing-key"))
        self.tuner.apply("schedule_conservativeness", 0.5)
        self.assertAlmostEqual(self.scheduler.new_token_ratio_tracker.init, 0.35)  # rebuilt after the override, not from the old value
        self.tuner.apply("max_queued_requests", 0)
        self.assertIsNone(self.scheduler.max_queued_requests)
        self.assertEqual(self.tuner.apply("stream_interval", 8), {"stream_interval": 8})

    def test_validate_bounds_by_startup_not_current_value(self):
        self.tuner.apply("chunked_prefill_size", 2048)
        self.tuner.validate("chunked_prefill_size", 8192)
        with self.assertRaises(knobs.InvalidSetting):
            self.tuner.validate("chunked_prefill_size", 16384)

    def test_variant_switch_waits_for_idle_and_blocks_admission_meanwhile(self):
        with tempfile.TemporaryDirectory() as tmp:
            variant = variants.register(tmp, "bump", "def install(model, patch, ctx):\n    patch(model, 'value', 2)\n")
            os.environ["LIVETUNE_VARIANTS_DIR"] = tmp
            try:
                self.tuner.validate("forward_variant", variant)
                self.tuner.apply("forward_variant", variant)
                self.assertEqual((self.model.value, self.tuner.readback()["pending_variant"]), (1, variant))
                self.assertTrue(self.tuner.admission_blocked())
                self.tuner.on_idle()
                self.assertEqual(self.model.value, 2)
                self.assertFalse(self.tuner.admission_blocked())
                self.assertEqual(self.tuner.readback()["variant"]["name"], "bump")
                self.assertEqual(self.tuner.readback()["variants"], {str(variant): variants.resolve(variant).sha256})
                Path(tmp, "bump.py").write_text("tampered")
                self.assertIn("does not match", self.tuner.readback()["variants"])
                self.tuner.apply("forward_variant", 0)
                self.tuner.on_idle()
                self.assertEqual(self.model.value, 1)
                with self.assertRaises(variants.VariantError):
                    self.tuner.validate("forward_variant", 9)
            finally:
                del os.environ["LIVETUNE_VARIANTS_DIR"]
        self.assertEqual(len(self.recaptures), 2)

    def test_live_variant_switching_is_refused_with_data_parallelism(self):
        self.parallel.dp_size = 2
        with self.assertRaises(knobs.InvalidSetting):
            self.tuner.validate("forward_variant", 1)

    def test_live_variant_switching_is_off_unless_enabled(self):
        os.environ.pop("LIVETUNE_LIVE_VARIANTS")
        with self.assertRaises(knobs.InvalidSetting):
            self.tuner.validate("forward_variant", 1)

    def test_startup_variant_installs_before_graph_capture_and_shows_in_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            variant = variants.register(tmp, "bump", "def install(model, patch, ctx):\n    patch(model, 'value', 3)\n")
            os.environ.update(LIVETUNE_VARIANTS_DIR=tmp, LIVETUNE_STARTUP_VARIANT=str(variant))
            try:
                runner = self.scheduler.tp_worker.model_runner
                self.plugin._install_startup_variant(runner)
                tuner = self.plugin.LiveTuner(self.scheduler)
            finally:
                for key in ("LIVETUNE_VARIANTS_DIR", "LIVETUNE_STARTUP_VARIANT"):
                    del os.environ[key]
        self.assertEqual(self.model.value, 3)
        self.assertEqual((tuner.readback()["settings"]["forward_variant"], tuner.readback()["variant"]["name"]), (variant, "bump"))
        self.assertEqual(tuner.readback()["startup_variant"], tuner.readback()["variant"])  # name and sha of the code installed

    def test_a_failed_switch_keeps_the_variant_that_was_serving(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = variants.register(tmp, "good", "def install(model, patch, ctx):\n    patch(model, 'value', 2)\n")
            bad = variants.register(tmp, "bad", "def install(model, patch, ctx):\n    raise RuntimeError('no kernel')\n")
            os.environ["LIVETUNE_VARIANTS_DIR"] = tmp
            try:
                self.tuner.apply("forward_variant", good)
                self.tuner.on_idle()
                self.tuner.apply("forward_variant", bad)
                self.tuner.on_idle()
            finally:
                del os.environ["LIVETUNE_VARIANTS_DIR"]
        state = self.tuner.readback()
        self.assertEqual((self.model.value, state["settings"]["forward_variant"], state["variant"]["name"]), (2, good, "good"))
        self.assertIn("no kernel", state["recent_errors"][-1]["error"])

    def test_a_failed_recapture_restores_the_previous_variant_on_every_rank(self):
        with tempfile.TemporaryDirectory() as tmp:
            good = variants.register(tmp, "good", "def install(model, patch, ctx):\n    patch(model, 'value', 2)\n")
            other = variants.register(tmp, "other", "def install(model, patch, ctx):\n    patch(model, 'value', 5)\n")
            os.environ["LIVETUNE_VARIANTS_DIR"] = tmp
            try:
                self.tuner.apply("forward_variant", good)
                self.tuner.on_idle()

                def recapture(runner):
                    if self.model.value == 5:
                        raise RuntimeError("illegal memory access")
                    self.recaptures.append(runner)

                self.tuner._recapture = recapture
                self.tuner.apply("forward_variant", other)
                self.tuner.on_idle()
            finally:
                del os.environ["LIVETUNE_VARIANTS_DIR"]
        state = self.tuner.readback()
        self.assertEqual((self.model.value, state["settings"]["forward_variant"], state["variant"]["name"]), (2, good, "good"))
        self.assertEqual(len(self.recaptures), 2)  # the switch to "good", then its restore
        self.assertIn("illegal memory access", state["recent_errors"][-1]["error"])

    def test_scheduler_stops_when_no_variant_can_be_restored(self):
        def recapture(runner):
            raise RuntimeError("CUDA context poisoned")

        self.tuner._recapture = recapture
        self.tuner.apply("forward_variant", 3)
        with self.assertRaises(self.plugin.NoUsableVariant):
            self.tuner.on_idle()

    def test_a_variant_rewritten_under_the_same_id_is_refused_until_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = variants.register(tmp, "bump", "def install(model, patch, ctx):\n    patch(model, 'value', 2)\n")
            os.environ["LIVETUNE_VARIANTS_DIR"] = tmp
            try:
                self.tuner.validate("forward_variant", first)
                again = variants.register(tmp, "bump", "def install(model, patch, ctx):\n    patch(model, 'value', 7)\n")
                self.assertEqual(again, first)
                with self.assertRaises(variants.VariantError):
                    self.tuner.validate("forward_variant", first)
                self.assertIn("changed after this scheduler pinned it", self.tuner.readback()["variants"])
            finally:
                del os.environ["LIVETUNE_VARIANTS_DIR"]

    def test_runtime_digest_covers_the_installed_package_sources(self):
        digest = self.plugin._source_digest("livetune")
        self.assertRegex(digest, "^[0-9a-f]{64}$")
        self.assertEqual(self.tuner.readback()["runtime"]["livetune"], digest)
        self.assertIsNone(self.plugin._source_digest("no_such_package_livetune"))
        self.assertRegex(self.tuner.readback()["runtime"]["packages"], "^[0-9a-f]{64}$")

    def test_runtime_inputs_digest_changes_with_artifact_content_not_location(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            for root in (a, b):
                Path(root, "autotune").mkdir()
                Path(root, "autotune", "sm103.json").write_text("{}")
                Path(root, "artifacts.json").write_text('{"files": []}')
            spec = lambda root: os.pathsep.join([str(Path(root, "artifacts.json")), str(Path(root, "autotune"))])
            self.assertEqual(self.plugin._inputs_digest(spec(a)), self.plugin._inputs_digest(spec(b)))
            Path(b, "autotune", "sm103.json").write_text('{"tile": 128}')
            self.assertNotEqual(self.plugin._inputs_digest(spec(a)), self.plugin._inputs_digest(spec(b)))
        self.assertIsNone(self.plugin._inputs_digest(""))

    def test_readback_reports_whether_live_variants_are_enabled(self):
        self.assertTrue(self.tuner.readback()["live_variants"])
        os.environ.pop("LIVETUNE_LIVE_VARIANTS")
        self.assertFalse(self.tuner.readback()["live_variants"])

    def test_pending_switch_is_cancelled_if_the_scheduler_never_drains(self):
        self.tuner.drain_steps = 10
        self.scheduler.forward_ct = 0
        self.tuner.apply("forward_variant", 3)
        self.scheduler.forward_ct = 5
        self.assertTrue(self.tuner.admission_blocked())
        self.scheduler.forward_ct = 11
        self.assertFalse(self.tuner.admission_blocked())
        self.assertIsNone(self.tuner.readback()["pending_variant"])
        self.assertIn("did not drain", self.tuner.readback()["recent_errors"][-1]["error"])

    def test_failed_apply_never_raises_and_keeps_previous_setting(self):
        with tempfile.TemporaryDirectory() as tmp:
            broken = variants.register(tmp, "broken", "def install(model, patch, ctx):\n    patch(model, 'value', 9)\n    raise RuntimeError('kernel build failed')\n")
            os.environ["LIVETUNE_VARIANTS_DIR"] = tmp
            try:
                self.assertIsNone(self.tuner.apply("forward_variant", broken))
                self.tuner.on_idle()
            finally:
                del os.environ["LIVETUNE_VARIANTS_DIR"]
        state = self.tuner.readback()
        self.assertEqual((self.model.value, state["settings"]["forward_variant"]), (1, 0))
        self.assertIn("kernel build failed", state["recent_errors"][-1]["error"])
        self.assertEqual(len(self.recaptures), 1)

if __name__ == "__main__":
    unittest.main()


def _record(t, prompt=2000, cached=0, output=256, family="f1", **kw):
    from livetune import trace

    return trace.Record(t=t, prompt_tokens=prompt, cached_tokens=cached, output_tokens=output, queue_s=kw.pop("queue_s", 0.1),
                        ttft_s=kw.pop("ttft_s", 0.5), decode_s=kw.pop("decode_s", 2.55), finish="length",
                        families=(family,) if family else (), cached_family=family if cached else None, **kw)


class TraceTest(unittest.TestCase):
    def test_prefix_keys_group_shared_prefixes_without_revealing_them(self):
        from livetune import trace

        keys = trace.PrefixKeys(b"k" * 32)
        a, b = list(range(3000)), list(range(256)) + [7] * 2744
        self.assertEqual(keys.families(a)[0], keys.families(b)[0])  # same first 256 tokens
        self.assertNotEqual(keys.families(a)[1], keys.families(b)[1])
        self.assertEqual(len(keys.families(list(range(100)))), 0)  # too short to name a family
        self.assertNotEqual(keys.digest(a, 256), trace.PrefixKeys(b"j" * 32).digest(a, 256))  # keyed
        self.assertNotIn("0, 1, 2", keys.digest(a, 256))

    def test_writer_rotates_and_reader_round_trips(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            writer = trace.Writer(tmp, max_bytes=600, keep=2)
            for i in range(12):
                writer.write(_record(1000.0 + i))
            writer.close()
            files = sorted(Path(tmp).glob("trace-*.jsonl"))
            self.assertLessEqual(len(files), 2)
            records = list(trace.read([tmp]))
            self.assertTrue(records and records[-1].t == 1011.0)
            self.assertEqual(list(trace.read([tmp], since=1011.0 - 3.05))[0].prompt_tokens, 2000)  # filtered by start time

    def test_summary_describes_the_mix_and_arrivals_keep_families(self):
        from livetune import trace

        records = [_record(100.0 + i, prompt=24000, cached=19200, family="agent") for i in range(8)]
        records += [_record(100.5 + i, prompt=2000, family=f"chat{i}") for i in range(8)]
        summary = trace.summarize(records)
        self.assertEqual(summary["requests"], 16)
        self.assertEqual(summary["bands"]["16-64k"]["share"], 0.5)
        self.assertEqual(summary["families"]["requests_sharing"], 0.5)
        self.assertAlmostEqual(summary["cache_hit"], 19200 * 8 / (24000 * 8 + 2000 * 8), places=3)
        self.assertAlmostEqual(records[0].decode_tps, 100.0)
        schedule = trace.arrivals(records, speed=2.0)
        self.assertEqual(schedule[0].at, 0.0)
        self.assertEqual({a.family for a in schedule if a.prompt_tokens == 24000}, {"agent"})
        self.assertEqual(max(a.at for a in schedule), (107.5 - 100.0) / 2)

    def test_family_prompts_share_their_prefix_at_any_length(self):
        prompts = loadgen.PromptSource(list(range(5000)))
        short, long = prompts.family_prompt(1000, 600, "agent"), prompts.family_prompt(3000, 1800, "agent")
        self.assertEqual(short[:600], long[:600])
        self.assertEqual((len(short), len(long)), (1000, 3000))
        self.assertNotEqual(prompts.family_prompt(1000, 600, "other")[:600], short[:600])


class TelemetryTest(unittest.TestCase):
    def test_a_finished_request_becomes_one_record_with_no_text(self):
        from livetune import sglang_plugin

        class FINISH_LENGTH:
            pass

        times = types.SimpleNamespace(scheduler_recv_time=10.0, wait_queue_entry_time=10.1, prefill_finished_time=10.6,
                                      completion_time=13.15, queue_duration_s=0.2)
        req = types.SimpleNamespace(rid="r1", time_stats=times, origin_input_ids=list(range(3000)), output_ids=[1] * 256,
                                    cached_tokens=2100, finished_reason=FINISH_LENGTH(), retraction_count=0,
                                    sampling_params=types.SimpleNamespace(temperature=0.0, max_new_tokens=256, json_schema=None, regex="a+", ebnf=None),
                                    spec_verify_ct=0, priority=None, lora_id=None, session_id=None, finished=lambda: True)
        with tempfile.TemporaryDirectory() as tmp:
            telemetry = sglang_plugin.Telemetry(tmp, page_size=256)
            telemetry.on_finish(req)
            telemetry.on_finish(req)  # the overlap scheduler outputs a finished request twice
            telemetry.writer.close()
            from livetune import trace

            records = list(trace.read([tmp]))
        self.assertEqual(len(records), 1)
        r = records[0]
        self.assertEqual((r.prompt_tokens, r.cached_tokens, r.output_tokens, r.finish, r.constrained), (3000, 2100, 256, "length", True))
        self.assertAlmostEqual(r.ttft_s, 0.5)  # from waiting-queue entry, on the scheduler's own clock
        self.assertAlmostEqual(r.decode_tps, 100.0)
        self.assertEqual(len(r.families), 2)  # 256 and 2048 tokens deep
        self.assertIsNotNone(r.cached_family)  # 2048 tokens, rounded down to whole pages
        self.assertNotIn("1, 2, 3", r.to_json())

    def test_batches_accumulate_counters_by_forward_mode(self):
        from livetune import sglang_plugin

        telemetry = sglang_plugin.Telemetry(None)
        decode = types.SimpleNamespace(forward_mode=types.SimpleNamespace(name="DECODE"), reqs=[1] * 40, extend_num_tokens=99999, launch_ts=None)
        extend = types.SimpleNamespace(forward_mode=types.SimpleNamespace(name="EXTEND"), reqs=[1] * 2, extend_num_tokens=8192, launch_ts=None)
        telemetry.on_batch(decode, types.SimpleNamespace(can_run_cuda_graph=True))
        telemetry.on_batch(extend, types.SimpleNamespace(can_run_cuda_graph=False))
        batches = telemetry.readback()["batches"]
        self.assertEqual((batches["decode_requests"], batches["decode_tokens"], batches["decode_graph_batches"], batches["extend_tokens"]), (40, 40, 1, 8192))


class AdvisorTest(unittest.TestCase):
    def _window(self, **kw):
        base = dict(seconds=5, running=40, queued=0, requests=10, prompt_tokens=240000, generation_tokens=5000, cached_tokens=192000,
                    request_tpot_p50=0.015, ttft_p90=2.0, kv_used=1e6, kv_evictable=48e6, kv_available=2000, eviction_s=0.6, forward_s=4.0)
        base.update(kw)
        return metrics.Window(**base)

    def _evidence(self, windows, traffic=None, batches=None, settings=None):
        from livetune import advisor

        settings = {**STARTUP, "schedule_policy": 0, "schedule_conservativeness": 1.0, "stream_interval": 1, **(settings or {})}
        return advisor.Evidence(windows, traffic or {"requests": 0}, batches or {}, settings, {**STARTUP}, kv_capacity=49_000_000, page_size=256)

    def test_traffic_mix_rules_and_tiers(self):
        from livetune import advisor

        traffic = {"requests": 100, "families": {"requests_sharing": 0.8}, "queue_s_p90": 2.0, "retracted_share": 0.05,
                   "bands": {"16-64k": {"share": 0.6}}, "cache_hit": 0.2, "arrival_rps": 12, "spec_accept_p50": 1.2}
        batches = {"decode_batches": 100, "decode_graph_batches": 50, "decode_requests": 3000, "decode_seconds": 8, "extend_seconds": 2,
                   "extend_batches": 10, "extend_tokens": 80000}
        proposals = advisor.advise(self._evidence([self._window(kv_available=20e6, eviction_s=0, forward_s=3.0)] * 6, traffic, batches,
                                                  {"max_running_requests": 16}))
        levers = {p.lever: p for p in proposals}
        self.assertEqual(levers["schedule_policy"].values[0], knobs.SCHEDULE_POLICIES.index("lpm"))
        self.assertEqual(levers["schedule_conservativeness"].values, (1.3, 1.6))
        self.assertEqual(levers["max_running_requests"].values, (32, 64))
        self.assertEqual(levers["chunked_prefill_size"].values, (4096, 2048))
        self.assertEqual(levers["stream_interval"].values, (2, 4))
        self.assertEqual((levers["cuda_graph_max_bs_decode"].tier, levers["decode_forward_variant"].tier), ("restart", "code"))
        self.assertEqual([p.tier for p in proposals], sorted((p.tier for p in proposals), key=["live", "restart", "code"].index))


class UtilizationMetricsTest(unittest.TestCase):
    def test_scheduler_series_come_from_one_rank_and_stages_by_category(self):
        text = "\n".join([
            'sglang:kv_available_tokens{tp_rank="0"} 100', 'sglang:kv_available_tokens{tp_rank="1"} 100',
            'sglang:eviction_duration_seconds_sum{tp_rank="0"} 2.0', 'sglang:eviction_duration_seconds_sum{tp_rank="3"} 2.0',
            'sglang:scheduler_stage_seconds_total{category="run_batch",tp_rank="0"} 10', 'sglang:scheduler_stage_seconds_total{category="idle",tp_rank="0"} 50',
        ])
        later = text.replace("2.0", "3.0").replace('run_batch",tp_rank="0"} 10', 'run_batch",tp_rank="0"} 14')
        win = metrics.window(metrics.parse(text, 0.0), metrics.parse(later, 5.0))
        self.assertEqual((win.kv_available, win.eviction_s, win.forward_s), (100, 1.0, 4.0))
        self.assertAlmostEqual(win.forward_share, 0.8)


class ImproveTest(unittest.TestCase):
    def test_a_replaced_policy_takes_over_at_the_next_window_keeping_the_servers_state(self):
        ctl = control.Controller(_policy(), smoothing=1.0, applied={"max_running_requests": 8})
        self.assertEqual(ctl.step(_window(2), 0).settings, {})
        ctl.replace_policy(Policy(Slo(50, 5), (Rule("all", math.inf, math.inf, {"max_running_requests": 24}),)))
        action = ctl.step(_window(2), 5)
        self.assertEqual((action.rule, action.settings), ("all", {"max_running_requests": 24}))

    def _servers(self, canary_gpu):
        scope = {"gpu": "B300", "startup": STARTUP}

        class Fake:
            def __init__(this, url, gpu):
                this.url, this.gpu = url, gpu

            def livetune_state(this):
                return {"settings": dict(STARTUP), "startup": dict(STARTUP), "page_size": 256, "telemetry": {"batches": {}}}

            def livetune_states(this):
                return [this.livetune_state()]

            def scrape(this):
                return metrics.parse("", 0.0)

            def info(this):
                return {"max_total_num_tokens": 1000}

            def fingerprint(this):
                return {**scope, "gpu": this.gpu}

        return Fake("prod", "B300"), Fake("canary", canary_gpu)

    def _improve(self, canary_gpu):
        import argparse

        prod, canary = self._servers(canary_gpu)
        with tempfile.TemporaryDirectory() as tmp:
            saved = cli.Server
            cli.Server = lambda url: canary
            try:
                args = argparse.Namespace(canary="canary", work_dir=tmp, advise_seconds=0, interval=1, trace_dir=tmp, window=600,
                                          slo_tps=50, slo_ttft=5, corpus="", speed=1.0, policy_out=str(Path(tmp, "policy.json")), every=0, once=True,
                                          stage_url=None, fleet="", guard_seconds=0, close_s=0)
                cli.improve(args, prod)
            finally:
                cli.Server = saved
            return [json.loads(line) for line in Path(tmp, "improve.jsonl").read_text().splitlines()]

    def test_improve_refuses_a_canary_that_would_measure_another_intervention(self):
        self.assertEqual(self._improve("H200")[0]["skipped"], {"canary_scope_differs": ["gpu"]})

    def test_improve_publishes_nothing_without_a_proposal(self):
        entry = self._improve("B300")[0]
        self.assertEqual((entry["skipped"], entry.get("published")), ("nothing to test", None))


class RolloutTest(unittest.TestCase):
    slo = Slo(80, 10)

    def test_a_staged_replica_is_promoted_only_when_no_worse_than_its_peers_under_the_same_load(self):
        from livetune import rollout

        peers = [_window(40, tps=85, ttft=3)] * 24
        self.assertEqual(rollout.judge([_window(40, tps=110, ttft=6)] * 12, peers, self.slo).decision, "promote")
        self.assertEqual(rollout.judge([_window(40, tps=70, ttft=3)] * 12, peers, self.slo).decision, "revert")  # misses the SLO more often
        slower = rollout.judge([_window(40, tps=81, ttft=3)] * 12, [_window(40, tps=95, ttft=3)] * 24, self.slo)
        self.assertEqual((slower.decision, "per-user speed" in slower.reason), ("revert", True))
        self.assertEqual(rollout.judge([_window(10, tps=110)] * 12, peers, self.slo).decision, "inconclusive")  # starved by the router
        self.assertEqual(rollout.judge([_window(40, tps=110)] * 3, peers, self.slo).decision, "inconclusive")

    def test_stage_restores_the_replicas_policy_unless_promoted(self):
        import argparse
        from livetune import rollout

        scope = {"gpu": "B300"}
        replica = types.SimpleNamespace(url="replica", fingerprint=lambda: scope, scrape=lambda: metrics.parse("", 0.0),
                                        livetune_state=lambda: {"settings": dict(STARTUP)})
        production = types.SimpleNamespace(fingerprint=lambda: scope)
        with tempfile.TemporaryDirectory() as tmp:
            stage_policy = Path(tmp, "stage.json")
            stage_policy.write_text("previous")
            args = argparse.Namespace(stage_url="replica", peers="peer", stage_policy=str(stage_policy), stage_seconds=0, interval=0,
                                      slo_tps=80, slo_ttft=10, stage_apply_s=0)
            saved = cli.Server
            cli.Server = lambda url: replica
            try:
                verdict = cli.stage(args, production, _policy())
            finally:
                cli.Server = saved
            # The replica never reported the candidate's settings, so nothing was measured or promoted.
            self.assertEqual((verdict.decision, verdict.reason, stage_policy.read_text()), ("inconclusive", "the staged replica did not apply the candidate", "previous"))


class ReplayIsolationTest(unittest.TestCase):
    def test_cold_first_members_share_the_family_prefix_at_one_length(self):
        from livetune import trace

        keys = trace.PrefixKeys(b"k" * 32)
        family = keys.families(list(range(24000)))  # every agent prompt shares its first 24k ids here
        records = [
            dataclasses_replace(_record(100.0, prompt=24000, cached=0, family=None), families=family),  # cold first request
            dataclasses_replace(_record(101.0, prompt=24000, cached=19200, family=None), families=family, cached_family="c19200"),
            dataclasses_replace(_record(102.0, prompt=24000, cached=19456, family=None), families=family, cached_family="c19200"),
            _record(103.0, prompt=2000, family=None),
        ]
        schedule = sorted(trace.arrivals(records), key=lambda a: a.prompt_tokens)
        agents = [a for a in schedule if a.prompt_tokens == 24000]
        # All three share the 16,384-token fixed family, the cold first one included; the two whose
        # cached prefixes hash alike share 19,200 tokens, which the cold one is not proven to.
        self.assertEqual(sorted(a.shared_tokens for a in agents), [16384, 19200, 19200])
        self.assertEqual({a.family for a in agents}, {family[-1], "c19200"})
        self.assertEqual((schedule[0].family, schedule[0].shared_tokens), (None, 0))

    def test_one_members_cache_hit_does_not_extend_the_family(self):
        from livetune import trace

        family = trace.PrefixKeys(b"k" * 32).families(list(range(24000)))
        records = [dataclasses_replace(_record(100.0 + i, prompt=24000, cached=cached, family=None), families=family,
                                       cached_family=f"own{i}" if cached else None) for i, cached in enumerate((0, 19200))]
        # The 19,200-token hit may come from a request outside the trace; only 16,384 tokens are proven shared.
        self.assertEqual({a.shared_tokens for a in trace.arrivals(records)}, {16384})

    def test_modes_replay_cannot_reproduce_are_refused(self):
        from livetune import trace

        with self.assertRaises(ValueError):
            trace.arrivals([_record(100.0), _record(101.0, constrained=True)])
        schedule = trace.arrivals([_record(100.0, priority=3), _record(101.0)])
        self.assertEqual(sorted(a.priority is not None for a in schedule), [False, True])

    def test_a_trace_rules_cache_guard_comes_from_recorded_hits(self):
        from livetune import advisor, trace

        records = [_record(100.0 + i, prompt=10000, cached=4000 if i % 2 else 0, family="f") for i in range(10)]
        profile = tune.trace_profile(trace.arrivals(records))
        self.assertEqual(profile["shared_prefix"], 0.2)  # 4,000 of 10,000 tokens hit on half the requests

    def test_every_measurement_starts_from_a_flushed_cache(self):
        calls = []
        server = types.SimpleNamespace(
            url="http://x", livetune_state=lambda: {"startup": {"max_running_requests": 64}}, fingerprint=lambda: {},
            apply=lambda settings: calls.append(("apply", dict(settings))), flush_cache=lambda: calls.append(("flush",)))
        arrivals = [types.SimpleNamespace(at=0.0, prompt_tokens=2000, output_tokens=8, shared_tokens=0, family=None, temperature=0.7, seconds=1.0, cached_tokens=0, priority=None)]
        saved = loadgen.run_arrivals

        sent = []

        async def fake(url, schedule, prompts, name="trace", warm=True):
            calls.append(("replay",))
            sent.append([list(ids) for ids in prompts])
            result = loadgen.PhaseResult(loadgen.Phase(0, 2000, 8, 1.0))
            result.requests = [loadgen.RequestRecord(0.0, ttft=0.1, tokens=8, decode_tps=100.0)]
            return result

        loadgen.run_arrivals = fake
        try:
            cli.tune_policy(server, Slo(50, 5), loadgen.PromptSource(list(range(5000))), {"max_running_requests": [8]}, None, arrivals, 0, 0, lambda r: None)
        finally:
            loadgen.run_arrivals = saved
        replays = [i for i, c in enumerate(calls) if c[0] == "replay"]
        self.assertTrue(replays and all(calls[i - 1] == ("flush",) for i in replays))
        self.assertTrue(len(sent) > 1 and all(ids == sent[0] for ids in sent))  # the same token ids for every trial


class FamilyDepthTest(unittest.TestCase):
    def test_prompts_of_different_lengths_group_at_the_depth_they_share(self):
        from livetune import trace

        keys = trace.PrefixKeys(b"k" * 32)
        long, short = list(range(20000)), list(range(2048)) + [9] * 2000
        records = [dataclasses_replace(_record(100.0 + i, prompt=len(ids), family=None), families=keys.families(ids)) for i, ids in enumerate((long, short))]
        self.assertEqual(trace.summarize(records)["families"]["requests_sharing"], 1.0)
        schedule = trace.arrivals(records)
        self.assertEqual(len({a.family for a in schedule}), 1)
        self.assertEqual({a.shared_tokens for a in schedule}, {2048})


class RolloutEvidenceTest(unittest.TestCase):
    def test_promotion_needs_windows_that_measured_the_slo_on_both_sides(self):
        from livetune import rollout

        quiet = [_window(40, tps=110, ttft=3)] + [metrics.Window(5, 40, 0, 0, 0, 0, 0, None, None)] * 11
        self.assertEqual(rollout.judge(quiet, [_window(40, tps=85, ttft=3)] * 24, Slo(80, 10)).decision, "inconclusive")

    def test_a_peer_outside_productions_scope_makes_the_stage_inconclusive(self):
        import argparse

        good, stale = {"gpu": "B300"}, {"gpu": "H200"}
        servers = {"replica": types.SimpleNamespace(url="replica", fingerprint=lambda: good),
                   "peer": types.SimpleNamespace(url="peer", fingerprint=lambda: stale)}
        with tempfile.TemporaryDirectory() as tmp:
            stage_policy = Path(tmp, "stage.json")
            stage_policy.write_text("previous")
            args = argparse.Namespace(stage_url="replica", peers="peer", stage_policy=str(stage_policy), stage_seconds=0, interval=0, slo_tps=80, slo_ttft=10)
            saved = cli.Server
            cli.Server = lambda url: servers[url]
            try:
                verdict = cli.stage(args, types.SimpleNamespace(fingerprint=lambda: good), _policy())
            finally:
                cli.Server = saved
            self.assertEqual((verdict.decision, "peer" in verdict.reason, stage_policy.read_text()), ("inconclusive", True, "previous"))


class OpenLoopProfileTest(unittest.TestCase):
    def test_a_trace_policy_rule_sits_at_the_demand_the_trace_produced(self):
        from livetune import trace

        schedule = [trace.Arrival(at=i * 0.5, prompt_tokens=2000, output_tokens=256, shared_tokens=0, family=None, temperature=0.7, seconds=10.0)
                    for i in range(100)]
        profile = tune.trace_profile(schedule)
        self.assertEqual((profile["users"], profile["open_loop"]), (20, True))  # a request every 0.5 s lasting 10 s
        self.assertTrue(tune.binding("max_running_requests", 64, tune.Profile(**profile)))  # open loop: any cap may bind
        result = {"profile": profile, "settings": {"max_running_requests": 16}, "summary": {}}
        policy = tune.build_policy([result], Slo(80, 10), {}, {"max_running_requests": 64})
        self.assertEqual(policy.select(Shape(20, 2000)).name, "trace")

    def test_the_stage_recognises_a_replica_running_a_tuned_rule(self):
        policy = Policy(Slo(80, 10), (Rule("trace", 25, 2500, {"max_running_requests": 16}), Rule("unmeasured", math.inf, math.inf, {"max_running_requests": 64})))
        running = lambda settings: types.SimpleNamespace(livetune_states=lambda: [{"settings": settings}])
        self.assertTrue(cli._runs_candidate(running({**STARTUP, "max_running_requests": 16, "policy_version": policy.version}), policy))
        self.assertFalse(cli._runs_candidate(running(dict(STARTUP)), policy))


class TelemetryRobustnessTest(unittest.TestCase):
    def test_a_bad_trace_key_disables_telemetry_instead_of_raising_into_serving(self):
        from livetune import sglang_plugin

        runtime = types.ModuleType("sglang.srt.runtime_context")
        runtime.get_parallel = lambda: types.SimpleNamespace(attn_tp_rank=0)
        saved = {name: sys.modules.get(name) for name in ("sglang", "sglang.srt", "sglang.srt.runtime_context")}
        sys.modules.update({"sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"), "sglang.srt.runtime_context": runtime})
        os.environ["LIVETUNE_TRACE_KEY"] = "not-hex"
        sglang_plugin._TELEMETRY.clear()
        try:
            telemetry = sglang_plugin._telemetry()
            self.assertIsNone(telemetry.writer)
            self.assertIn("ValueError", telemetry.readback()["error"])
        finally:
            del os.environ["LIVETUNE_TRACE_KEY"]
            sglang_plugin._TELEMETRY.clear()
            for name, module in saved.items():
                sys.modules.pop(name, None) if module is None else sys.modules.__setitem__(name, module)

    def test_rotation_keeps_a_bounded_tail_of_exited_writers(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            dead = 2 ** 22 + 12345  # beyond the default pid range, so no live process has it
            for i in range(5):
                Path(tmp, f"trace-20260101T00000{i}-{dead}-{i:012d}.jsonl").write_text("")
            writer = trace.Writer(tmp, max_bytes=200, keep=2)
            for i in range(10):
                writer.write(_record(1000.0 + i))
            writer.close()
            left = sorted(p.name for p in Path(tmp).glob(f"trace-*-{dead}-*.jsonl"))
            self.assertEqual(left, [f"trace-20260101T00000{i}-{dead}-{i:012d}.jsonl" for i in (3, 4)])

    def test_trials_remember_an_open_loop_workload(self):
        phase = {"users": 20, "prompt_tokens": 2000, "output_tokens": 256}
        summary = {"completed": 9, "errors": 0, "output_tps": 1000, "tps_per_user_p50": 90, "ttft_p90": 1, "phase": phase}
        trials = [{"profile": "trace", "open_loop": True, "settings": {"max_running_requests": cap}, "summary": dict(summary, output_tps=tps)}
                  for cap, tps in ((64, 1000), (32, 1200), (32, 1200))]
        best = tune.best_from_trials(trials, Slo(80, 10), {"max_running_requests": 64})
        self.assertEqual(best[0]["settings"]["max_running_requests"], 32)  # 32 >= 20 users, but open loop lets it bind

    def test_rotation_never_deletes_another_writers_files(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp, "trace-20260101T000000-999999-000000000000.jsonl")
            other.write_text("")
            writer = trace.Writer(tmp, max_bytes=200, keep=1)
            for i in range(10):
                writer.write(_record(1000.0 + i))
            writer.close()
            self.assertTrue(other.exists())


class DataParallelUtilizationTest(unittest.TestCase):
    def test_forward_share_is_per_scheduler_on_a_data_parallel_server(self):
        lines = lambda busy: "\n".join(f'sglang:scheduler_stage_seconds_total{{category="run_batch",dp_rank="{d}",tp_rank="0"}} {busy}' for d in range(4))
        win = metrics.window(metrics.parse(lines(0), 0.0), metrics.parse(lines(2.5), 10.0))
        self.assertEqual((win.schedulers, win.forward_s), (4, 10.0))
        self.assertAlmostEqual(win.forward_share, 0.25)  # each scheduler busy 2.5 s of 10


class GateTest(unittest.TestCase):
    def _sample(self, rows, drift=0.0):
        from livetune import gate

        return gate.Sample([list(r) for r in rows], [[-1.0 - drift] * len(r) for r in rows])

    def test_a_variant_is_judged_against_how_well_stock_agrees_with_itself(self):
        from livetune import gate

        stock = self._sample([[1, 2, 3, 4, 5, 6, 7, 8, 9]] * 4)
        noisy = self._sample([[1, 2, 3, 4, 5, 6, 7, 8, 9]] * 3 + [[1, 2, 3, 9, 9, 9, 9, 9, 9]])  # stock itself diverges on one prompt
        close = self._sample([[1, 2, 3, 4, 5, 6, 7, 8, 9]] * 3 + [[1, 2, 3, 4, 9, 9, 9, 9, 9]], drift=0.01)
        broken = self._sample([[7, 7, 7, 7, 7, 7, 7, 7, 7]] * 4)
        self.assertTrue(gate.judge(stock, noisy, close).passed)
        verdict = gate.judge(stock, noisy, broken)
        self.assertFalse(verdict.passed)
        self.assertTrue(any("prefix match" in r for r in verdict.reasons))
        drifted = gate.judge(stock, stock, self._sample([[1, 2, 3, 4, 5, 6, 7, 8, 9]] * 4, drift=0.5))
        self.assertTrue(any("logprob drift" in r for r in drifted.reasons))


class VariantEvalTest(unittest.TestCase):
    def test_a_failing_variant_is_rejected_and_the_server_returns_to_stock(self):
        import argparse
        from livetune import gate

        applied, calls = [], {"greedy": 0}
        good = gate.Sample([[1, 2, 3, 4, 5, 6, 7, 8]] * 2, [[-1.0] * 8] * 2)
        bad = gate.Sample([[9] * 8] * 2, [[-1.0] * 8] * 2)

        def greedy(prompts, tokens):
            calls["greedy"] += 1
            return good if calls["greedy"] <= 2 else bad  # two stock runs, then the variant

        server = types.SimpleNamespace(url="http://x", livetune_state=lambda: {"settings": {"forward_variant": 2}},
                                       greedy=greedy, apply=lambda s: applied.append(dict(s)), flush_cache=lambda: None)
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "v.py").write_text("def install(model, patch, ctx):\n    pass\n")
            Path(tmp, "corpus.json").write_text(json.dumps(list(range(5000))))
            args = argparse.Namespace(variant=str(Path(tmp, "v.py")), name="kernel", variants_dir=str(Path(tmp, "variants")),
                                      corpus=str(Path(tmp, "corpus.json")), prompts=2, prompt_tokens=64, tokens=8, seed=7,
                                      trace=None, speed=1.0, slo_tps=None, slo_ttft=None)
            report = cli.variant_eval(args, server)
            self.assertTrue(report["variant"].startswith("kernel-"))
            self.assertEqual((report["decision"], report["gate"]["passed"]), ("reject", False))
            self.assertEqual(applied[0], {"forward_variant": 0})  # baselines on real stock, not the incumbent 2
            self.assertEqual(applied[-1], {"forward_variant": 2})  # and the incumbent comes back afterwards
            self.assertEqual(variants.resolve(report["id"], str(Path(tmp, "variants"))).name, report["variant"])


class GuardTest(unittest.TestCase):
    def test_the_fleet_reverts_to_the_previous_policy_when_it_regresses_after_promotion(self):
        import argparse

        good, bad = [_window(40, tps=100, ttft=2)] * 12, [_window(40, tps=60, ttft=2)] * 12
        watched = iter([[good], [bad]])
        saved_watch, saved_runs = cli._watch, cli._runs_candidate
        cli._runs_candidate = lambda server, policy: True
        cli._watch = lambda servers, seconds, interval: next(watched)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "policy.json")
            path.write_text("previous")
            args = argparse.Namespace(fleet="", policy_out=str(path), slo_tps=80, slo_ttft=10, guard_seconds=60, interval=5, stage_apply_s=0)
            saved_wait = cli._wait_applied
            cli._wait_applied = lambda server, policy, timeout, interval: True
            try:
                verdict = cli.promote(args, types.SimpleNamespace(url="prod", fingerprint=lambda: {}), _policy())
            finally:
                cli._watch, cli._wait_applied, cli._runs_candidate = saved_watch, saved_wait, saved_runs
            self.assertEqual((verdict.decision, path.read_text()), ("revert", "previous"))

    def test_an_improvement_stays_published(self):
        import argparse

        before, after = [_window(40, tps=85, ttft=2)] * 12, [_window(40, tps=110, ttft=3)] * 12
        watched = iter([[before], [after]])
        saved_watch, saved_runs = cli._watch, cli._runs_candidate
        cli._runs_candidate = lambda server, policy: True
        cli._watch = lambda servers, seconds, interval: next(watched)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "policy.json")
            path.write_text("previous")
            args = argparse.Namespace(fleet="", policy_out=str(path), slo_tps=80, slo_ttft=10, guard_seconds=60, interval=5, stage_apply_s=0)
            saved_wait = cli._wait_applied
            cli._wait_applied = lambda server, policy, timeout, interval: True
            try:
                verdict = cli.promote(args, types.SimpleNamespace(url="prod", fingerprint=lambda: {}), _policy())
            finally:
                cli._watch, cli._wait_applied, cli._runs_candidate = saved_watch, saved_wait, saved_runs
            self.assertEqual(verdict.decision, "promote")
            self.assertNotEqual(path.read_text(), "previous")


class FleetEvidenceTest(unittest.TestCase):
    def test_schedulers_sharing_a_trace_directory_share_one_prefix_key(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp, tempfile.TemporaryDirectory() as other:
            a, b = trace.PrefixKeys(directory=tmp), trace.PrefixKeys(directory=tmp)
            self.assertEqual(a.digest(list(range(300)), 256), b.digest(list(range(300)), 256))
            self.assertNotEqual(a.key, trace.PrefixKeys(directory=other).key)  # another deployment
            self.assertEqual(oct(Path(tmp, ".trace-key").stat().st_mode & 0o777), "0o600")
            self.assertEqual(list(trace.read([tmp])), [])  # the key file is not a trace

    def test_batch_counters_cover_every_data_parallel_scheduler(self):
        server = types.SimpleNamespace(livetune_states=lambda: [{"telemetry": {"batches": {"decode_batches": 10.0}}},
                                                               {"telemetry": {"batches": {"decode_batches": 30.0}}}, {}])
        self.assertEqual(cli._batch_counters(server), {"decode_batches": 40.0})

    def test_the_guard_reverts_when_a_replica_leaves_the_candidate(self):
        import argparse

        saved = (cli._watch, cli._wait_applied, cli._runs_candidate)
        cli._watch = lambda servers, seconds, interval: [[_window(40, tps=100)] * 12 for _ in servers]
        cli._wait_applied = lambda server, policy, timeout, interval: True
        cli._runs_candidate = lambda server, policy: False  # rolled back by its controller mid-guard
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "policy.json")
            path.write_text("previous")
            args = argparse.Namespace(fleet="", policy_out=str(path), slo_tps=80, slo_ttft=10, guard_seconds=60, interval=5, stage_apply_s=0)
            try:
                verdict = cli.promote(args, types.SimpleNamespace(url="prod", fingerprint=lambda: {}), _policy())
            finally:
                cli._watch, cli._wait_applied, cli._runs_candidate = saved
            self.assertEqual((verdict.decision, path.read_text()), ("revert", "previous"))

    def test_the_guard_ignores_replicas_outside_scope_and_waits_for_the_rest(self):
        import argparse

        good = {"gpu": "B300"}
        members = {"stale": types.SimpleNamespace(url="stale", fingerprint=lambda: {"gpu": "H200"})}
        watched, waited = [], []
        saved = (cli.Server, cli._watch, cli._wait_applied)
        cli.Server = lambda url: members[url]
        cli._watch = lambda servers, seconds, interval: watched.append([s.url for s in servers]) or [[_window(40, tps=100)] * 12 for _ in servers]
        cli._wait_applied = lambda server, policy, timeout, interval: waited.append(server.url) or False
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "policy.json")
            path.write_text("previous")
            args = argparse.Namespace(fleet="stale", policy_out=str(path), slo_tps=80, slo_ttft=10, guard_seconds=60, interval=5, stage_apply_s=0)
            try:
                verdict = cli.promote(args, types.SimpleNamespace(url="prod", fingerprint=lambda: good), _policy())
            finally:
                cli.Server, cli._watch, cli._wait_applied = saved
        self.assertEqual((watched, waited), ([["prod"]], ["prod"]))
        self.assertEqual(verdict.decision, "inconclusive")  # nothing applied, so nothing was judged


class GateBaselineAndAbortTest(unittest.TestCase):
    def test_an_unrepeatable_stock_baseline_rejects_rather_than_passing_anything(self):
        from livetune import gate

        stock = gate.Sample([[1] * 9, [2] * 9], [[-1.0] * 9] * 2)
        unrepeatable = gate.Sample([[5] * 9, [6] * 9], [[-1.0] * 9] * 2)
        different = gate.Sample([[7] * 9, [8] * 9], [[-1.0] * 9] * 2)
        verdict = gate.judge(stock, unrepeatable, different)
        self.assertFalse(verdict.passed)
        self.assertIn("does not repeat itself", verdict.reasons[0])

    def test_aborts_replay_as_the_work_they_did(self):
        from livetune import trace

        records = [_record(100.0), dataclasses_replace(_record(101.0, output=40), finish="abort"),
                   dataclasses_replace(_record(102.0, output=0), finish="abort", launched=False)]
        schedule = trace.arrivals(records)
        self.assertEqual(sorted(a.output_tokens for a in schedule), [40, 256])  # the queued abort never ran


class NestedFamilyAndConcurrencyTest(unittest.TestCase):
    def test_a_short_request_keeps_the_ancestor_it_shares_with_a_deeper_family(self):
        from livetune import trace

        keys = trace.PrefixKeys(b"k" * 32)
        long_a, long_b = list(range(3000)), list(range(3000))
        short = list(range(256)) + [7] * 1000
        records = [dataclasses_replace(_record(100.0 + i, prompt=len(ids), family=None), families=keys.families(ids))
                   for i, ids in enumerate((long_a, long_b, short))]
        schedule = trace.arrivals(records)
        prompts = loadgen.PromptSource(list(range(9000)))
        built = [prompts.family_prompt(a.prompt_tokens, a.shared_tokens, a.family, a.ancestors) for a in schedule]
        by_len = sorted(built, key=len)
        self.assertEqual(by_len[1][:2048], by_len[2][:2048])  # the long pair share 2,048 tokens
        self.assertEqual(by_len[0][:256], by_len[1][:256])  # and the short one shares the 256-token ancestor
        self.assertNotEqual(by_len[0][256:300], by_len[1][256:300])

    def test_concurrency_is_weighted_by_how_long_each_level_lasted(self):
        from livetune import trace

        burst = [trace.Arrival(at=0.0, prompt_tokens=10, output_tokens=1, shared_tokens=0, family=None, temperature=None, seconds=0.1) for _ in range(100)]
        quiet = [trace.Arrival(at=1.0, prompt_tokens=10, output_tokens=1, shared_tokens=0, family=None, temperature=None, seconds=99.0)]
        self.assertEqual(trace.concurrency(burst + quiet), 1)


class ReplayDeterminismTest(unittest.TestCase):
    def test_compression_shortens_arrival_gaps_but_not_service_times(self):
        from livetune import trace

        schedule = trace.arrivals([_record(100.0, ttft_s=0.5, decode_s=9.5), _record(120.0, ttft_s=0.5, decode_s=9.5)], speed=4.0)
        self.assertEqual([a.at for a in schedule], [0.0, 5.0])
        self.assertEqual({a.seconds for a in schedule}, {10.0})


class RequestModeAndPrivacyTest(unittest.TestCase):
    def test_trace_files_and_directory_are_owner_only(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp, "trace")
            writer = trace.Writer(directory)
            writer.write(_record(100.0))
            writer.close()
            self.assertEqual(oct(directory.stat().st_mode & 0o777), "0o700")
            self.assertEqual({oct(p.stat().st_mode & 0o777) for p in directory.glob("trace-*.jsonl")}, {"0o600"})

    def test_sampling_and_logprob_settings_are_replayed(self):
        from livetune import trace

        record = dataclasses_replace(_record(100.0), sampling={"top_p": 0.9, "top_k": 40.0}, logprobs=5)
        arrival = trace.arrivals([record])[0]
        self.assertEqual((arrival.sampling, arrival.logprobs), ({"top_p": 0.9, "top_k": 40.0}, 5))
        self.assertEqual(trace.Record.from_json(record.to_json()), record)

    def test_non_finite_stock_logprobs_fail_the_gate(self):
        from livetune import gate

        rows = [[1, 2, 3, 4, 5, 6, 7, 8, 9]] * 4
        stock = gate.Sample(rows, [[-1.0] * 9] * 3 + [[-1.0] * 8 + [float("nan")]])
        clean = gate.Sample(rows, [[-1.0] * 9] * 4)
        verdict = gate.judge(stock, clean, clean)
        self.assertFalse(verdict.passed)
        self.assertIn("non-finite", verdict.reasons[0])


class PageDepthTest(unittest.TestCase):
    def test_proven_cached_sharing_stops_at_the_hashed_pages(self):
        from livetune import trace

        family = trace.PrefixKeys(b"k" * 32).families(list(range(3000)))
        records = [dataclasses_replace(_record(100.0 + i, prompt=3000, cached=2100, family=None), families=family,
                                       cached_family="c", cached_family_tokens=2048) for i in range(2)]
        self.assertEqual({a.shared_tokens for a in trace.arrivals(records)}, {2048})


class CachedSubfamilyTest(unittest.TestCase):
    def test_a_deeper_cached_prefix_extends_only_the_members_that_share_it(self):
        from livetune import trace

        family = trace.PrefixKeys(b"k" * 32).families(list(range(9000)))[:2]  # shared to 2,048
        deep = [dataclasses_replace(_record(100.0 + i, prompt=9000, cached=8192, family=None), families=family,
                                    cached_family="deep", cached_family_tokens=8192) for i in range(2)]
        shallow = dataclasses_replace(_record(103.0, prompt=9000, cached=0, family=None), families=family)
        schedule = sorted(trace.arrivals(deep + [shallow]), key=lambda a: a.shared_tokens)
        self.assertEqual([a.shared_tokens for a in schedule], [2048, 8192, 8192])
        prompts = loadgen.PromptSource(list(range(20000)))
        built = [prompts.family_prompt(a.prompt_tokens, a.shared_tokens, a.family, a.ancestors) for a in schedule]
        self.assertEqual(built[1][:8192], built[2][:8192])
        self.assertEqual(built[0][:2048], built[1][:2048])
        self.assertNotEqual(built[0][2048:2100], built[1][2048:2100])


class StreamModeTest(unittest.TestCase):
    def test_streaming_and_prompt_logprob_modes_are_recorded_and_replayed(self):
        from livetune import trace

        record = dataclasses_replace(_record(100.0), stream=False, logprobs=0, logprob_start=10)
        arrival = trace.arrivals([record])[0]
        self.assertEqual((arrival.stream, arrival.logprobs, arrival.logprob_start), (False, 0, 10))
        self.assertEqual(trace.Record.from_json(record.to_json()), record)

    def test_a_non_streaming_replay_request_counts_its_tokens(self):
        import asyncio

        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def json(self):
                return {"meta_info": {"completion_tokens": 37}}

        bodies = []
        session = types.SimpleNamespace(post=lambda url, json: bodies.append(json) or Response())
        record = loadgen.RequestRecord(0.0)
        asyncio.run(loadgen._one(session, "http://x", [1], 37, record, stream=False, logprobs=0, logprob_start=5))
        self.assertEqual((record.tokens, record.ttft, bodies[0]["stream"], bodies[0]["logprob_start_len"]), (37, None, False, 5))


class PolicyIdentityAndAbortTest(unittest.TestCase):
    def test_a_replica_counts_as_running_the_candidate_only_once_its_controller_loaded_it(self):
        policy = Policy(Slo(80, 10), (Rule("trace", 25, 2500, {"max_running_requests": 16}), Rule("unmeasured", math.inf, math.inf, {"max_running_requests": 64})))
        running = lambda settings: types.SimpleNamespace(livetune_states=lambda: [{"settings": settings}])
        matching = {**STARTUP, "max_running_requests": 16}
        self.assertFalse(cli._runs_candidate(running(matching), policy))  # same settings, other policy
        self.assertTrue(cli._runs_candidate(running({**matching, "policy_version": policy.version}), policy))
        self.assertLess(policy.version, 1 << 48)

    def test_launched_aborts_replay_their_prefill_and_queued_ones_are_dropped(self):
        from livetune import trace

        launched = dataclasses_replace(_record(101.0, output=0), finish="abort", launched=True)
        queued = dataclasses_replace(_record(102.0, output=0), finish="abort", launched=False)
        schedule = trace.arrivals([_record(100.0), launched, queued])
        self.assertEqual(sorted(a.output_tokens for a in schedule), [1, 256])

    def test_multimodal_traces_are_refused(self):
        from livetune import trace

        with self.assertRaises(ValueError):
            trace.arrivals([_record(100.0), dataclasses_replace(_record(101.0), multimodal=True)])

    def test_every_record_is_readable_as_soon_as_it_is_written(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            writer = trace.Writer(tmp)
            writer.write(_record(100.0))
            self.assertEqual(len(list(trace.read([tmp]))), 1)  # before close
            writer.close()


class BudgetAndPrewarmTest(unittest.TestCase):
    def test_replay_declares_the_recorded_limit_and_stops_at_the_observed_output(self):
        import asyncio
        from livetune import trace

        arrival = trace.arrivals([dataclasses_replace(_record(100.0, output=3), max_new_tokens=512, finish="stop")])[0]
        self.assertEqual((arrival.max_new_tokens, arrival.output_tokens), (512, 3))
        chunks = [{"meta_info": {"completion_tokens": n}} for n in range(1, 10)]
        bodies = []

        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            @property
            async def content(self):
                for chunk in chunks:
                    yield f"data: {json.dumps(chunk)}".encode()

        session = types.SimpleNamespace(post=lambda url, json: bodies.append(json) or Response())
        record = loadgen.RequestRecord(0.0)
        asyncio.run(loadgen._one(session, "http://x", [1], arrival.output_tokens, record, max_new_tokens=arrival.max_new_tokens))
        self.assertEqual((bodies[0]["sampling_params"]["max_new_tokens"], record.tokens), (512, 3))

    def test_hits_from_before_the_window_are_prewarmed_and_in_window_ones_are_not(self):
        from livetune import trace

        a = trace.Arrival(at=0.0, prompt_tokens=100, output_tokens=1, shared_tokens=0, family=None, temperature=None, cached_tokens=40)
        b = trace.Arrival(at=1.0, prompt_tokens=100, output_tokens=1, shared_tokens=60, family="f", temperature=None, cached_tokens=0)
        c = trace.Arrival(at=2.0, prompt_tokens=100, output_tokens=1, shared_tokens=60, family="f", temperature=None, cached_tokens=60)
        ids = [list(range(i * 100, i * 100 + 100)) for i in range(3)]
        warm = loadgen.warm_prefixes([a, b, c], ids)
        self.assertEqual(warm, [ids[0][:40]])  # c's hit is explained by b, earlier in the window


class ReplayCutoffTest(unittest.TestCase):
    def test_non_streaming_early_stops_are_refused(self):
        from livetune import trace

        with self.assertRaises(ValueError):
            trace.arrivals([dataclasses_replace(_record(100.0, output=3), stream=False, max_new_tokens=512)])

    def test_prewarming_counts_coverage_through_shared_ancestors(self):
        from livetune import trace

        early = trace.Arrival(at=0.0, prompt_tokens=9000, output_tokens=1, shared_tokens=8192, family="deep", temperature=None,
                              ancestors=((256, "a256"), (2048, "a2048")))
        later = trace.Arrival(at=1.0, prompt_tokens=3000, output_tokens=1, shared_tokens=2048, family="a2048", temperature=None,
                              ancestors=((256, "a256"),), cached_tokens=2048)
        ids = [list(range(9000)), list(range(3000))]
        self.assertEqual(loadgen.warm_prefixes([early, later], ids), [])  # the early request explains the later hit


class AbortTimingAndPrewarmTest(unittest.TestCase):
    def test_a_launched_zero_token_abort_keeps_its_arrival_and_duration(self):
        from livetune import trace

        aborted = dataclasses_replace(_record(110.0, output=0, ttft_s=None, decode_s=None), finish="abort", launched=True, server_s=6.0)
        schedule = sorted(trace.arrivals([_record(100.0, ttft_s=0.5, decode_s=2.5), aborted]), key=lambda a: a.at)
        self.assertEqual([(a.at, a.seconds) for a in schedule], [(0.0, 3.0), (7.0, 6.0)])  # arrived at 104, not 110

    def test_a_rejected_prewarm_fails_the_measurement(self):
        import asyncio

        class Response:
            def __init__(self, status):
                self.status = status

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def read(self):
                return b""

        statuses = iter([503, 503])
        session = types.SimpleNamespace(post=lambda url, json: Response(next(statuses)))
        arrival = types.SimpleNamespace(at=0.0, cached_tokens=10, family=None, ancestors=(), shared_tokens=0)
        with self.assertRaises(RuntimeError):
            asyncio.run(loadgen._prewarm(session, "http://x", [arrival], [list(range(20))]))


class WindowStartTest(unittest.TestCase):
    def test_a_window_holds_requests_that_started_in_it(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            writer = trace.Writer(tmp)
            writer.write(_record(1000.0, ttft_s=1.0, decode_s=1.0))  # started at 998
            writer.write(dataclasses_replace(_record(1000.0), server_s=1800.0))  # a long one that started at -800
            writer.close()
            self.assertEqual(len(list(trace.read([tmp], since=900.0))), 1)


class MinTokensAndVersionTest(unittest.TestCase):
    def test_min_new_tokens_is_replayed(self):
        import asyncio

        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def json(self):
                return {"meta_info": {"completion_tokens": 8}}

        bodies = []
        session = types.SimpleNamespace(post=lambda url, json: bodies.append(json) or Response())
        asyncio.run(loadgen._one(session, "http://x", [1], 8, loadgen.RequestRecord(0.0), stream=False, sampling={"min_new_tokens": 8.0}))
        self.assertEqual(bodies[0]["sampling_params"]["min_new_tokens"], 8)

    def test_the_controller_never_reasserts_a_stale_policy_version(self):
        ctl = control.Controller(_policy(), smoothing=1.0, applied={"max_running_requests": 8})
        ctl.step(_window(2), 0)
        self.assertNotIn("policy_version", ctl.applied)


class WorkloadShapeTest(unittest.TestCase):
    def test_a_different_workload_at_the_same_load_is_inconclusive(self):
        from livetune import rollout

        chat = [_window(40, tps=100)] * 12
        agentic = [metrics.Window(10, 40, 0, 5, 5 * 24000, 1000, 5 * 19200, 0.01, 1.0)] * 12
        verdict = rollout.judge(agentic, chat, Slo(80, 10))
        self.assertEqual(verdict.decision, "inconclusive")
        self.assertIn("workloads differ", verdict.reason)

    def test_replay_windows_close_before_now(self):
        from livetune import trace

        with tempfile.TemporaryDirectory() as tmp:
            writer = trace.Writer(tmp)
            for t in (100.0, 200.0, 300.0):
                writer.write(_record(t, ttft_s=0.0, decode_s=0.0))
            writer.close()
            self.assertEqual([r.t for r in trace.read([tmp], since=150.0, until=250.0)], [200.0])


class DataParallelCandidateTest(unittest.TestCase):
    def test_every_scheduler_must_run_the_candidate(self):
        policy = Policy(Slo(80, 10), (Rule("trace", 25, 2500, {"max_running_requests": 16}), Rule("unmeasured", math.inf, math.inf, {"max_running_requests": 64})))
        good = {**STARTUP, "max_running_requests": 16, "policy_version": policy.version}
        mixed = types.SimpleNamespace(livetune_states=lambda: [{"settings": good}, {"settings": dict(STARTUP)}])
        self.assertFalse(cli._runs_candidate(mixed, policy))

    def test_a_failed_first_scrape_loses_a_window_not_the_watch(self):
        calls = {"n": 0}

        def scrape():
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("metrics down")
            return metrics.parse("", float(calls["n"]))

        server = types.SimpleNamespace(scrape=scrape)
        saved = cli.time.sleep
        cli.time.sleep = lambda s: None
        try:
            windows = cli._watch([server], seconds=0.0001, interval=0)
        finally:
            cli.time.sleep = saved
        self.assertEqual(len(windows), 1)


class SeedAndGuardFailureTest(unittest.TestCase):
    def test_replay_sends_only_the_seed_production_sent(self):
        import asyncio

        class Response:
            status = 200

            async def __aenter__(self):
                return self

            async def __aexit__(self, *exc):
                return False

            async def json(self):
                return {"meta_info": {"completion_tokens": 1}}

        bodies = []
        session = types.SimpleNamespace(post=lambda url, json: bodies.append(json) or Response())
        for sampling in ({}, {"sampling_seed": 42.0}):
            asyncio.run(loadgen._one(session, "http://x", [1], 1, loadgen.RequestRecord(0.0), stream=False, sampling=sampling))
        self.assertNotIn("sampling_seed", bodies[0]["sampling_params"])
        self.assertEqual(bodies[1]["sampling_params"]["sampling_seed"], 42)

    def test_a_guard_that_cannot_read_a_replica_restores_the_previous_policy(self):
        import argparse

        saved = (cli._watch, cli._wait_applied, cli._runs_candidate)
        cli._watch = lambda servers, seconds, interval: [[_window(40, tps=100)] * 12 for _ in servers]
        cli._wait_applied = lambda server, policy, timeout, interval: True

        def unreadable(server, policy):
            raise OSError("server_info timed out")

        cli._runs_candidate = unreadable
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "policy.json")
            path.write_text("previous")
            args = argparse.Namespace(fleet="", policy_out=str(path), slo_tps=80, slo_ttft=10, guard_seconds=60, interval=5, stage_apply_s=0)
            try:
                verdict = cli.promote(args, types.SimpleNamespace(url="prod", fingerprint=lambda: {}), _policy())
            finally:
                cli._watch, cli._wait_applied, cli._runs_candidate = saved
            self.assertEqual((verdict.decision, path.read_text()), ("revert", "previous"))


class SeedPrecisionTest(unittest.TestCase):
    def test_large_integer_seeds_survive_recording(self):
        from livetune import sglang_plugin, trace

        class FINISH_LENGTH:
            pass

        times = types.SimpleNamespace(scheduler_recv_time=0.0, wait_queue_entry_time=1.0, prefill_finished_time=1.5, completion_time=2.0,
                                      queue_duration_s=0.0, forward_entry_time=1.1)
        params = types.SimpleNamespace(temperature=0.7, max_new_tokens=8, sampling_seed=9007199254740993, top_p=0.9)
        req = types.SimpleNamespace(rid="r", time_stats=times, origin_input_ids=list(range(10)), output_ids=[1] * 8, cached_tokens=0,
                                    finished_reason=FINISH_LENGTH(), sampling_params=params, finished=lambda: True)
        record = sglang_plugin.Telemetry(None).record(req, 100.0, 2.0)
        self.assertEqual(trace.Record.from_json(record.to_json()).sampling["sampling_seed"], 9007199254740993)
        self.assertEqual(record.sampling["top_p"], 0.9)


class ServerSideSloTest(unittest.TestCase):
    def test_non_streaming_traces_are_judged_on_the_servers_histograms(self):
        text = "\n".join([
            'sglang:request_time_per_output_token_seconds_bucket{le="0.01"} %d', 'sglang:request_time_per_output_token_seconds_bucket{le="+Inf"} %d',
            'sglang:request_time_per_output_token_seconds_count %d',
            'sglang:time_to_first_token_seconds_bucket{le="1.0"} %d', 'sglang:time_to_first_token_seconds_bucket{le="+Inf"} %d',
            'sglang:time_to_first_token_seconds_count %d'])
        scrapes = iter([metrics.parse(text % (0, 0, 0, 0, 0, 0), 0.0), metrics.parse(text % (10, 10, 10, 10, 10, 10), 60.0)])
        server = types.SimpleNamespace(url="http://x", livetune_state=lambda: {"startup": {"max_running_requests": 64}}, fingerprint=lambda: {},
                                       apply=lambda s: None, flush_cache=lambda: None, scrape=lambda: next(scrapes))
        arrivals = [types.SimpleNamespace(at=0.0, prompt_tokens=2000, output_tokens=8, shared_tokens=0, family=None, temperature=0.7,
                                          seconds=1.0, cached_tokens=0, priority=None, stream=False)]
        saved = loadgen.run_arrivals

        async def fake(url, schedule, prompts, name="trace", warm=True):
            result = loadgen.PhaseResult(loadgen.Phase(0, 2000, 8, 1.0))
            result.requests = [loadgen.RequestRecord(0.0, tokens=8)]
            return result

        loadgen.run_arrivals = fake
        trials = []
        try:
            cli.tune_policy(server, Slo(50, 5), loadgen.PromptSource(list(range(5000))), {}, None, arrivals, 0, 0, trials.append)
        finally:
            loadgen.run_arrivals = saved
        summary = trials[0]["summary"]
        self.assertEqual(summary["slo_from"], "server")
        self.assertIsNotNone(summary["tps_per_user_p50"])
        self.assertIsNotNone(summary["ttft_p90"])

