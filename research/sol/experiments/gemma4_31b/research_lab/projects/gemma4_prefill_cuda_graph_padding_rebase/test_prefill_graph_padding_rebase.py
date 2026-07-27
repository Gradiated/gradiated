import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent
MODULE_PATH = PROJECT_ROOT / "run_prefill_graph_padding_rebase.py"
SPEC = importlib.util.spec_from_file_location("prefill_graph_rebase", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class PrefillGraphPaddingRebaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source_root = PROJECT_ROOT / "inputs/official"
        cls.workload_root = PROJECT_ROOT / "inputs/workload"

    def build(self):
        return MODULE.build_terminal(
            project_root=PROJECT_ROOT,
            source_root=self.source_root,
            workload_path=self.workload_root / "WORKLOAD.json",
            launch_path=self.workload_root / "LAUNCH.json",
            terminal_path=self.workload_root / "C32_TERMINAL.json",
            config_path=self.workload_root / "MODEL_CONFIG.json",
            qualified_terminal_path=self.workload_root / "QUALIFIED_TERMINAL.json",
            gpu_prices_path=self.workload_root / "GPU_PRICES.json",
            retrieved_at_utc="2026-07-27T05:00:00Z",
        )

    def test_exact_official_sources_and_ast_consumers(self):
        manifest, checks = MODULE.verify_sources(self.source_root)
        self.assertEqual(len(manifest), len(MODULE.SOURCE_HASHES))
        self.assertTrue(checks["all_passed"])
        buckets = MODULE.capture_buckets(self.source_root, 2048)
        self.assertEqual(buckets[-5:], [1024, 1280, 1536, 1792, 2048])

        runner = MODULE.make_runner(
            self.source_root, [2816, 3072, 8192], MODULE.PADDING_FACTOR
        )
        self.assertFalse(MODULE.run_guard_case(runner, 3208))
        self.assertTrue(
            MODULE.run_guard_case(
                MODULE.make_runner(self.source_root, [8192], MODULE.PADDING_FACTOR),
                4096,
            )
        )

    def test_exact_c32_trace_guard_on_off_is_identical(self):
        result = self.build()
        trace = result["exact_c32_trace"]
        self.assertEqual(trace["compulsory_rows"], 117728)
        self.assertEqual(trace["guard_on_padded_rows"], 32)
        self.assertEqual(trace["guard_off_padded_rows"], 32)
        self.assertEqual(trace["guard_enabled_rows_removed"], 0)
        self.assertEqual(trace["forward_count"], 58)
        self.assertEqual(trace["differing_route_forward_indices"], [])
        self.assertEqual(
            [row["raw_num_tokens"] for row in trace["forwards"]].count(2048), 57
        )
        self.assertEqual(trace["forwards"][-1]["raw_num_tokens"], 992)
        self.assertEqual(trace["forwards"][-1]["capture_bucket"], 1024)

    def test_terminal_is_typed_none_with_complete_zero_bounds(self):
        result = self.build()
        self.assertEqual(
            result["terminal_type"], "typed_none_exact_c32_guard_never_crosses"
        )
        self.assertTrue(result["decision"]["source_complete_consumer_reachable"])
        self.assertFalse(result["decision"]["exact_workload_guard_activated"])
        self.assertEqual(
            result["complete_bounds"][
                "guard_enabled_reduction_interval_seconds_per_request"
            ],
            [0.0, 0.0],
        )
        self.assertEqual(result["h200_consumer"]["type"], "none")

    def test_main_artifact_round_trip(self):
        with tempfile.TemporaryDirectory(dir=PROJECT_ROOT / "artifacts") as temp_dir:
            output = Path(temp_dir) / "terminal.json"
            result = self.build()
            output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
            reloaded = json.loads(output.read_text())
            self.assertEqual(reloaded["exact_c32_trace"]["forward_count"], 58)


if __name__ == "__main__":
    unittest.main()
