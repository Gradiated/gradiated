import unittest

from validation.qwen_kv_dedup_quality.runner import _validate_transform_config
from validation.qwen_kv_dedup_quality.schema import RunConfig
from validation.qwen_kv_dedup_quality.transform import KvHeadDedupSummary
from validation.qwen_int4_quality.schema import QualityThresholds


class KvDedupRunnerTests(unittest.TestCase):
    def test_rejects_runtime_geometry_different_from_pinned_config(self) -> None:
        with self.assertRaisesRegex(ValueError, "original KV head"):
            _validate_transform_config(self._config(), self._summary(original_heads=4))

    @staticmethod
    def _config() -> RunConfig:
        return RunConfig(
            schema_version="inference-foundry.kv-dedup-quality-run.v1",
            suite="suite",
            seed=1,
            dtype="bfloat16",
            torch_threads=4,
            evaluation_strategy="interleaved_models",
            transform_scheme="minimum_joint_kv_weight_distance_pair_mean",
            expected_original_kv_heads=8,
            expected_unique_kv_heads=4,
            maximum_transformed_layers=1,
            maximum_pairs_per_transformed_layer=4,
            thresholds=QualityThresholds(0.15, 1.15, 0.5, 0.98, 0.8),
        )

    @staticmethod
    def _summary(original_heads: int) -> KvHeadDedupSummary:
        return KvHeadDedupSummary(
            scheme="minimum_joint_kv_weight_distance_pair_mean",
            layer_count=1,
            original_kv_heads=original_heads,
            unique_kv_heads=original_heads // 2,
            head_dim=1,
            transformed_module_count=2,
            transformed_parameter_count=8,
            changed_value_count=8,
            total_unique_parameter_count=8,
            baseline_checkpoint_bits_per_parameter=16,
            baseline_checkpoint_weight_bytes=16,
            estimated_deduplicated_weight_bytes=8,
            estimated_weight_storage_reduction_percent=50.0,
            baseline_kv_cache_bytes_per_token=16,
            deduplicated_kv_cache_bytes_per_token=8,
            kv_cache_reduction_percent=50.0,
            total_pairing_distance_squared=1.0,
            layer_pairings=(((0, 1),),),
            runtime_weight_storage_deduplicated=False,
            runtime_kv_cache_deduplicated=False,
            requires_custom_attention_alias_kernel=True,
            transformed_layer_indices=(0,),
            all_layer_relative_pairing_distances=(0.1,),
        )


if __name__ == "__main__":
    unittest.main()
