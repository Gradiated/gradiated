import gzip
import json

from gdecide import decontam

LONG = ("the quick brown fox jumps over the lazy dog while the farmer counts thirteen sheep in the green field "
        "near the old mill")


def row(rid, state, instructions="Which?"):
    return {"id": rid, "source": "s", "license": "x", "state": state,
            "questions": {"q": {"type": "choice", "instructions": instructions, "criteria": {"a": None, "b": None}}},
            "expected": {"q": "a"}}


def write_gz(path, rows):
    with gzip.open(path, "wt") as handle:
        for r in rows:
            handle.write(json.dumps(r) + "\n")


def make_inputs(tmp_path):
    suite = tmp_path / "suite"
    suite.mkdir()
    suite_text = "a suite state about something else entirely with enough words to form several thirteen grams"
    write_gz(suite / "selected-rows.jsonl.gz", [row("s1", suite_text)])
    items = tmp_path / "items.jsonl"
    items.write_text("\n".join(json.dumps({"bench": "JevBench", "id": f"j{i}", "gold": "a",
                                           "request": {"state": state, "questions": {"q": {"type": "noul"}}}})
                               for i, state in enumerate(["Exact panel state.", f"Panel item: {LONG}."])) + "\n")
    data = tmp_path / "data"
    data.mkdir()
    write_gz(data / "train.jsonl.gz", [
        row("t1", "Exact panel state."),
        row("t2", f"Unrelated preface, then {LONG} and more words."),
        row("t3", "A clean training state."),
        row("t4", "A suite state about something else entirely with enough words to form several thirteen grams"),
    ])
    return suite, items, data


def kept_ids(path):
    return [json.loads(line)["id"] for line in gzip.open(path, "rt")]


def test_extra_items_decontaminate(tmp_path):
    suite, items, data = make_inputs(tmp_path)
    out = tmp_path / "out"
    decontam.main(["--suite", str(suite), "--inputs", str(data / "*.jsonl.gz"), "--out", str(out), "--workers", "1",
                   "--extra-items", str(items)])
    assert kept_ids(out / "train.jsonl.gz") == ["t3"]
    report = json.loads((out / "decontam-report.json").read_text())["train.jsonl.gz"]
    assert report["dropped"] == {"state_match": 2, "ngram13": 1}
    assert not (out / "suite-ngrams.npz").exists()


def test_without_extra_items_unchanged(tmp_path):
    suite, _, data = make_inputs(tmp_path)
    out = tmp_path / "out"
    decontam.main(["--suite", str(suite), "--inputs", str(data / "*.jsonl.gz"), "--out", str(out), "--workers", "1"])
    assert kept_ids(out / "train.jsonl.gz") == ["t1", "t2", "t3"]
    assert (out / "suite-ngrams.npz").exists()
