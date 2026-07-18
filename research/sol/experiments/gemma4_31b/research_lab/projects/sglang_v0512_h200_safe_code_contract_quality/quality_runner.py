#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

from safe_code_contract import CONTRACT, canonical_json, digest_bytes, transform_request


PROJECT = Path(__file__).resolve().parent
ADAPTER = PROJECT.parent / "sglang_v0512_h200_output_contract_adapter" / "adapter.py"
STRICT_SCORER = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/quality/score_pair.py")
ORIGINAL_SUITE = PROJECT.parent / "sglang_v0512_h200_stock_quality_validation" / "suite"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def load_json(path: Path) -> object:
    return json.loads(path.read_text())


def load_adapter():
    spec = importlib.util.spec_from_file_location("bound_adapter", ADAPTER)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load bound adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_strict_scorer():
    spec = importlib.util.spec_from_file_location("bound_strict_scorer", STRICT_SCORER)
    if spec is None or spec.loader is None:
        raise ValueError("unable to load bound strict scorer")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(STRICT_SCORER.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def heldout_cases() -> list[dict]:
    rows = [
        ("heldout_ordering", "Return only Python code defining `def insertion_sort(xs):` that returns a sorted copy of xs in ascending order.", ["assert insertion_sort([3,1,2]) == [1,2,3]", "assert insertion_sort([]) == []", "assert insertion_sort([2,1,2]) == [1,2,2]"], "ordering"),
        ("heldout_aggregation", "Return only Python code defining `def count_positive(xs):` that returns the number of positive integers in xs.", ["assert count_positive([-2,0,4,1]) == 2", "assert count_positive([]) == 0", "assert count_positive([-1,-3]) == 0"], "aggregation"),
        ("heldout_indexing", "Return only Python code defining `def at_or_none(xs, index):` that returns xs[index] when index is valid and None otherwise.", ["assert at_or_none([7,8,9], 1) == 8", "assert at_or_none([7], -1) is None", "assert at_or_none([7], 1) is None"], "indexing"),
        ("heldout_branching", "Return only Python code defining `def clamp(value, low, high):` that returns low below the range, high above the range, otherwise value.", ["assert clamp(3, 4, 9) == 4", "assert clamp(12, 4, 9) == 9", "assert clamp(7, 4, 9) == 7"], "branching"),
    ]
    return [
        {"case_id": case_id, "prompt": prompt, "scorer": {"kind": "python_tests", "tests": tests}, "category": category, "heldout": True}
        for case_id, prompt, tests, category in rows
    ]


def original_cases() -> list[dict]:
    rows = [json.loads(line) for line in (ORIGINAL_SUITE / "cases.jsonl").read_text().splitlines()]
    for row in rows:
        if row["scorer"]["kind"] == "python":
            row["scorer"]["kind"] = "python_tests"
    return rows


def build_suite() -> dict:
    suite = PROJECT / "suite"
    suite.mkdir(exist_ok=True)
    original = original_cases()
    heldout = heldout_cases()
    cases = original + heldout
    for case in cases:
        case["content_sha256"] = hashlib.sha256(canonical_json({k: v for k, v in case.items() if k != "content_sha256"}).encode()).hexdigest()
    policy = {
        "model": "google/gemma-4-31B-it",
        "revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "temperature": 0.0,
        "top_p": 1.0,
        "max_tokens": 128,
        "repetitions": 2,
        "max_nll_delta": 0.03,
        "minimum_scored_tokens": 128,
        "request_transformer": "safe_code_contract.py",
        "adapter": str(ADAPTER),
        "contract": CONTRACT,
    }
    (suite / "cases.jsonl").write_text("".join(canonical_json(row) + "\n" for row in cases))
    write(suite / "policy.json", policy)
    manifest = {path.name: sha(path) for path in (suite / "cases.jsonl", suite / "policy.json")}
    manifest["suite_sha256"] = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    write(suite / "MANIFEST.json", manifest)
    return manifest


def load_suite() -> tuple[dict, list[dict], dict]:
    suite = PROJECT / "suite"
    manifest = load_json(suite / "MANIFEST.json")
    actual = {path.name: sha(path) for path in (suite / "cases.jsonl", suite / "policy.json")}
    if actual != {k: manifest[k] for k in actual}:
        raise ValueError("suite content binding mismatch")
    if hashlib.sha256(canonical_json(actual).encode()).hexdigest() != manifest["suite_sha256"]:
        raise ValueError("suite manifest identity mismatch")
    return load_json(suite / "policy.json"), [json.loads(line) for line in (suite / "cases.jsonl").read_text().splitlines()], manifest


def payload(case: dict, policy: dict) -> str:
    messages = case.get("scorer", {}).get("history", []) + [{"role": "user", "content": case["prompt"]}]
    return canonical_json({"model": policy["model"], "messages": messages, "temperature": 0.0, "top_p": 1.0, "max_tokens": policy["max_tokens"], "stream": False})


def score_python(strict_scorer, output: object, tests: list[str]) -> float:
    return strict_scorer.executable_score(output, tests)


def score_capture(cases: list[dict], captures: Path) -> dict:
    adapter = load_adapter()
    strict_scorer = load_strict_scorer()
    rows = {row["case_id"]: row for row in (json.loads(line) for line in captures.read_text().splitlines())}
    if set(rows) != {case["case_id"] for case in cases}:
        raise ValueError("capture does not contain each frozen case exactly once")
    results = []
    for case in cases:
        row = rows[case["case_id"]]
        decision = adapter.adapt(row["request_bytes"], row["raw_output"])
        if decision.output != row["adapted_output"] or decision.transformed != row["adapter_transformed"]:
            raise ValueError("adapter capture boundary mismatch")
        kind = case["scorer"]["kind"]
        if kind == "python_tests":
            score = score_python(strict_scorer, decision.output, case["scorer"]["tests"])
        elif kind == "nll":
            values = row["raw_output"].get("input_token_logprobs", []) if isinstance(row["raw_output"], dict) else []
            score = 1.0 if len(values) >= case["scorer"].get("minimum", 128) else 0.0
        elif kind == "exact":
            score = 1.0 if isinstance(decision.output, str) and decision.output.strip() == case["scorer"]["expected"] else 0.0
        elif kind == "json":
            try:
                score = 1.0 if json.loads(decision.output) == case["scorer"]["expected"] else 0.0
            except (TypeError, json.JSONDecodeError):
                score = 0.0
        else:
            raise ValueError(f"unknown scorer {kind}")
        results.append({"case_id": case["case_id"], "score": score, "adapter_transformed": decision.transformed, "adapter_reason": decision.reason})
    return {"pass": all(row["score"] == 1.0 for row in results), "cases": results}


def synthetic_safe_output(case_id: str) -> str:
    outputs = {
        "python": "def median(xs):\n    values = list(xs)\n    for i in range(len(values)):\n        for j in range(len(values) - 1):\n            if values[j] > values[j + 1]:\n                temp = values[j]\n                values[j] = values[j + 1]\n                values[j + 1] = temp\n    return values[len(values) // 2]",
        "heldout_ordering": "def insertion_sort(xs):\n    values = list(xs)\n    for i in range(len(values)):\n        for j in range(len(values) - 1):\n            if values[j] > values[j + 1]:\n                temp = values[j]\n                values[j] = values[j + 1]\n                values[j + 1] = temp\n    return values",
        "heldout_aggregation": "def count_positive(xs):\n    total = 0\n    for value in xs:\n        if value > 0:\n            total = total + 1\n    return total",
        "heldout_indexing": "def at_or_none(xs, index):\n    if index < 0 or index >= len(xs):\n        return None\n    return xs[index]",
        "heldout_branching": "def clamp(value, low, high):\n    if value < low:\n        return low\n    if value > high:\n        return high\n    return value",
    }
    return outputs[case_id]


def precreate() -> dict:
    bindings = load_json(PROJECT / "BINDINGS.json")
    manifest = build_suite()
    policy, cases, _ = load_suite()
    adapter = load_adapter()
    out = PROJECT / "artifacts" / "precreate-terminal"
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    fixture_rows = []
    raw_capture = out / "local_serialized_captures.jsonl"
    for case in cases:
        raw = payload(case, policy)
        transformed = transform_request(raw)
        is_code = case["case_id"] == "python" or case.get("heldout") is True
        if transformed.transformed != is_code:
            raise ValueError(f"unexpected transform decision for {case['case_id']}")
        if not is_code and transformed.request_bytes != raw:
            raise ValueError(f"non-code request mutated for {case['case_id']}")
        if is_code:
            output = synthetic_safe_output(case["case_id"])
        elif case["scorer"]["kind"] == "nll":
            output = {"input_token_logprobs": [{"logprob": -0.5, "token_id": 1} for _ in range(128)]}
        elif case["scorer"]["kind"] == "json":
            output = canonical_json(case["scorer"]["expected"])
        else:
            output = case["scorer"]["expected"]
        adapted = adapter.adapt(transformed.request_bytes, output)
        if is_code and (adapted.output != output or not adapter.safe_python(output)):
            raise ValueError(f"safe adapter boundary did not preserve safe code for {case['case_id']}")
        if not is_code and adapted.output != output:
            raise ValueError(f"non-code response changed for {case['case_id']}")
        fixture_rows.append({"case_id": case["case_id"], "request_bytes": transformed.request_bytes, "raw_output": output, "adapted_output": adapted.output, "adapter_transformed": adapted.transformed})
    raw_capture.write_text("".join(canonical_json(row) + "\n" for row in fixture_rows))
    score = score_capture(cases, raw_capture)
    ambiguous = canonical_json({"messages": [{"role": "user", "content": "Explain Python code and include an example."}]})
    ambiguous_decision = transform_request(ambiguous)
    negative = {
        "ambiguous_not_transformed": not ambiguous_decision.transformed and ambiguous_decision.request_bytes == ambiguous,
        "unsafe_sorted_rejected": not adapter.safe_python("def f(xs):\n    return sorted(xs)"),
        "unsafe_import_rejected": not adapter.safe_python("import os\ndef f(x):\n    return x"),
    }
    deterministic = all(transform_request(payload(case, policy)) == transform_request(payload(case, policy)) for case in cases)
    hashes = {
        "bindings": sha(PROJECT / "BINDINGS.json"), "transformer": sha(PROJECT / "safe_code_contract.py"),
        "runner": sha(PROJECT / "quality_runner.py"), "adapter": sha(ADAPTER), "strict_scorer": sha(STRICT_SCORER),
        "original_suite_manifest": sha(ORIGINAL_SUITE / "MANIFEST.json"), "suite_manifest": sha(PROJECT / "suite" / "MANIFEST.json"),
    }
    adapter_binding_ok = sha(ADAPTER) == bindings["adapter_source"]["sha256"]
    scorer_binding_ok = sha(STRICT_SCORER) == bindings["strict_scorer"]["sha256"]
    terminal = {
        "classification": "sglang_safe_code_contract_precreate_terminal",
        "pass": bool(score["pass"] and deterministic and all(negative.values()) and adapter_binding_ok and scorer_binding_ok),
        "suite_sha256": manifest["suite_sha256"], "cases": len(cases), "heldout_case_ids": [case["case_id"] for case in cases if case.get("heldout")],
        "contract_sha256": digest_bytes(CONTRACT), "deterministic": deterministic, "negative": negative,
        "score": score, "hashes": hashes, "adapter_binding_ok": adapter_binding_ok, "scorer_binding_ok": scorer_binding_ok, "local_capture_sha256": sha(raw_capture),
        "provider_spend_usd": 0.0, "provider_create_authority": "director_only",
        "required_bench": {"accelerator": "nvidia-h200-sxm", "disk_gib": 250, "runtime": bindings["runtime"]["image"]},
    }
    write(out / "TERMINAL.json", terminal)
    return terminal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["build", "validate", "precreate"])
    args = parser.parse_args()
    if args.mode == "build":
        print(build_suite()["suite_sha256"])
    elif args.mode == "validate":
        print(load_suite()[2]["suite_sha256"])
    else:
        terminal = precreate()
        print(json.dumps(terminal, sort_keys=True))
        if not terminal["pass"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
