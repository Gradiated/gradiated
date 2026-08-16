import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_kv_dedup_quality.frontier import build_frontier


class KvDedupFrontierTests(unittest.TestCase):
    def test_selects_largest_passing_cache_reduction_and_bounds_speedup(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = [
                self._write(Path(directory), "pass.json", 2.0, True, "pass-id"),
                self._write(Path(directory), "fail.json", 5.0, False, "fail-id"),
            ]

            report = build_frontier(paths)

        self.assertEqual(
            report["summary"]["maximum_passing_cache_reduction_percent"], 2.0
        )
        self.assertEqual(
            report["summary"]["maximum_passing_source_content_id"], "pass-id"
        )
        self.assertEqual(
            report["summary"]["first_failing_cache_reduction_percent"], 5.0
        )
        self.assertAlmostEqual(
            report["summary"]["ideal_cache_only_decode_speedup_upper_bound"],
            1.0 / 0.98,
        )
        self.assertFalse(report["claims"]["runtime_cost_reduction_claim_permitted"])

    def test_rejects_mixed_corpora(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = self._write(Path(directory), "one.json", 1.0, True, "one")
            second = self._write(Path(directory), "two.json", 2.0, True, "two")
            document = json.loads(second.read_text(encoding="utf-8"))
            document["corpus"]["generated_corpus_sha256"] = "other-corpus"
            second.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "corpus"):
                build_frontier([first, second])

    @staticmethod
    def _write(
        directory: Path,
        name: str,
        reduction: float,
        passed: bool,
        content_id: str,
    ) -> Path:
        path = directory / name
        path.write_text(
            json.dumps(
                {
                    "schema_version": "inference-foundry.kv-dedup-quality-validation.v1",
                    "content_identity_sha256": content_id,
                    "provenance": {
                        "model": {
                            "weight_files": [{"name": "weights", "sha256": "model"}]
                        }
                    },
                    "corpus": {"generated_corpus_sha256": "corpus"},
                    "transform": {
                        "scheme": "minimum_joint_kv_weight_distance_pair_mean",
                        "transformed_layer_indices": [0],
                        "layer_pairings": [[[0, 1]]],
                        "kv_cache_reduction_percent": reduction,
                        "estimated_weight_storage_reduction_percent": reduction / 10.0,
                    },
                    "metrics": {
                        "nll_delta": 0.01,
                        "perplexity_ratio": 1.01,
                        "logit_rmse": 0.1,
                        "logit_cosine_similarity": 0.99,
                        "top1_agreement": 0.9,
                        "target_tokens": 10,
                    },
                    "quality_report": {"passed": passed},
                }
            ),
            encoding="utf-8",
        )
        return path


if __name__ == "__main__":
    unittest.main()
