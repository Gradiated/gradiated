#!/usr/bin/env python3
import ast
import json
import math
import os
import random
import resource
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_quality import QualityError, load_and_validate


class ScoreError(ValueError):
    pass


def normalized(value):
    return " ".join(str(value).strip().split()).casefold()


def safe_python(source):
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    defined_functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    allowed_calls = defined_functions | {"min", "max", "len", "range", "list", "tuple"}
    forbidden = (
        ast.Import, ast.ImportFrom, ast.Attribute, ast.ClassDef, ast.AsyncFunctionDef,
        ast.Global, ast.Nonlocal, ast.Lambda, ast.With, ast.AsyncWith, ast.Try,
        ast.Raise, ast.While, ast.Delete,
    )
    for node in ast.walk(tree):
        if isinstance(node, forbidden):
            return False
        if isinstance(node, ast.Name) and node.id.startswith("__"):
            return False
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in allowed_calls:
                return False
    return True


def limit_child():
    resource.setrlimit(resource.RLIMIT_CPU, (1, 1))
    resource.setrlimit(resource.RLIMIT_AS, (128 * 1024 * 1024, 128 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (8, 8))


def executable_score(source, tests):
    if not isinstance(source, str) or not safe_python(source):
        return 0.0
    program = source + "\n" + "\n".join(tests) + "\n"
    try:
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-I", "-S", "-c", program],
                cwd=directory,
                env={"PATH": os.environ.get("PATH", "")},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=2,
                preexec_fn=limit_child,
                check=False,
            )
    except (OSError, subprocess.TimeoutExpired):
        return 0.0
    return 1.0 if result.returncode == 0 else 0.0


def case_score(case, output):
    scorer = case["scorer"]
    kind = scorer["kind"]
    if kind == "json_exact":
        if not isinstance(output, str):
            return 0.0, {}
        try:
            parsed = json.loads(output)
        except json.JSONDecodeError:
            return 0.0, {"malformed": True}
        return (1.0 if parsed == scorer["expected"] else 0.0), {"malformed": False}
    if kind == "normalized_exact":
        return (1.0 if isinstance(output, str) and normalized(output) == normalized(scorer["expected"]) else 0.0), {}
    if kind == "python_tests":
        return executable_score(output, scorer["tests"]), {}
    if kind == "teacher_forced_logprobs":
        if not isinstance(output, dict):
            return 0.0, {"teacher_forced_nll": None}
        if output.get("source") != "runtime_teacher_forced_input_token_logprobs":
            return 0.0, {"teacher_forced_nll": None}
        if output.get("token_sequence_sha256") != case.get("token_sequence_sha256"):
            return 0.0, {"teacher_forced_nll": None}
        values = output.get("input_token_logprobs")
        if not isinstance(values, list) or len(values) < scorer["minimum_scored_tokens"]:
            return 0.0, {"teacher_forced_nll": None}
        logprobs = []
        for value in values:
            if not isinstance(value, dict) or set(value) != {"logprob", "token_id"}:
                return 0.0, {"teacher_forced_nll": None}
            logprob = value["logprob"]
            token_id = value["token_id"]
            if not isinstance(logprob, (int, float)) or isinstance(logprob, bool) or not math.isfinite(logprob) or logprob > 0:
                return 0.0, {"teacher_forced_nll": None}
            if not isinstance(token_id, int) or isinstance(token_id, bool) or token_id < 0:
                return 0.0, {"teacher_forced_nll": None}
            logprobs.append(float(logprob))
        measured_nll = -sum(logprobs) / len(logprobs)
        return (1.0 if measured_nll <= scorer["max_nll"] else 0.0), {"teacher_forced_nll": measured_nll}
    raise ScoreError(f"unsupported scorer: {kind}")


def load_responses(path, case_ids):
    try:
        rows = [json.loads(line) for line in Path(path).read_text().splitlines() if line]
    except (OSError, json.JSONDecodeError) as error:
        raise ScoreError(f"invalid response JSONL: {error}") from error
    if any(not isinstance(row, dict) or "case_id" not in row or "output" not in row for row in rows):
        raise ScoreError("every response requires case_id and output")
    by_id = {row["case_id"]: row["output"] for row in rows}
    if len(by_id) != len(rows) or set(by_id) != case_ids:
        raise ScoreError("responses must contain each frozen case exactly once")
    return by_id


def evaluate(cases, response_path):
    responses = load_responses(response_path, {case["case_id"] for case in cases})
    case_results = []
    for case in cases:
        score, metrics = case_score(case, responses[case["case_id"]])
        case_results.append({"case_id": case["case_id"], "category": case["category"], "score": score, "metrics": metrics})
    categories = {}
    for category in sorted({case["category"] for case in cases}):
        values = [result["score"] for result in case_results if result["category"] == category]
        categories[category] = sum(values) / len(values)
    return {"overall": sum(result["score"] for result in case_results) / len(case_results), "categories": categories, "cases": case_results}


def paired_interval(differences, samples, confidence, seed):
    if not differences:
        raise ScoreError("no paired cases")
    generator = random.Random(seed)
    boot = []
    for _ in range(samples):
        draw = [differences[generator.randrange(len(differences))] for _ in differences]
        boot.append(sum(draw) / len(draw))
    boot.sort()
    tail = (1.0 - confidence) / 2.0
    low = boot[max(0, int(tail * len(boot)))]
    high = boot[min(len(boot) - 1, int((1.0 - tail) * len(boot)) - 1)]
    return [low, high]


def score_pair(root, split, control_path, candidate_path):
    try:
        bundle = load_and_validate(root)
    except QualityError as error:
        raise ScoreError(str(error)) from error
    if split not in {"development", "holdout"}:
        raise ScoreError("split must be development or holdout")
    cases = bundle["fixtures"][split]
    control = evaluate(cases, control_path)
    candidate = evaluate(cases, candidate_path)
    control_by_id = {row["case_id"]: row for row in control["cases"]}
    candidate_by_id = {row["case_id"]: row for row in candidate["cases"]}
    differences = [candidate_by_id[case["case_id"]]["score"] - control_by_id[case["case_id"]]["score"] for case in cases]
    policy = bundle["policy"]
    interval = paired_interval(differences, policy["paired_bootstrap_samples"], policy["paired_confidence_level"], policy["frozen_seed"])
    overall_regression = control["overall"] - candidate["overall"]
    category_regressions = {name: control["categories"][name] - candidate["categories"][name] for name in control["categories"]}
    reasons = []
    if overall_regression > policy["max_overall_point_regression"] + 1e-12:
        reasons.append("overall_point_regression")
    if any(value > policy["max_critical_category_regression"] + 1e-12 for value in category_regressions.values()):
        reasons.append("critical_category_regression")
    if policy["catastrophic_category_failure_is_reject"] and any(value == 0.0 for value in candidate["categories"].values()):
        reasons.append("catastrophic_category_failure")
    control_nll = next(row["metrics"].get("teacher_forced_nll") for row in control["cases"] if row["category"] == "teacher_forced_loss")
    candidate_nll = next(row["metrics"].get("teacher_forced_nll") for row in candidate["cases"] if row["category"] == "teacher_forced_loss")
    if control_nll is None or candidate_nll is None or candidate_nll > control_nll * (1 + policy["max_teacher_forced_nll_relative_increase"]):
        reasons.append("teacher_forced_loss_regression")
    margin = -policy["max_overall_point_regression"]
    provisional = not reasons and interval[0] <= margin
    return {
        "schema_version": 1,
        "suite_sha256": bundle["manifest"]["bundle_sha256"],
        "split": split,
        "control": control,
        "candidate": candidate,
        "overall_regression": overall_regression,
        "category_regressions": category_regressions,
        "candidate_minus_control_paired_ci": interval,
        "point_screen_pass": not reasons,
        "provisional_due_to_uncertainty": provisional,
        "reject_reasons": reasons,
    }


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("usage: score_pair.py SUITE_DIR SPLIT CONTROL.jsonl CANDIDATE.jsonl", file=sys.stderr)
        raise SystemExit(2)
    try:
        result = score_pair(Path(sys.argv[1]), sys.argv[2], Path(sys.argv[3]), Path(sys.argv[4]))
    except ScoreError as error:
        print(f"INVALID: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
