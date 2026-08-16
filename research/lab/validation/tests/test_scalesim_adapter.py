import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validation.scalesim_adapter.normalize import build_report
from validation.scalesim_adapter.run import (
    render_config,
    render_layout,
    render_topology,
)


class ScaleSimAdapterTests(unittest.TestCase):
    def test_renderer_exports_exact_deterministic_scale_sim_inputs(self) -> None:
        workload = {
            "id": "qwen",
            "dimensions": {"batch": 1, "m": 1, "n": 1024, "k": 2048},
        }
        architecture = {
            "id": "ws32",
            "array_height": 32,
            "array_width": 32,
            "ifmap_sram_kb": 64,
            "filter_sram_kb": 64,
            "ofmap_sram_kb": 64,
            "dataflow": "ws",
            "interface_bandwidth": "CALC",
        }

        self.assertEqual(
            render_topology(workload),
            "Layer Name, M, N, K,\nqwen, 1, 1024, 2048,\n",
        )
        self.assertIn("run_name = qwen__ws32", render_config("qwen", architecture))
        self.assertIn("ArrayHeight = 32", render_config("qwen", architecture))
        self.assertIn("Dataflow = ws", render_config("qwen", architecture))
        self.assertIn("qwen,1,1,1,1,1,1", render_layout("qwen"))

    def test_normalizes_exact_native_result_and_keeps_unsupported_claims_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._write_request(root)
            raw = self._write_raw_case(root)

            report = build_report(request, raw)

        self.assertEqual(report["status"], "native_sweep_succeeded")
        self.assertEqual(report["tool_identity"]["revision"], "stable-revision")
        self.assertEqual(len(report["cases"]), 1)
        case = report["cases"][0]
        self.assertEqual(case["logical_accounting"]["multiply_accumulates"], 2_097_152)
        self.assertEqual(case["logical_accounting"]["flops"], 4_194_304)
        self.assertEqual(case["logical_accounting"]["total_tensor_bytes"], 4_200_448)
        self.assertEqual(
            case["native_result"]["total_cycles_including_prefetch"], 70_000
        )
        self.assertEqual(
            case["native_result"]["dram_accesses"]["filter_reads"], 2_097_152
        )
        self.assertTrue(report["claims"]["exact_topology_claim_permitted"])
        self.assertTrue(report["claims"]["native_cycle_count_claim_permitted"])
        self.assertTrue(report["claims"]["same_oracle_cycle_ratio_claim_permitted"])
        self.assertFalse(report["claims"]["bf16_arithmetic_claim_permitted"])
        self.assertFalse(report["claims"]["gpu_latency_claim_permitted"])
        self.assertFalse(report["claims"]["energy_claim_permitted"])
        self.assertFalse(report["claims"]["area_claim_permitted"])
        self.assertFalse(report["claims"]["cost_claim_permitted"])
        self.assertFalse(report["claims"]["whole_model_claim_permitted"])
        self.assertEqual(len(case["raw_artifacts"]), 9)
        self.assertEqual(len(report["content_identity_sha256"]), 64)
        self.assertEqual(
            report["sweep_analysis"]["base_architecture_rankings"]["qwen"], ["ws32"]
        )
        self.assertTrue(
            report["sweep_analysis"][
                "base_architecture_rank_identical_across_workloads"
            ]
        )

    def test_rejects_topology_that_does_not_match_the_declared_gemm(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._write_request(root)
            raw = self._write_raw_case(root)
            topology = raw / "qwen" / "ws32" / "input" / "topology.csv"
            topology.write_text(
                "Layer Name, M, N, K,\nqwen, 1, 1024, 2047,\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(ValueError, "topology dimensions"):
                build_report(request, raw)

    def test_rejects_missing_or_malformed_native_reports(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._write_request(root)
            raw = self._write_raw_case(root)
            compute = (
                raw / "qwen" / "ws32" / "output" / "qwen__ws32" / "COMPUTE_REPORT.csv"
            )
            compute.write_text("wrong,header\n0,1\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "COMPUTE_REPORT.csv header"):
                build_report(request, raw)

    def test_rejects_failed_process_even_when_csv_files_exist(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = self._write_request(root)
            raw = self._write_raw_case(root)
            capture = raw / "qwen" / "ws32" / "process.json"
            document = json.loads(capture.read_text(encoding="utf-8"))
            document["exit_code"] = 1
            capture.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "process did not succeed"):
                build_report(request, raw)

    @staticmethod
    def _write_request(root: Path) -> Path:
        source = root / "source.json"
        source.write_text(
            json.dumps(
                {
                    "content_id": "source-content-id",
                    "problem_dimensions": {"batch": 1, "m": 1, "n": 1024, "k": 2048},
                    "tensor_types": {
                        "input": "bf16",
                        "weight": "bf16",
                        "output": "bf16",
                        "accumulator": "fp32",
                    },
                    "accounting": {
                        "multiply_accumulates": 2_097_152,
                        "flops": 4_194_304,
                        "input_elements": 2_048,
                        "weight_elements": 2_097_152,
                        "output_elements": 1_024,
                        "input_bytes": 4_096,
                        "weight_bytes": 4_194_304,
                        "output_bytes": 2_048,
                    },
                }
            )
            + "\n",
            encoding="utf-8",
        )
        source_sha256 = hashlib.sha256(source.read_bytes()).hexdigest()
        path = root / "request.json"
        path.write_text(
            json.dumps(
                {
                    "schema_version": "inference-foundry.scalesim-v3-smoke-request.v1",
                    "request_id": "test",
                    "tool": {
                        "name": "SCALE-Sim",
                        "version": "3.0.0",
                        "repository": "https://github.com/scalesim-project/SCALE-Sim",
                        "revision": "stable-revision",
                        "release_tag": "v3.0.0",
                        "license": "MIT",
                        "license_sha256": "license-sha",
                    },
                    "current_main_probe": {"revision": "main-revision"},
                    "workloads": [
                        {
                            "id": "qwen",
                            "model_id": "Qwen/Qwen3-0.6B",
                            "operator": "attention.o_proj",
                            "dimensions": {"batch": 1, "m": 1, "n": 1024, "k": 2048},
                            "tensor_types": {
                                "input": "bf16",
                                "weight": "bf16",
                                "output": "bf16",
                                "accumulator": "fp32",
                            },
                            "source_contract": {
                                "kind": "timeloop_problem_export",
                                "path": "source.json",
                                "sha256": source_sha256,
                                "content_id": "source-content-id",
                                "basis": "test",
                            },
                            "semantic_limit": "SCALE-Sim models untyped dense elements.",
                        }
                    ],
                    "architectures": [
                        {
                            "id": "ws32",
                            "array_height": 32,
                            "array_width": 32,
                            "ifmap_sram_kb": 64,
                            "filter_sram_kb": 64,
                            "ofmap_sram_kb": 64,
                            "dataflow": "ws",
                            "interface_bandwidth": "CALC",
                            "role": "base_array_dataflow_sweep",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return path

    @staticmethod
    def _write_raw_case(root: Path) -> Path:
        raw = root / "raw"
        case = raw / "qwen" / "ws32"
        inputs = case / "input"
        outputs = case / "output" / "qwen__ws32"
        inputs.mkdir(parents=True)
        outputs.mkdir(parents=True)
        (raw / "probe.json").write_text(
            json.dumps(
                {
                    "schema_version": "inference-foundry.scalesim-v3-probe.v1",
                    "revision": "stable-revision",
                    "version": "3.0.0",
                    "license_sha256": "license-sha",
                    "python": "3.12.12",
                    "platform": "test",
                    "scale_sim_source_sha256": "source-file-sha",
                }
            ),
            encoding="utf-8",
        )
        (inputs / "topology.csv").write_text(
            "Layer Name, M, N, K,\nqwen, 1, 1024, 2048,\n", encoding="utf-8"
        )
        (inputs / "layout.csv").write_text(
            "Layer name, placeholder,\nqwen, 1,\n", encoding="utf-8"
        )
        (inputs / "config.cfg").write_text(
            "[general]\n"
            "run_name = qwen__ws32\n"
            "[architecture_presets]\n"
            "ArrayHeight = 32\n"
            "ArrayWidth = 32\n"
            "IfmapSramSzkB = 64\n"
            "FilterSramSzkB = 64\n"
            "OfmapSramSzkB = 64\n"
            "Dataflow = ws\n"
            "[layout]\n"
            "IfmapCustomLayout = False\n"
            "FilterCustomLayout = False\n"
            "[sparsity]\n"
            "SparsitySupport = false\n"
            "[run_presets]\n"
            "InterfaceBandwidth = CALC\n"
            "UseRamulatorTrace = False\n",
            encoding="utf-8",
        )
        (case / "stdout.txt").write_text("complete\n", encoding="utf-8")
        (case / "stderr.txt").write_text("", encoding="utf-8")
        (case / "process.json").write_text(
            json.dumps(
                {
                    "schema_version": "inference-foundry.scalesim-v3-process.v1",
                    "status": "succeeded",
                    "exit_code": 0,
                    "command": ["python", "driver"],
                }
            ),
            encoding="utf-8",
        )
        (outputs / "COMPUTE_REPORT.csv").write_text(
            "LayerID, Total Cycles (incl. prefetch), Total Cycles, Stall Cycles, Overall Util %, Mapping Efficiency %, Compute Util %,\n"
            "0, 70000, 66000, 0, 3.0, 100.0, 3.1,\n",
            encoding="utf-8",
        )
        (outputs / "BANDWIDTH_REPORT.csv").write_text(
            "LayerID, Avg IFMAP SRAM BW, Avg FILTER SRAM BW, Avg OFMAP SRAM BW, Avg IFMAP DRAM BW, Avg FILTER DRAM BW, Avg OFMAP DRAM BW,\n"
            "0, 1, 2, 3, 4, 5, 6,\n",
            encoding="utf-8",
        )
        (outputs / "DETAILED_ACCESS_REPORT.csv").write_text(
            "LayerID, SRAM IFMAP Start Cycle, SRAM IFMAP Stop Cycle, SRAM IFMAP Reads, SRAM Filter Start Cycle, SRAM Filter Stop Cycle, SRAM Filter Reads, SRAM OFMAP Start Cycle, SRAM OFMAP Stop Cycle, SRAM OFMAP Writes, DRAM IFMAP Start Cycle, DRAM IFMAP Stop Cycle, DRAM IFMAP Reads, DRAM Filter Start Cycle, DRAM Filter Stop Cycle, DRAM Filter Reads, DRAM OFMAP Start Cycle, DRAM OFMAP Stop Cycle, DRAM OFMAP Writes,\n"
            "0, 1, 2, 2048, 1, 2, 2097152, 1, 2, 1024, 1, 2, 2048, 1, 2, 2097152, 1, 2, 1024,\n",
            encoding="utf-8",
        )
        return raw


if __name__ == "__main__":
    unittest.main()
