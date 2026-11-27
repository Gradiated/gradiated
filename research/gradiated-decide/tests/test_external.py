import argparse
import json

from gdecide import external


def test_top_noul_and_choice():
    assert external.top({"type": "noul", "noul": 0.8})[:2] == ("true", 0.8)
    assert external.top({"type": "choice", "probabilities": {"A": 0.3, "B": 0.7}})[0] == "B"


def test_macro_f1_and_ece():
    assert external.macro_f1([("E", "E"), ("I", "I")]) == 1.0
    assert external.ece([(1.0, True), (1.0, True)]) == 0.0
    assert abs(external.ece([(0.9, False)]) - 0.9) < 1e-9


def test_score_counts_missing_as_wrong(tmp_path):
    items = tmp_path / "items.jsonl"
    items.write_text("\n".join(json.dumps({"bench": "PubMedQA", "id": i, "request": {}, "gold": "yes"}) for i in "ab"))
    run = tmp_path / "run"
    run.mkdir()
    (run / "predictions-0.jsonl").write_text(json.dumps({"id": "a", "bench": "PubMedQA", "pred": "yes", "p": 0.9,
                                                         "probs": {"yes": 0.9, "no": 0.1}}) + "\n")
    external.score(argparse.Namespace(items=str(items), run=str(run)))
    result = json.loads((run / "external-score.json").read_text())["benchmarks"]["PubMedQA"]
    assert result["n"] == 2 and result["answered"] == 1 and result["top1_accuracy"] == 50.0
