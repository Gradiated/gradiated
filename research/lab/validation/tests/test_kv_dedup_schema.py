import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_kv_dedup_quality.schema import load_run_config


class KvDedupSchemaTests(unittest.TestCase):
    def test_loads_pair_mean_transform(self) -> None:
        config = self._load(self._document())

        self.assertEqual(
            config.transform_scheme, "minimum_joint_kv_weight_distance_pair_mean"
        )
        self.assertEqual(config.expected_original_kv_heads, 8)
        self.assertEqual(config.expected_unique_kv_heads, 4)
        self.assertEqual(config.maximum_transformed_layers, 7)
        self.assertEqual(config.maximum_pairs_per_transformed_layer, 4)

    def test_rejects_non_halving_transform(self) -> None:
        document = self._document()
        document["transform"]["expected_unique_kv_heads"] = 3

        with self.assertRaisesRegex(ValueError, "pair count"):
            self._load(document)

    def _load(self, document: dict[str, object]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_run_config(path)

    @staticmethod
    def _document() -> dict[str, object]:
        return {
            "schema_version": "inference-foundry.kv-dedup-quality-run.v1",
            "suite": "qwen-kv-dedup",
            "seed": 1,
            "dtype": "bfloat16",
            "torch_threads": 4,
            "evaluation_strategy": "interleaved_models",
            "transform": {
                "scheme": "minimum_joint_kv_weight_distance_pair_mean",
                "expected_original_kv_heads": 8,
                "expected_unique_kv_heads": 4,
                "maximum_transformed_layers": 7,
                "maximum_pairs_per_transformed_layer": 4,
            },
            "non_inferiority": {
                "maximum_nll_increase": 0.15,
                "maximum_perplexity_ratio": 1.15,
                "maximum_logit_rmse": 0.5,
                "minimum_logit_cosine_similarity": 0.98,
                "minimum_top1_agreement": 0.8,
            },
        }


if __name__ == "__main__":
    unittest.main()
