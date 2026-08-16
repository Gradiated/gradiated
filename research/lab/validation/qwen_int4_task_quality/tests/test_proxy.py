import unittest

from validation.qwen_int4_task_quality.proxy import validate_proxy_contract


class ProxyContractTests(unittest.TestCase):
    def test_accepts_same_frozen_runtime_representation(self) -> None:
        validate_proxy_contract(self._document())

    def test_rejects_float32_scale_storage(self) -> None:
        document = self._document()
        document["quantization"]["scale_storage"] = "float32"

        with self.assertRaisesRegex(ValueError, "scale storage"):
            validate_proxy_contract(document)

    @staticmethod
    def _document() -> dict[str, object]:
        return {
            "dtype": "bfloat16",
            "evaluation_strategy": "interleaved_models",
            "quantization": {
                "granularity": "groupwise",
                "group_size": 8,
                "code_scale": "float32_max_abs_div_7",
                "scale_storage": "bfloat16",
                "dequantization_scale": "stored_bfloat16_promoted_to_float32",
                "included_module_patterns": [
                    "model.layers.*.self_attn.o_proj",
                    "model.layers.*.mlp.gate_proj",
                    "model.layers.*.mlp.up_proj",
                ],
                "expected_module_count": 84,
                "expected_parameter_count": 234881024,
            },
        }


if __name__ == "__main__":
    unittest.main()
