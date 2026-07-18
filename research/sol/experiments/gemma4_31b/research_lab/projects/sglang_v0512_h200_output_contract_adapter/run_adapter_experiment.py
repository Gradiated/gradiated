#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import math
import statistics
import subprocess
import sys
import time
from pathlib import Path

from adapter import adapt, digest, safe_python


PROJECT = Path(__file__).resolve().parent


def load_json(path: Path):
    return json.loads(path.read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path: Path, expected: str) -> None:
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"immutable binding mismatch: {path} {actual} != {expected}")


def request_bytes(row: dict) -> str:
    raw = row.get("raw")
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        raise ValueError(f"missing raw request for {row.get('case_id')}")
    value = raw[0].get("request_bytes")
    if not isinstance(value, str):
        raise ValueError(f"missing raw request bytes for {row.get('case_id')}")
    return value


def adapt_capture(source: Path, destination: Path, audit: Path) -> list[dict]:
    records = []
    adapted_rows = []
    for line in source.read_text().splitlines():
        row = json.loads(line)
        original = row["output"]
        decision = adapt(request_bytes(row), original)
        adapted = dict(row)
        adapted["output"] = decision.output
        adapted_rows.append(adapted)
        records.append({
            "case_id": row["case_id"],
            "request_sha256": hashlib.sha256(request_bytes(row).encode()).hexdigest(),
            "original_output_sha256": digest(original),
            "adapted_output_sha256": digest(decision.output),
            "transformed": decision.transformed,
            "reason": decision.reason,
        })
    destination.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in adapted_rows))
    audit.write_text(json.dumps(records, sort_keys=True, indent=2) + "\n")
    return records


def run_score(quality_suite: Path, control: Path, candidate: Path, destination: Path) -> dict:
    subprocess.run(
        [sys.executable, str(quality_suite), "score", "--control", str(control), "--candidate", str(candidate), "--output", str(destination)],
        check=True,
        capture_output=True,
        text=True,
    )
    return load_json(destination)


def fixture_report() -> list[dict]:
    explicit = json.dumps({"messages": [{"role": "user", "content": "Return only Python code for this task."}]})
    ambiguous = json.dumps({"messages": [{"role": "user", "content": "Explain Python code and include an example."}]})
    fixtures = [
        ("safe_python_fence", explicit, "```python\ndef f(x):\n    return x + 1\n```", True),
        ("safe_unlabeled_fence", explicit, "```\ndef f(x):\n    return x + 1\n```", True),
        ("mixed_prose", explicit, "Here is code:\n```python\ndef f(x):\n    return x\n```", False),
        ("multiple_blocks", explicit, "```python\ndef f(x):\n    return x\n```\n```python\ndef g(x):\n    return x\n```", False),
        ("unsupported_language", explicit, "```javascript\nfunction f(x) { return x; }\n```", False),
        ("malformed_fence", explicit, "```python\ndef f(x):\n    return x", False),
        ("unsafe_python", explicit, "```python\ndef f(x):\n    while x:\n        return x\n```", False),
        ("import", explicit, "```python\nimport os\ndef f(x):\n    return x\n```", False),
        ("attribute", explicit, "```python\ndef f(x):\n    return x.real\n```", False),
        ("ambiguous_request", ambiguous, "```python\ndef f(x):\n    return x\n```", False),
    ]
    report = []
    for name, request, output, expected in fixtures:
        decision = adapt(request, output)
        passed = decision.transformed == expected and (expected or decision.output == output)
        report.append({"name": name, "expected_transformed": expected, "decision": decision.reason, "passed": passed})
    if not all(row["passed"] for row in report):
        raise ValueError("negative fixture failure")
    return report


def benchmark(request: str, transformed: str, unchanged: str, count: int) -> dict:
    samples_ns = []
    for index in range(count):
        output = transformed if index % 2 == 0 else unchanged
        started = time.perf_counter_ns()
        adapt(request, output)
        samples_ns.append(time.perf_counter_ns() - started)
    samples_ns.sort()
    p99_ns = samples_ns[math.ceil(0.99 * count) - 1]
    return {
        "responses": count,
        "mixed_ratio": "50% transformed / 50% unchanged",
        "median_ns": statistics.median(samples_ns),
        "p99_ns": p99_ns,
        "p99_ms": p99_ns / 1_000_000,
    }


def verify_safe_python_parity(scorer: Path, raw_python_output: str, destination: Path) -> dict:
    spec = importlib.util.spec_from_file_location("bound_strict_scorer", scorer)
    if spec is None or spec.loader is None:
        raise ValueError("unable to import bound strict scorer")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(scorer.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    bodies = [
        "def f(x):\n    return x + 1",
        "import os\ndef f(x):\n    return x",
        "def f(x):\n    return x.real",
        "def f(x):\n    while x:\n        return x",
        raw_python_output.removeprefix("```python\n").removesuffix("\n```"),
    ]
    rows = [{"source_sha256": digest(body), "adapter_safe": safe_python(body), "bound_safe": module.safe_python(body)} for body in bodies]
    if any(row["adapter_safe"] != row["bound_safe"] for row in rows):
        raise ValueError("safe Python implementation differs from bound scorer")
    result = {"pass": True, "rows": rows}
    destination.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark-responses", type=int, default=100000)
    args = parser.parse_args()
    bindings = load_json(PROJECT / "BINDINGS.json")
    quality_root = (PROJECT / bindings["quality_terminal"]["path"]).resolve().parent
    raw_control = (PROJECT / bindings["raw_control"]["path"]).resolve()
    raw_candidate = (PROJECT / bindings["raw_candidate"]["path"]).resolve()
    reference = (PROJECT / bindings["reference"]["path"]).resolve()
    terminal = (PROJECT / bindings["quality_terminal"]["path"]).resolve()
    scorer = Path(bindings["strict_scorer"]["path"])
    for path, item in ((raw_control, bindings["raw_control"]), (raw_candidate, bindings["raw_candidate"]), (reference, bindings["reference"]), (terminal, bindings["quality_terminal"]), (scorer, bindings["strict_scorer"])):
        require_hash(path, item["sha256"])
    out = PROJECT / "artifacts" / "adapter-terminal"
    out.mkdir(parents=True, exist_ok=True)
    control_audit = adapt_capture(raw_control, out / "control_adapted.jsonl", out / "control_audit.json")
    candidate_audit = adapt_capture(raw_candidate, out / "candidate_adapted.jsonl", out / "candidate_audit.json")
    if control_audit != candidate_audit:
        raise ValueError("control/candidate adapter decisions differ")
    transformed = [row for row in control_audit if row["transformed"]]
    non_targets = [row for row in control_audit if not row["transformed"]]
    if any(row["case_id"] != "python" for row in transformed) or any(row["original_output_sha256"] != row["adapted_output_sha256"] for row in non_targets):
        raise ValueError("adapter did not have the required narrow identity boundary")
    quality_suite = raw_control.parents[2] / "quality_suite.py"
    subprocess.run([sys.executable, str(quality_suite), "validate"], check=True, capture_output=True, text=True)
    score = run_score(quality_suite, out / "control_adapted.jsonl", out / "candidate_adapted.jsonl", out / "PAIRED_SCORE.json")
    fixtures = fixture_report()
    raw_python = next(json.loads(line) for line in raw_control.read_text().splitlines() if json.loads(line)["case_id"] == "python")
    safe_python_parity = verify_safe_python_parity(scorer, raw_python["output"], out / "SAFE_PYTHON_PARITY.json")
    unchanged = next(json.loads(line) for line in raw_control.read_text().splitlines() if json.loads(line)["case_id"] == "math")["output"]
    overhead = benchmark(request_bytes(raw_python), raw_python["output"], unchanged, args.benchmark_responses)
    overhead["service_seconds_per_request"] = bindings["candidate"]["service_seconds_per_request"]
    overhead["derived_service_impact_percent"] = overhead["p99_ns"] / 1_000_000_000 / overhead["service_seconds_per_request"] * 100
    (out / "OVERHEAD.json").write_text(json.dumps(overhead, sort_keys=True, indent=2) + "\n")
    reference_data = load_json(reference)
    terminal_data = load_json(terminal)
    reference_pass = bool(bindings["reference"]["prompt_token_identity"] and reference_data["scored_tokens"] == bindings["reference"]["scored_tokens"] and terminal_data["reference_prompt_token_identity"])
    score_pass = bool(score["pass"] and all(row["control_pass"] and row["candidate_pass"] for row in score["cases"]))
    terminal_result = {
        "classification": "sglang_output_contract_adapter_terminal",
        "pass": bool(score_pass and reference_pass and overhead["p99_ms"] <= 1.0 and overhead["derived_service_impact_percent"] < 0.3),
        "raw_sglang_pass": False,
        "adapter_scope": "text-only default non-reasoning requests that explicitly require Python code only",
        "input_hashes": {"control": sha256(raw_control), "candidate": sha256(raw_candidate), "reference": sha256(reference), "quality_terminal": sha256(terminal), "strict_scorer": sha256(scorer), "quality_runner": sha256(quality_suite)},
        "transformation": {"control": control_audit, "candidate": candidate_audit},
        "strict_score": score,
        "reference_pass": reference_pass,
        "negative_fixtures": fixtures,
        "safe_python_parity": safe_python_parity,
        "overhead": overhead,
    }
    (out / "TERMINAL.json").write_text(json.dumps(terminal_result, sort_keys=True, indent=2) + "\n")
    if not terminal_result["pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
