import json
from pathlib import Path

import pytest
from checkpoint_eval import predicted_label, summarize, validate_row, verify_adapter
from data import read_jsonl


def test_jsonl_unicode_line_separator_remains_inside_visible_state(tmp_path):
    row = {
        "state": "a\u2028b",
        "labels": ["a", "b"],
        "descriptions": ["A", "B"],
        "gold": "a",
    }
    path = tmp_path / "panel.jsonl"
    path.write_text(json.dumps(row, ensure_ascii=False) + "\n")
    assert [validate_row(item) for item in read_jsonl(path)] == [row]


def test_paired_metrics_derive_correctness_from_predictions():
    rows = [
        {
            "id": "a",
            "benchmark": "b",
            "labels": ["no", "yes"],
            "gold": "yes",
            "base": {"label": "no", "probabilities": [0.8, 0.2]},
            "checkpoint": {"label": "yes", "probabilities": [0.2, 0.8]},
        },
        {
            "id": "b",
            "benchmark": "b",
            "labels": ["no", "yes"],
            "gold": "no",
            "base": {"label": "no", "probabilities": [0.8, 0.2]},
            "checkpoint": {"label": "yes", "probabilities": [0.2, 0.8]},
        },
    ]
    report = summarize(rows)["b"]
    assert report["paired"] == 2
    assert report["wins"] == report["losses"] == 1
    assert report["mcnemar_exact_p"] == 1
    assert report["arms"]["base"]["accuracy"] == 0.5
    assert report["arms"]["base"]["brier"] == pytest.approx(0.68)


def test_adapter_payload_hash_is_checked(tmp_path: Path):
    (tmp_path / "checkpoint-complete.json").write_text(
        json.dumps(
            {
                "files": {
                    "adapter_config.json": "bad",
                    "adapter_model.safetensors": "bad",
                }
            }
        )
    )
    (tmp_path / "adapter_config.json").write_text("{}")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_adapter(tmp_path)


def test_wrong_gold_and_option_alignment_rejected():
    with pytest.raises(ValueError, match="aligned"):
        validate_row({"labels": ["a", "b"], "descriptions": ["A", "B"], "gold": "c"})
    with pytest.raises(ValueError, match="duplicate"):
        validate_row({"labels": ["a", "a"], "descriptions": ["A", "A"], "gold": "a"})


def test_ties_use_frozen_benchmark_label_ordering_and_ignore_stale_labels():
    assert predicted_label(["z", "a"], [0.5, 0.5]) == "a"
    row = {
        "id": "tie",
        "benchmark": "b",
        "labels": ["z", "a"],
        "gold": "a",
        "base": {"label": "z", "probabilities": [0.5, 0.5]},
    }
    assert summarize([row])["b"]["arms"]["base"]["correct"] == 1
