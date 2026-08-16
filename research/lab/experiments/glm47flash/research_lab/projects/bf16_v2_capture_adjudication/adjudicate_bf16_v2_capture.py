#!/usr/bin/env python3
"""Deterministically adjudicate the frozen BF16 V2 capture archive."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import subprocess
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BRIDGE = ROOT.parent / "bf16_vllm_quality_bridge" / "artifacts" / "nebius_h100_bf16_vllm_v2_2026-07-15-r4"
ARCHIVE = BRIDGE / "vllm-awq-batch.tar.gz"
SUITE = ROOT.parent / "quality_gate_calibration" / "executable_development_v2" / "development.jsonl"
PREREGISTRATION = ROOT.parent / "quality_gate_calibration" / "BF16_DEVELOPMENT_CAPTURE_PREREGISTRATION.json"
ARCHIVE_SHA256 = "98e34729b73048ab97e20e66eda4ee807bb6a6e41fbe9c403273135035b39dba"
FIXTURE_SHA256 = "4953e524526106b353a7df8de6d84e45fa18d96464935117ca926f483d03a6b7"
MANIFEST_SHA256 = "d304c6b323cd382b0a952b3389267b8d4881096cb4dc0622b051014769852351"
PREREGISTRATION_SHA256 = "1191fc7643120e8bb1f8eab796fbd22f29e7065b26a1c7b4e28387eddd0b32d8"
REVISION = "33faccf4c2ba82142214d0d4e16232a4e9ccfe10"
REQUIRED = ("raw-response-bytes", "normalized-output-bytes", "transform-decisions", "responses.jsonl", "runtime-evidence.json", "identity-manifest.json", "capture-result.json")
FENCE = re.compile(r"\A```python\r?\n([\s\S]*?)\r?\n```\Z")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def read_json(data: bytes, label: str) -> object:
    try:
        return json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label}: invalid JSON") from error


def normalized_exact(value: object, expected: str) -> bool:
    return isinstance(value, str) and value.strip() == expected


def json_exact(value: object, expected: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return json.loads(value) == expected
    except json.JSONDecodeError:
        return False


def python_source(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    fenced = FENCE.fullmatch(value)
    if fenced:
        return fenced.group(1)
    if "```" in value:
        return None
    return value


def python_tests(value: object, tests: list[str]) -> bool:
    source = python_source(value)
    if source is None:
        return False
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "candidate.py"
        path.write_text(source + "\n" + "\n".join(tests) + "\n")
        def limits() -> None:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (2, 2))
            resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_FSIZE, (1024 * 1024, 1024 * 1024))
        try:
            result = subprocess.run([sys.executable, "-I", str(path)], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3, preexec_fn=limits)
        except (OSError, subprocess.TimeoutExpired):
            return False
    return result.returncode == 0


def nll(value: object, case: dict) -> tuple[float, int]:
    if not isinstance(value, dict) or value.get("source") != "runtime_teacher_forced_input_token_logprobs":
        raise ValueError(f"{case['case_id']}: invalid runtime logprob source")
    if value.get("token_sequence_sha256") != case["token_sequence_sha256"]:
        raise ValueError(f"{case['case_id']}: token-sequence hash mismatch")
    rows = value.get("input_token_logprobs")
    if not isinstance(rows, list) or len(rows) < case["scorer"]["minimum_scored_tokens"]:
        raise ValueError(f"{case['case_id']}: insufficient scored tokens")
    logprobs = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("token_id"), int) or not isinstance(row.get("logprob"), (int, float)) or not math.isfinite(float(row["logprob"])):
            raise ValueError(f"{case['case_id']}: malformed finite runtime logprob")
        logprobs.append(float(row["logprob"]))
    return -sum(logprobs) / len(logprobs), len(logprobs)


def negative_controls() -> dict[str, bool]:
    return {
        "json_key_order_is_canonical": json_exact('{"b":2,"a":1}', {"a": 1, "b": 2}),
        "json_extra_field_rejected": not json_exact('{"a":1,"b":2}', {"a": 1}),
        "normalized_whitespace_only_accepted": normalized_exact("  expected\n", "expected"),
        "normalized_prefix_rejected": not normalized_exact("answer: expected", "expected"),
        "single_python_fence_accepted": python_tests("```python\ndef add(a, b):\n    return a + b\n```", ["assert add(2, 3) == 5"]),
        "prose_python_rejected": not python_tests("Here is code:\n```python\ndef add(a,b): return a+b\n```", ["assert add(2, 3) == 5"]),
        "multiple_python_blocks_rejected": not python_tests("```python\ndef add(a,b): return a+b\n```\n```python\npass\n```", ["assert add(2, 3) == 5"]),
        "wrong_fence_rejected": not python_tests("```json\n{}\n```", ["assert True"]),
        "nonfinite_logprob_rejected": _nonfinite_rejected(),
    }


def _nonfinite_rejected() -> bool:
    case = {"case_id": "negative", "token_sequence_sha256": "x", "scorer": {"minimum_scored_tokens": 1}}
    try:
        nll({"source": "runtime_teacher_forced_input_token_logprobs", "token_sequence_sha256": "x", "input_token_logprobs": [{"token_id": 1, "logprob": float("nan")}]}, case)
    except ValueError:
        return True
    return False


def member_bytes(archive: tarfile.TarFile, name: str) -> bytes:
    handle = archive.extractfile(name)
    if handle is None:
        raise ValueError(f"missing archive member {name}")
    return handle.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--output", type=Path, default=ROOT / "BF16_V2_CONTROL_ADJUDICATION.json")
    args = parser.parse_args()
    controls = negative_controls()
    if args.self_test:
        print(json.dumps({"negative_controls": controls, "pass": all(controls.values())}, sort_keys=True))
        raise SystemExit(0 if all(controls.values()) else 1)
    checks = {"archive_sha256": digest(ARCHIVE.read_bytes()) == ARCHIVE_SHA256, "suite_fixture_sha256": digest(SUITE.read_bytes()) == FIXTURE_SHA256, "suite_manifest_sha256": digest((SUITE.parent / "MANIFEST.json").read_bytes()) == MANIFEST_SHA256, "preregistration_sha256": digest(PREREGISTRATION.read_bytes()) == PREREGISTRATION_SHA256, "negative_controls": all(controls.values())}
    cases = [read_json(line, "suite row") for line in SUITE.read_bytes().splitlines()]
    if len(cases) != 36 or not all(isinstance(case, dict) for case in cases):
        raise ValueError("frozen suite geometry invalid")
    suite_by_id = {case["case_id"]: case for case in cases}
    if len(suite_by_id) != 36:
        raise ValueError("duplicate suite case ID")
    capture_results, ceilings = [], defaultdict(list)
    with tarfile.open(ARCHIVE, "r:gz") as archive:
        names = {member.name for member in archive.getmembers() if member.isfile()}
        manifest = read_json(member_bytes(archive, "bf16-v2-quality/manifest.json"), "archive manifest")
        manifest_rows = {row["path"]: row for row in manifest if isinstance(row, dict)} if isinstance(manifest, list) else {}
        checks["internal_manifest_complete"] = len(manifest_rows) == len(manifest)
        for path, row in manifest_rows.items():
            data = member_bytes(archive, "bf16-v2-quality/" + path)
            if row.get("bytes") != len(data) or row.get("sha256") != digest(data):
                raise ValueError(f"internal manifest mismatch: {path}")
        checks["internal_manifest_hashes"] = True
        for capture in range(1, 4):
            prefix = f"bf16-v2-quality/capture-{capture}/"
            available = {name.removeprefix(prefix) for name in names if name.startswith(prefix)}
            if not set(REQUIRED).issubset(available):
                raise ValueError(f"capture-{capture}: required artifact missing")
            artifacts = {name: member_bytes(archive, prefix + name) for name in REQUIRED}
            identity = read_json(artifacts["identity-manifest.json"], f"capture-{capture} identity")
            result = read_json(artifacts["capture-result.json"], f"capture-{capture} result")
            runtime = read_json(artifacts["runtime-evidence.json"], f"capture-{capture} runtime")
            decisions = read_json(artifacts["transform-decisions"], f"capture-{capture} decisions")
            if not isinstance(identity, dict) or identity != {"model": "glm-4.7-flash-bf16", "model_revision": REVISION, "suite_sha256": FIXTURE_SHA256}:
                raise ValueError(f"capture-{capture}: frozen identity mismatch")
            if not isinstance(result, dict) or result.get("capture_pass") is not True or result.get("case_count") != 36 or result.get("model_revision") != REVISION or tuple(result.get("required_artifacts", [])) != REQUIRED:
                raise ValueError(f"capture-{capture}: capture-result contract mismatch")
            if artifacts["normalized-output-bytes"] != artifacts["responses.jsonl"]:
                raise ValueError(f"capture-{capture}: normalized response alias mismatch")
            responses = [read_json(line, f"capture-{capture} response") for line in artifacts["responses.jsonl"].splitlines()]
            raw_rows = artifacts["raw-response-bytes"].splitlines()
            if len(responses) != 36 or len(raw_rows) != 36 or not isinstance(decisions, list) or len(decisions) != 36 or not isinstance(runtime, dict):
                raise ValueError(f"capture-{capture}: response geometry mismatch")
            response_by_id = {row.get("case_id"): row.get("output") for row in responses if isinstance(row, dict)}
            decision_by_id = {row.get("case_id"): row for row in decisions if isinstance(row, dict)}
            runtime_by_id = {row.get("case_id"): row for row in runtime.get("cases", []) if isinstance(row, dict)}
            if set(response_by_id) != set(suite_by_id) or set(decision_by_id) != set(suite_by_id) or set(runtime_by_id) != set(suite_by_id):
                raise ValueError(f"capture-{capture}: case IDs do not bind to frozen suite")
            if artifacts["normalized-output-bytes"] != b"".join(canonical(row) + b"\n" for row in responses):
                raise ValueError(f"capture-{capture}: responses are not canonical normalized JSON")
            if runtime.get("raw_response_sha256") != digest(artifacts["raw-response-bytes"]):
                raise ValueError(f"capture-{capture}: aggregate raw hash mismatch")
            for response, raw, decision in zip(responses, raw_rows, decisions):
                case_id = response.get("case_id") if isinstance(response, dict) else None
                if not isinstance(decision, dict) or decision.get("case_id") != case_id or decision.get("raw_response_sha256") != digest(raw) or runtime_by_id[case_id] != decision:
                    raise ValueError(f"capture-{capture}: raw response binding mismatch for {case_id}")
            category_scores = defaultdict(int)
            case_scores = []
            for case in cases:
                value, kind = response_by_id[case["case_id"]], case["scorer"]["kind"]
                if kind == "json_exact":
                    passed = json_exact(value, case["scorer"]["expected"])
                elif kind == "normalized_exact":
                    passed = normalized_exact(value, case["scorer"]["expected"])
                elif kind == "python_tests":
                    passed = python_tests(value, case["scorer"]["tests"])
                elif kind == "teacher_forced_logprobs_calibration":
                    value_nll, token_count = nll(value, case)
                    ceilings[case["case_id"]].append(value_nll)
                    passed = True
                else:
                    raise ValueError(f"unknown scorer {kind}")
                category_scores[case["category"]] += int(passed)
                item = {"case_id": case["case_id"], "category": case["category"], "pass": passed}
                if kind == "teacher_forced_logprobs_calibration":
                    item.update(mean_nll=value_nll, scored_tokens=token_count)
                case_scores.append(item)
            if len(category_scores) != 6 or any(case["category"] not in category_scores for case in cases):
                raise ValueError(f"capture-{capture}: category geometry invalid")
            capture_results.append({"capture": capture, "category_scores": dict(sorted(category_scores.items())), "case_scores": case_scores, "identity_verified": True, "raw_response_bindings_verified": True})
    ceilings_result = {case_id: {"control_mean_nll": values, "max_control_mean_nll": max(values), "ceiling": max(values) * 1.05} for case_id, values in sorted(ceilings.items())}
    category_repeatable = {category: [capture["category_scores"][category] for capture in capture_results] for category in sorted(capture_results[0]["category_scores"])}
    gate_pass = all(all(score >= 5 for score in scores) for scores in category_repeatable.values())
    adjudication = {"schema_version": 1, "classification": "BF16_V2_development_control_adjudication", "archive": {"path": str(ARCHIVE), "sha256": ARCHIVE_SHA256}, "checks": checks, "captures": capture_results, "category_repeatability": category_repeatable, "gate": {"minimum_per_category": 5, "pass": gate_pass, "decision": "establish_bf16_development_control_unlock_bounded_student_recovery_canary" if all(checks.values()) and gate_pass else "close_current_quality_gate"}, "legacy_outer_controller": {"allocation_result_json": "missing_legacy_packaging_artifact", "scientific_effect": "none; it is not part of the V2 per-capture contract"}}
    args.output.write_bytes(json.dumps(adjudication, indent=2, sort_keys=True).encode() + b"\n")
    if all(checks.values()) and gate_pass:
        (ROOT / "BF16_V2_NLL_CEILINGS.json").write_bytes(json.dumps({"schema_version": 1, "rule": "1.05 * max(control mean NLL across three captures)", "ceilings": ceilings_result}, indent=2, sort_keys=True).encode() + b"\n")
    print(json.dumps({"gate_pass": gate_pass, "checks_pass": all(checks.values()), "output": str(args.output)}, sort_keys=True))


if __name__ == "__main__":
    main()
