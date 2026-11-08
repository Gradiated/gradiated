import hashlib
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
                    stop=lambda: len(scraped) > 3, clock=lambda: 0.0, sleep=lambda s: None)
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
        self.assertEqual((record.tokens, record.decode_tps), (10, 3.0))  # 6 tokens over 2 s, not 9
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
        runtime = types.ModuleType("sglang.srt.runtime_context")
        runtime.get_parallel = lambda: parallel
        self._saved = {name: sys.modules.get(name) for name in ("sglang", "sglang.srt", "sglang.srt.runtime_context")}
        sys.modules.update({"sglang": types.ModuleType("sglang"), "sglang.srt": types.ModuleType("sglang.srt"), "sglang.srt.runtime_context": runtime})
        self.model = types.SimpleNamespace(value=1)
        runner = types.SimpleNamespace(model=self.model)
        self.scheduler = types.SimpleNamespace(page_size=256, max_running_requests=64, chunked_prefill_size=8192,
                                               max_prefill_tokens=8192, tp_rank=0, tp_size=4, tp_worker=types.SimpleNamespace(model_runner=runner))
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
