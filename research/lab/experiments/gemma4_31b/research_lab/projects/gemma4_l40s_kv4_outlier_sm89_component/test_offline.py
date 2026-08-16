from __future__ import annotations

import ast
import json
from pathlib import Path
import unittest

import offline_audit


PROJECT = Path(__file__).resolve().parent


class OfflineContractTest(unittest.TestCase):
    def test_packet_is_project_local_and_hash_complete(self):
        manifest = offline_audit.validate_manifest()
        self.assertEqual(
            set(manifest["files"]),
            {
                "local_kv4_outlier_bindings.cpp",
                "local_kv4_outlier_cuda.cu",
                "run_sm89_component.py",
                "runtime_source/decode_attention.py",
                "runtime_source/memory_pool.py",
                "runtime_source/triton_backend.py",
                "sglang_local_kv4_outlier.py",
            },
        )

    def test_runner_has_fixed_geometry_and_real_consumers(self):
        source = (PROJECT / "packet/run_sm89_component.py").read_text()
        tree = ast.parse(source)
        assignments = {
            node.targets[0].id: ast.literal_eval(node.value)
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id
            in {
                "BATCH",
                "QUERY_HEADS",
                "KV_HEADS",
                "HEAD_DIM",
                "WINDOW",
                "PAGE_SIZE",
                "LOCAL_LAYERS",
                "DECODE_STEPS",
                "WARMUPS",
                "REPEATS",
            }
        }
        self.assertEqual(
            assignments,
            {
                "BATCH": 32,
                "QUERY_HEADS": 32,
                "KV_HEADS": 16,
                "HEAD_DIM": 256,
                "WINDOW": 1024,
                "PAGE_SIZE": 1,
                "LOCAL_LAYERS": 50,
                "DECODE_STEPS": 358,
                "WARMUPS": 5,
                "REPEATS": 31,
            },
        )
        for token in (
            "baseline_pool.set_kv_buffer",
            "decode_attention_fwd(",
            "extension.pack(",
            "extension.paged_attention(",
            "make_reference(",
        ):
            self.assertIn(token, source)
        self.assertNotIn("argparse.ArgumentParser().add_argument(\"--window\"", source)

    def test_physical_bound_charges_both_producer_and_consumer(self):
        value = offline_audit.physical_bounds()
        step = value["one_c32_local_layer_decode_step_bytes"]
        self.assertEqual(step["e5m2_complete"], 269_221_888)
        self.assertEqual(step["kv4_outlier_complete_unique_lower"], 151_666_688)
        self.assertEqual(step["kv4_outlier_complete_issued_upper"], 302_661_632)
        locked = value["locked_50_layers_358_steps_c32_batch_bytes"]
        self.assertEqual(locked["e5m2_complete"], 4_819_071_795_200)
        self.assertEqual(
            locked["kv4_outlier_complete_unique_lower"], 2_714_833_715_200
        )

    def test_owner_has_separate_repair_and_terminal_release_paths(self):
        source = (PROJECT / "l40s_component_owner.py").read_text()
        tree = ast.parse(source)
        functions = {
            node.name for node in tree.body if isinstance(node, ast.FunctionDef)
        }
        self.assertIn("release_scientific", functions)
        self.assertIn("release_terminal_boundary", functions)
        self.assertIn("repair_request", functions)
        self.assertIn("validate_patch_request", functions)
        self.assertIn("consumer_only_from_bound_producer_snapshot", source)
        self.assertIn("--expected-claimed-at", source)
        self.assertNotIn("sglang.launch_server", source)
        self.assertNotIn("--checkpoint", source)

    def test_ready_is_positive_offline_readiness_not_science(self):
        value = offline_audit.build_ready()
        self.assertTrue(value["pass"])
        self.assertEqual(value["decision"], "positive")
        self.assertEqual(
            value["scientific_result"], "unmeasured_target_gpu_execution_required"
        )
        self.assertFalse(value["scope"]["cuda_invoked"])
        self.assertFalse(value["scope"]["gpu_pool_claimed"])
        self.assertIn(
            "--deadline-seconds 1620",
            value["owner"]["exact_later_command"],
        )
        self.assertEqual(
            value["locked_request_measured_bound_contract"][
                "dependent_synchronization_credit"
            ],
            0.0,
        )

    def test_manifest_json_round_trip(self):
        value = json.loads(
            (PROJECT / "packet/PACKET_MANIFEST.json").read_text()
        )
        self.assertEqual(value["fixed_contract"]["repeats"], 31)
        self.assertEqual(value["runtime_commit"], offline_audit.build_ready()["fixed_contract"]["runtime_commit"])


if __name__ == "__main__":
    unittest.main()
