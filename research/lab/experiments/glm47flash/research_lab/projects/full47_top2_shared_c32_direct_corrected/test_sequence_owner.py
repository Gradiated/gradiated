import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).with_name("sequence_owner.py")
SPEC = importlib.util.spec_from_file_location("corrected_owner", PATH)
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)
PREDECESSOR_SUMMARY = PATH.parents[1] / "full47_top2_shared_c32_direct" / "artifacts" / "l40s_top2_shared_c32_20260716_r1" / "top4_shared_c32_pre" / "summary.json"


def allocation(rate):
    return {
        "semantic": {"pass": True},
        "quality": {"pass": False, "absolute_bf16_quality_failure_carried_forward": True},
        "performance": {"profiles": [{
            "concurrency": 32, "output_tokens_per_second_conservative": rate,
            "success_fraction": 1.0, "exact_geometry_pass": True, "wall_seconds": 106.0,
            "requests": 64, "rows": [{}] * 64,
            "prefix_cache_disabled": True, "prefix_cache_zero_delta": True,
        }]},
    }


class CorrectedOwnerTests(unittest.TestCase):
    def test_dual_gate_requires_stable_controls_and_three_percent_uplift(self):
        self.assertTrue(OWNER.top2_gate(614.0, 633.0, 615.0))
        self.assertFalse(OWNER.top2_gate(614.0, 632.0, 615.0))
        self.assertFalse(OWNER.top2_gate(600.0, 650.0, 640.0))
        self.assertFalse(OWNER.top2_gate(614.0, None, 615.0))

    def test_real_predecessor_summary_uses_conservative_rate_and_deferred_quality_only(self):
        self.assertTrue(PREDECESSOR_SUMMARY.is_file())
        self.assertEqual(OWNER.throughput(PREDECESSOR_SUMMARY), 614.9256260882358)
        self.assertTrue(OWNER.background_valid(PREDECESSOR_SUMMARY))
        value = json.loads(PREDECESSOR_SUMMARY.read_text())
        profile = value["allocation_result"]["performance"]["profiles"][0]
        profile["prefix_cache_zero_delta"] = False
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "summary.json"; changed.write_text(json.dumps(value))
            self.assertFalse(OWNER.background_valid(changed))

    def test_owner_has_ordered_post_control_gate_and_false_cleanup_before_top3(self):
        source = PATH.read_text()
        self.assertLess(source.index('("top2_shared_c32", "top2")'), source.index('("top4_shared_c32_post", "top4")'))
        self.assertLess(source.index("if not top2_gate"), source.index('recovery_args(out / "top3_shared_c32"'))
        false_branch = source[source.index("if not top2_gate"):source.index('recovery_args(out / "top3_shared_c32"')]
        self.assertIn("cleanup(instance_id, name)", false_branch)
        self.assertIn("background_arm_envelope_seconds = 300", source)

    def test_actual_owner_runs_top4_top2_top4_then_top3_only_on_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / "model"; model.mkdir()
            (model / "config.json").write_text(json.dumps({"num_experts_per_tok": 4, "n_shared_experts": 1}))
            calls = []
            def summary(directory, rate, retained=True):
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "summary.json").write_text(json.dumps({"instance_id": "instance-1", "retained_for_next_experiment": retained, "allocation_result": allocation(rate)}))
            def smoke_run(out, *_args, **_kwargs):
                calls.append("top4_shared_c32_pre"); summary(out, 614.0); return 1
            def recover_run(args):
                calls.append(args.output_dir.name); summary(args.output_dir, {"top2_shared_c32": 633.0, "top4_shared_c32_post": 615.0, "top3_shared_c32": 620.0}[args.output_dir.name], args.keep_instance_after_result); return 0
            with patch.object(OWNER, "PROJECT", root), patch.object(OWNER, "MODEL", model), patch.object(OWNER.smoke, "run", smoke_run), patch.object(OWNER.recover, "run", recover_run), patch.dict(os.environ, {"INVOCATION_ID": "x", "SYSTEMD_EXEC_PID": str(os.getpid())}, clear=False):
                self.assertEqual(OWNER.main(), 0)
            self.assertEqual(calls, ["top4_shared_c32_pre", "top2_shared_c32", "top4_shared_c32_post", "top3_shared_c32"])

    def test_actual_owner_cleans_immediately_and_skips_top3_when_gate_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / "model"; model.mkdir()
            (model / "config.json").write_text(json.dumps({"num_experts_per_tok": 4, "n_shared_experts": 1}))
            calls, cleaned = [], []
            def summary(directory, rate):
                directory.mkdir(parents=True, exist_ok=True)
                (directory / "summary.json").write_text(json.dumps({"instance_id": "instance-1", "retained_for_next_experiment": True, "allocation_result": allocation(rate)}))
            def smoke_run(out, *_args, **_kwargs): calls.append("pre"); summary(out, 614.0); return 1
            def recover_run(args): calls.append(args.output_dir.name); summary(args.output_dir, 615.0 if args.output_dir.name == "top2_shared_c32" else 614.0); return 0
            with patch.object(OWNER, "PROJECT", root), patch.object(OWNER, "MODEL", model), patch.object(OWNER.smoke, "run", smoke_run), patch.object(OWNER.recover, "run", recover_run), patch.object(OWNER, "cleanup", lambda *args: cleaned.append(args) or True), patch.dict(os.environ, {"INVOCATION_ID": "x", "SYSTEMD_EXEC_PID": str(os.getpid())}, clear=False):
                self.assertEqual(OWNER.main(), 0)
            self.assertEqual(calls, ["pre", "top2_shared_c32", "top4_shared_c32_post"])
            self.assertEqual(cleaned, [("instance-1", "glm47-top2-shared-c32-20260716-r2")])

    def test_top3_deadline_reserve_cleans_without_launching_top3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / "model"; model.mkdir()
            (model / "config.json").write_text(json.dumps({"num_experts_per_tok": 4, "n_shared_experts": 1}))
            calls, cleaned = [], []
            def summary(directory, rate):
                directory.mkdir(parents=True, exist_ok=True); (directory / "summary.json").write_text(json.dumps({"instance_id": "instance-1", "retained_for_next_experiment": True, "allocation_result": allocation(rate)}))
            def smoke_run(out, *_args, **_kwargs): calls.append("pre"); summary(out, 614.0); return 1
            def recover_run(args): calls.append(args.output_dir.name); summary(args.output_dir, 633.0 if args.output_dir.name == "top2_shared_c32" else 615.0); return 0
            clock = iter((1000.0, 2900.0))
            with patch.object(OWNER, "PROJECT", root), patch.object(OWNER, "MODEL", model), patch.object(OWNER.smoke, "run", smoke_run), patch.object(OWNER.recover, "run", recover_run), patch.object(OWNER, "cleanup", lambda *args: cleaned.append(args) or True), patch.object(OWNER.time, "time", side_effect=lambda: next(clock)), patch.dict(os.environ, {"INVOCATION_ID": "x", "SYSTEMD_EXEC_PID": str(os.getpid())}, clear=False):
                self.assertEqual(OWNER.main(), 0)
            self.assertEqual(calls, ["pre", "top2_shared_c32", "top4_shared_c32_post"])
            self.assertEqual(len(cleaned), 1)
