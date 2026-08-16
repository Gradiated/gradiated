from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import unittest

import numpy as np

import streaming_accuracy_analysis as analysis


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "packed_m384_streaming_cluster.cu"
RUNNER = ROOT / "streaming_accuracy_component_runner.py"
REPORT = (
    ROOT
    / "artifacts"
    / "streaming-accuracy"
    / "OFFLINE_STREAMING_ACCURACY_ANALYSIS.json"
)
READY = ROOT / "PACKED_M384_STREAMING_ACCURACY_READY.json"
STATUS = ROOT / "STATUS.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StreamingAccuracyTest(unittest.TestCase):
    def test_streaming_reduction_matches_full_fp32(self) -> None:
        rng = np.random.default_rng(90210)
        score = rng.normal(size=(2, 12, 133)).astype(np.float32)
        value = rng.normal(size=(133, 64)).astype(np.float32)
        score[:, :, -7:] = -np.inf
        full = analysis.stable_output(score, value)
        streaming = analysis.streaming_output(score, value)
        np.testing.assert_allclose(
            streaming, full, rtol=3e-6, atol=3e-6
        )

    def test_source_contains_exact_cluster_consumer(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        for required in (
            "cg::this_cluster()",
            "map_shared_rank",
            "cudaLaunchAttributeClusterDimension",
            "launch_exact<256, 16, 1024, 1, true>",
            "launch_exact<512, 4, 4214, 2, false>",
            "accumulator[kRows]",
            "output[output_offset]",
        ):
            self.assertIn(required, source)
        for forbidden in (
            "packed_m384_attention_v2",
            "partial_numerator",
            "score_workspace",
            "cudaMalloc",
        ):
            self.assertNotIn(forbidden, source)

    def test_runner_is_lifecycle_pure_and_new_candidate_only(self) -> None:
        tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
        imported = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        }
        imported.update(
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module is not None
        )
        self.assertFalse(
            imported
            & {
                "paramiko",
                "grad_research.gpu_pool",
                "nebius",
            }
        )
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("high_precision_reference", source)
        self.assertIn("candidate_graph_replay", source)
        self.assertIn("cuobjdump", source)

    def test_complete_report_passes_every_offline_gate(self) -> None:
        report = json.loads(REPORT.read_text(encoding="utf-8"))
        self.assertEqual(report["candidate"]["sha256"], digest(SOURCE))
        self.assertTrue(report["ready_gates_pass"])
        self.assertTrue(report["correctness"]["complete_exact_geometry"])
        self.assertTrue(report["correctness"]["ten_x_v2_error_gate"])
        self.assertTrue(
            report["physical"]["both_forbidden_hbm_workspaces_eliminated"]
        )
        self.assertTrue(report["physical"]["global_gate_pass"])
        self.assertTrue(
            report["physical"]["weighted_50_local_10_global"]["pass"]
        )
        cases = {
            case["name"]: case for case in report["correctness"]["cases"]
        }
        self.assertEqual(cases["local"]["candidate_vs_fp64"]["elements"], 3145728)
        self.assertEqual(cases["global"]["candidate_vs_fp64"]["elements"], 6291456)

    def test_ready_and_status_hash_bind_the_packet(self) -> None:
        ready = json.loads(READY.read_text(encoding="utf-8"))
        status = json.loads(STATUS.read_text(encoding="utf-8"))
        self.assertEqual(ready["implementation"]["source_sha256"], digest(SOURCE))
        self.assertEqual(ready["runner"]["sha256"], digest(RUNNER))
        self.assertEqual(
            ready["offline_evidence"]["sha256"], digest(REPORT)
        )
        self.assertEqual(
            status["streaming_accuracy_ready"]["sha256"], digest(READY)
        )


if __name__ == "__main__":
    unittest.main()
