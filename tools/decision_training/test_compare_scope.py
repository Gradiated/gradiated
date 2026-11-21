import math
from copy import deepcopy

import pytest
from compare import (
    calibration_rows,
    validate_benchmark_predictions,
    validate_dev_predictions,
)


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
            "logits": [math.log(0.2), math.log(0.8)],
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


@pytest.mark.parametrize(
    "change",
    [
        {"probs": {"no": -0.2, "yes": 1.2}},
        {"probs": {"no": 0.2, "yes": 0.9}},
        {"probs": {"no": float("nan"), "yes": 0.8}},
        {"logits": [0.0, float("inf")]},
        {"logits": [0.0, 1.0, 2.0]},
        {"logits": [0.0, 0.0]},
    ],
)
def test_corrupt_distributions_rejected_before_metrics(change):
    source = [{"id": "x", "expected": "yes", "labels": ["no", "yes"]}]
    row = {
        "id": "x",
        "expected": "yes",
        "correct": True,
        "probs": {"no": 0.2, "yes": 0.8},
        "logits": [math.log(0.2), math.log(0.8)],
    }
    with pytest.raises(ValueError, match="probabilities|logits"):
        validate_benchmark_predictions([{**row, **change}], source)


def test_dev_predictions_require_full_original_targets_and_ordered_labels():
    source = [
        {"id": str(i), "labels": ["no", "yes"], "target": [0.3, 0.7]} for i in range(2)
    ]
    rows = [
        {
            "id": row["id"],
            "target": row["target"],
            "probs": {"no": 0.2, "yes": 0.8},
            "logits": [math.log(0.2), math.log(0.8)],
        }
        for row in source
    ]
    validate_dev_predictions(rows, source)
    for bad in (rows[:1], [rows[0], rows[0]]):
        with pytest.raises(ValueError, match="complete source-matched"):
            validate_dev_predictions(bad, source)
    bad = deepcopy(rows)
    bad[0]["target"] = [0.7, 0.3]
    with pytest.raises(ValueError, match="targets"):
        validate_dev_predictions(bad, source)
    bad = deepcopy(rows)
    bad[0]["probs"] = {"yes": 0.8, "no": 0.2}
    with pytest.raises(ValueError, match="probabilities"):
        validate_dev_predictions(bad, source)


def test_calibration_selection_filters_length_before_taking_first_256(monkeypatch):
    monkeypatch.setattr("compare.render_prompt", lambda tokenizer, row: row["size"])

    class Tokenizer:
        def encode(self, size, add_special_tokens):
            return [1] * size

    rows = [{"id": str(i), "size": 20 if i == 0 else 5} for i in range(300)]
    result = calibration_rows(rows, Tokenizer(), 10)
    assert [r["id"] for r in result] == [str(i) for i in range(1, 257)]
