import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

PATH = Path(__file__).with_name("sequence_owner.py")
SPEC = importlib.util.spec_from_file_location("top3_c36_owner", PATH)
OWNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OWNER)


def allocation(rows):
    return {"semantic": {"pass": True}, "quality": {"pass": False, "absolute_bf16_quality_failure_carried_forward": True}, "performance": {"profiles": rows}}


def row(concurrency, rate):
    return {"concurrency": concurrency, "output_tokens_per_second_conservative": rate, "success_fraction": 1.0, "exact_geometry_pass": True, "wall_seconds": 100.0, "requests": 64, "rows": [{}] * 64, "prefix_cache_disabled": True, "prefix_cache_zero_delta": True}


class Top3C36OwnerTests(unittest.TestCase):
    def test_c36_gate_requires_fresh_control_rate_memory_and_complete_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "summary.json"
            path.write_text(json.dumps({"retained_for_next_experiment": True, "allocation_result": allocation([row(32, 644.4), row(36, 664.5)])}))
            with patch.object(OWNER, "peak_memory_mib", return_value=42000):
                self.assertTrue(OWNER.c36_pass(path))
                self.assertTrue(OWNER.c40_admitted(path))
            with patch.object(OWNER, "peak_memory_mib", return_value=45000):
                self.assertFalse(OWNER.c40_admitted(path))

    def test_owner_sequences_primary_before_conditional_and_cleans_false_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); model = root / "model"; model.mkdir(); (model / "config.json").write_text(json.dumps({"num_experts_per_tok": 4, "n_shared_experts": 1}))
            calls, cleaned = [], []
            def write_summary(directory, rows, retained=True):
                directory.mkdir(parents=True, exist_ok=True); (directory / "summary.json").write_text(json.dumps({"instance_id": "instance-1", "retained_for_next_experiment": retained, "artifact_sha256": "x", "allocation_result": allocation(rows)}))
            def smoke_run(out, *_args, **_kwargs): calls.append(out.name); write_summary(out, [row(32, 644.4)]); return 0
            def recover_run(args): calls.append(args.output_dir.name); write_summary(args.output_dir, [row(32, 644.4), row(36, 664.5)] if args.max_num_seqs == 36 else [row(40, 684.0)], args.keep_instance_after_result); return 0
            with patch.object(OWNER, "PROJECT", root), patch.object(OWNER, "MODEL", model), patch.object(OWNER.smoke, "run", smoke_run), patch.object(OWNER.recover, "run", recover_run), patch.object(OWNER, "peak_memory_mib", return_value=42000), patch.object(OWNER, "cleanup", lambda *args: cleaned.append(args) or True), patch.object(OWNER.time, "time", return_value=1000.0), patch.dict(os.environ, {"INVOCATION_ID": "x", "SYSTEMD_EXEC_PID": str(os.getpid())}, clear=False):
                self.assertEqual(OWNER.main(), 0)
            self.assertEqual(calls, ["bootstrap_maxseq36", "top3_shared_c32_c36", "top3_shared_c40"])
            self.assertEqual(cleaned, [])
