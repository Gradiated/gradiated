import json
import tempfile
import unittest
from pathlib import Path

from validation.qwen_kv_recovery.schema import load_config


class RecoveryConfigTests(unittest.TestCase):
    def test_loads_pinned_cpu_recovery_contract(self) -> None:
        config = self._load(self._document())

        self.assertEqual(config.data.training_split, "train")
        self.assertEqual(config.data.heldout_split, "test")
        self.assertEqual(config.data.training_target_tokens, 8192)
        self.assertEqual(config.checkpoint_tokens, (2048, 4096, 8192))
        self.assertEqual(config.adapter.rank, 8)
        self.assertEqual(config.maximum_rss_bytes, 18 * 1024**3)
        self.assertEqual(config.zero_token_control.content_identity_sha256, "a" * 64)

    def test_rejects_training_on_the_heldout_split(self) -> None:
        document = self._document()
        document["data"]["training_split"] = "test"

        with self.assertRaisesRegex(ValueError, "training and held-out splits"):
            self._load(document)

    def test_rejects_checkpoint_beyond_training_budget(self) -> None:
        document = self._document()
        document["checkpoints_after_target_tokens"] = [2048, 9000]

        with self.assertRaisesRegex(ValueError, "checkpoint"):
            self._load(document)

    @staticmethod
    def _load(document: dict[str, object]):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(document), encoding="utf-8")
            return load_config(path)

    @staticmethod
    def _document() -> dict[str, object]:
        return {
            "schema_version": "inference-foundry.qwen-kv-recovery-run.v1",
            "suite": "test",
            "seed": 7,
            "device": "cpu",
            "dtype": "bfloat16",
            "torch_threads": 4,
            "maximum_rss_bytes": 18 * 1024**3,
            "data": {
                "dataset_id": "Salesforce/wikitext",
                "dataset_config": "wikitext-2-raw-v1",
                "dataset_revision": "revision",
                "training_split": "train",
                "training_dataset_fingerprint": "fingerprint",
                "heldout_split": "test",
                "reserved_calibration_tokens": 4096,
                "training_target_tokens": 8192,
                "target_tokens_per_step": 128,
            },
            "transform": {
                "scheme": "minimum_joint_kv_weight_distance_pair_mean",
                "original_kv_heads": 8,
                "unique_kv_heads": 4,
            },
            "adapter": {"rank": 8, "alpha": 8.0, "targets": ["q_proj", "o_proj"]},
            "optimization": {
                "optimizer": "AdamW",
                "learning_rate": 0.00004,
                "weight_decay": 0.05,
                "teacher_kl_weight": 0.7,
                "next_token_weight": 0.3,
                "temperature": 2.0,
            },
            "zero_token_control": {
                "path": "artifact.json",
                "sha256": "b" * 64,
                "content_identity_sha256": "a" * 64,
            },
            "checkpoints_after_target_tokens": [2048, 4096, 8192],
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
