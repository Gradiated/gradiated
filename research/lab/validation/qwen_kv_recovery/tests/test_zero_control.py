import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from validation.qwen_kv_recovery.runner import _load_and_validate_zero_token_control


class ZeroTokenControlTests(unittest.TestCase):
    def test_accepts_only_an_exact_initialization_equivalent(self) -> None:
        pairings = tuple((((0, 1), (2, 3), (4, 5), (6, 7))) for _ in range(28))
        weights = [{"name": "model.safetensors", "bytes": 8, "sha256": "c" * 64}]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            holdout = root / "holdout.json"
            holdout.write_text("{}", encoding="utf-8")
            source = root / "source.json"
            document = {
                "content_identity_sha256": "a" * 64,
                "inputs": {
                    "corpus_sha256": hashlib.sha256(b"{}").hexdigest(),
                    "dtype": "bfloat16",
                },
                "provenance": {"model": {"weight_files": weights}},
                "transform": {
                    "layer_pairings": [
                        [list(pair) for pair in layer] for layer in pairings
                    ],
                    "transformed_layer_indices": list(range(28)),
                },
                "metrics": {"candidate_mean_nll": 10.0},
                "quality_report": {"passed": False},
            }
            source.write_text(json.dumps(document), encoding="utf-8")
            config = SimpleNamespace(
                dtype="bfloat16",
                zero_token_control=SimpleNamespace(
                    path=str(source),
                    sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    content_identity_sha256="a" * 64,
                ),
            )
            structure = SimpleNamespace(
                layer_pairings=pairings,
                adapter_b_zero_at_initialization=True,
            )

            result = _load_and_validate_zero_token_control(
                config,
                structure,
                {"weight_files": weights},
                holdout,
            )

        self.assertTrue(result["exactly_equivalent_to_recovery_initialization"])


if __name__ == "__main__":
    unittest.main()
