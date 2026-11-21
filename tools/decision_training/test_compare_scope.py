import pytest
from compare import validate_benchmark_predictions


def test_equal_partial_sets_and_stale_gold_are_not_the_frozen_benchmark():
    benchmark = [
        {"id": str(n), "expected": "yes", "labels": ["no", "yes"]} for n in range(3)
    ]
    predictions = [
        {
            "id": str(n),
            "expected": "yes",
            "probs": {"no": 0.2, "yes": 0.8},
            "correct": True,
        }
        for n in range(3)
    ]
    validate_benchmark_predictions(predictions, benchmark)
    with pytest.raises(ValueError, match="complete frozen"):
        validate_benchmark_predictions(predictions[:2], benchmark)
    with pytest.raises(ValueError, match="expected answers"):
        validate_benchmark_predictions(
            [{**predictions[0], "expected": "no"}, *predictions[1:]], benchmark
        )
    with pytest.raises(ValueError, match="correctness"):
        validate_benchmark_predictions(
            [{**predictions[0], "correct": False}, *predictions[1:]], benchmark
        )
