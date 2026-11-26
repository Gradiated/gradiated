import hashlib
import json

import pytest
from benchmark_identity import verify_benchmark


def test_same_states_with_altered_question_or_expected_are_rejected(
    tmp_path, monkeypatch
):
    path = tmp_path / "benchmark.jsonl"
    row = {"state": "fixed state", "question": "original question", "expected": "yes"}
    original = json.dumps(row).encode()
    monkeypatch.setattr(
        "benchmark_identity.JEVBENCH_SHA256", hashlib.sha256(original).hexdigest()
    )
    path.write_bytes(original)
    verify_benchmark(path)
    for field, value in (("question", "different question"), ("expected", "no")):
        path.write_text(json.dumps({**row, field: value}))
        with pytest.raises(ValueError, match="complete frozen"):
            verify_benchmark(path)
