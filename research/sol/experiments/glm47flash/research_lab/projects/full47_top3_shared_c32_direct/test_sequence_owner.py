import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).with_name("sequence_owner.py")
SPEC = importlib.util.spec_from_file_location("top3_owner", PATH)
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)
REAL_PRE = PATH.parents[1] / "full47_top2_shared_c32_direct" / "artifacts" / "l40s_top2_shared_c32_20260716_r1" / "top4_shared_c32_pre" / "summary.json"


def result(rate):
    return {"semantic": {"pass": True}, "quality": {"pass": False, "absolute_bf16_quality_failure_carried_forward": True}, "performance": {"profiles": [{"concurrency": 32, "output_tokens_per_second_conservative": rate, "success_fraction": 1.0, "exact_geometry_pass": True, "wall_seconds": 106.0, "requests": 64, "rows": [{}] * 64, "prefix_cache_disabled": True, "prefix_cache_zero_delta": True}]}}


class OwnerTests(unittest.TestCase):
    def test_real_artifact_and_corrected_contract(self):
        self.assertTrue(REAL_PRE.is_file())
        self.assertEqual(OWNER.throughput(REAL_PRE), 614.9256260882358)
        self.assertTrue(OWNER.background_valid(REAL_PRE))
        value = json.loads(REAL_PRE.read_text()); value["allocation_result"]["performance"]["profiles"][0]["prefix_cache_zero_delta"] = False
        with tempfile.TemporaryDirectory() as tmp:
            changed = Path(tmp) / "summary.json"; changed.write_text(json.dumps(value))
            self.assertFalse(OWNER.background_valid(changed))

    def test_gate_requires_bracket_and_three_percent_gain(self):
        self.assertTrue(OWNER.top3_gate(614, 633, 615))
        self.assertFalse(OWNER.top3_gate(614, 632, 615))
        self.assertFalse(OWNER.top3_gate(600, 633, 640))

    def test_actual_order_and_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); model = root / "model"; model.mkdir(); (model / "config.json").write_text(json.dumps({"num_experts_per_tok": 4, "n_shared_experts": 1}))
            calls, cleaned = [], []
            def summary(directory, rate):
                directory.mkdir(parents=True, exist_ok=True); (directory / "summary.json").write_text(json.dumps({"instance_id": "i", "retained_for_next_experiment": True, "allocation_result": result(rate)}))
            def smoke_run(directory, *_args, **_kwargs): calls.append(directory.name); summary(directory, 614); return 0
            def recover_run(args): calls.append(args.output_dir.name); summary(args.output_dir, 633 if args.output_dir.name == "top3_shared_c32" else 615); return 0
            with patch.object(OWNER, "PROJECT", root), patch.object(OWNER, "MODEL", model), patch.object(OWNER.smoke, "run", smoke_run), patch.object(OWNER.recover, "run", recover_run), patch.object(OWNER, "cleanup", lambda *args: cleaned.append(args) or True), patch.dict(os.environ, {"INVOCATION_ID": "x", "SYSTEMD_EXEC_PID": str(os.getpid())}, clear=False):
                self.assertEqual(OWNER.main(), 0)
            self.assertEqual(calls, ["top4_shared_c32_pre", "top3_shared_c32", "top4_shared_c32_post"])
            self.assertEqual(cleaned, [("i", "glm47-top3-shared-c32-20260716-r1")])
