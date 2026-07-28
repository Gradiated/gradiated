#!/usr/bin/env python3
"""Five-case, token-ID-bound Transformers/SGLang greedy generation comparator."""
import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
import urllib.request
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
WORKSPACE = PROJECT.parents[6]
SOURCE = PROJECT.parent / "sglang_v0512_h200_safe_code_contract_quality"
ADAPTER = PROJECT.parent / "sglang_v0512_h200_output_contract_adapter" / "adapter.py"
SCORER = WORKSPACE / "research/sol/experiments/glm47flash/campaign_100/quality/score_pair.py"
CASES = ("heldout_ordering", "python", "heldout_aggregation", "heldout_indexing", "heldout_branching")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    temporary.replace(path)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def frozen():
    bindings = json.loads((PROJECT / "BINDINGS.json").read_text())
    source_bindings = SOURCE / "BINDINGS.json"
    suite = SOURCE / "suite"
    artifacts = SOURCE / "artifacts" / "h200-safe-code-final-20260718t1255z"
    expected = bindings["frozen_quality_inputs"]
    checks = {
        "source_bindings": sha(source_bindings) == expected["bindings_sha256"],
        "suite_manifest": sha(suite / "MANIFEST.json") == expected["suite_manifest_sha256"],
        "control_capture": sha(artifacts / "control.jsonl") == expected["control_capture_sha256"],
        "candidate_capture": sha(artifacts / "candidate.jsonl") == expected["candidate_capture_sha256"],
        "reference_sentinel": sha(artifacts / "REFERENCE_SENTINEL.json") == expected["reference_sentinel_sha256"],
        "terminal": sha(artifacts / "TERMINAL.json") == expected["terminal_sha256"],
        "adapter": sha(ADAPTER) == expected["adapter_sha256"],
        "strict_scorer": sha(SCORER) == expected["strict_scorer_sha256"],
    }
    manifest = json.loads((suite / "MANIFEST.json").read_text())
    checks["suite"] = manifest["suite_sha256"] == expected["suite_sha256"]
    if not all(checks.values()):
        raise ValueError("frozen binding mismatch: " + canonical(checks))
    rows = {row["case_id"]: row for row in map(json.loads, (suite / "cases.jsonl").read_text().splitlines())}
    if set(CASES) - set(rows):
        raise ValueError("five-case suite incomplete")
    return bindings, manifest, [rows[name] for name in CASES], checks


def request_bytes(case, policy, transform):
    payload = {"model": policy["model"], "messages": case.get("scorer", {}).get("history", []) + [{"role": "user", "content": case["prompt"]}], "temperature": 0.0, "top_p": 1.0, "max_tokens": 128, "stream": False}
    transformed = transform.transform_request(canonical(payload))
    return transformed.request_bytes, transformed


def score(case, raw_request, output, adapter, scorer):
    decision = adapter.adapt(raw_request, output)
    if case["scorer"]["kind"] != "python_tests":
        raise ValueError("admitted five-case suite must be code-only")
    return {"score": scorer.executable_score(decision.output, case["scorer"]["tests"]), "adapter_transformed": decision.transformed, "adapter_reason": decision.reason}


def first_divergence(left, right):
    for index, (a, b) in enumerate(zip(left, right)):
        if a != b:
            return {"index": index, "transformers_token_id": a, "sglang_token_id": b}
    if len(left) != len(right):
        return {"index": min(len(left), len(right)), "transformers_token_id": left[min(len(left), len(right))] if len(left) > len(right) else None, "sglang_token_id": right[min(len(left), len(right))] if len(right) > len(left) else None}
    return None


def local_fixture(output_dir):
    bindings, manifest, cases, checks = frozen()
    adapter, scorer = load_module("bound_adapter", ADAPTER), load_module("bound_scorer", SCORER)
    transform = load_module("safe_code_contract", SOURCE / "safe_code_contract.py")
    safe = {
        "heldout_ordering": "def insertion_sort(xs):\n    values = list(xs)\n    for i in range(len(values)):\n        for j in range(len(values) - 1):\n            if values[j] > values[j + 1]:\n                values[j], values[j + 1] = values[j + 1], values[j]\n    return values",
        "python": "def median(xs):\n    values = list(xs)\n    for i in range(len(values)):\n        for j in range(len(values) - 1):\n            if values[j] > values[j + 1]:\n                values[j], values[j + 1] = values[j + 1], values[j]\n    return values[len(values) // 2]",
        "heldout_aggregation": "def count_positive(xs):\n    total = 0\n    for value in xs:\n        if value > 0:\n            total += 1\n    return total",
        "heldout_indexing": "def at_or_none(xs, index):\n    if index < 0 or index >= len(xs):\n        return None\n    return xs[index]",
        "heldout_branching": "def clamp(value, low, high):\n    if value < low:\n        return low\n    if value > high:\n        return high\n    return value",
    }
    policy = json.loads((SOURCE / "suite" / "policy.json").read_text())
    rows = []
    for position, case in enumerate(cases):
        raw_request, transformed = request_bytes(case, policy, transform)
        input_ids = [236823, 1000 + position, 2000 + position]
        output_ids = [3000 + position, 4000 + position]
        result = score(case, raw_request, safe[case["case_id"]], adapter, scorer)
        rows.append({"case_id": case["case_id"], "request_sha256": hashlib.sha256(raw_request.encode()).hexdigest(), "request_transform": {"transformed": transformed.transformed, "original_sha256": transformed.original_sha256, "transformed_sha256": transformed.transformed_sha256}, "input_ids": input_ids, "input_ids_sha256": digest(input_ids), "transformers": {"output_ids": output_ids, "output_text": safe[case["case_id"]], "finish_reason": "fixture", **result}, "sglang": {"output_ids": output_ids, "output_text": safe[case["case_id"]], "finish_reason": "fixture", **result}, "input_token_ids_equal": True, "output_token_ids_equal": True, "first_output_divergence": None})
    write(output_dir / "LOCAL_VALIDATION.json", {"classification": "gemma4_generation_equivalence_local_validation", "pass": all(row["transformers"]["score"] == row["sglang"]["score"] == 1.0 for row in rows), "bindings": checks, "suite_sha256": manifest["suite_sha256"], "cases": rows, "provider_spend_usd": 0.0, "fixture_only": True})
    return rows, checks, manifest


def precreate(output_dir):
    rows, checks, manifest = local_fixture(output_dir)
    terminal = {"classification": "gemma4_sglang_transformers_generation_equivalence_precreate_terminal", "pass": True, "typed_terminal": "ready_for_director_bench_request", "frozen_bindings": checks, "suite_sha256": manifest["suite_sha256"], "case_ids": list(CASES), "local_validation_sha256": sha(output_dir / "LOCAL_VALIDATION.json"), "runner_sha256": sha(PROJECT / "generation_equivalence_runner.py"), "provider_spend_usd": 0.0, "provider_create_authority": "director_only", "bench_release_state": "not_claimed_pool_empty", "next_execution": "Run generate on one claimed nvidia-h200-sxm bench with the exact image/checkpoint; preserve raw token IDs and scorer output."}
    write(output_dir / "TERMINAL.json", terminal)
    request = {"classification": "director_bench_request", "project": PROJECT.name, "typed_precreate_terminal": "artifacts/precreate-terminal/TERMINAL.json", "terminal_sha256": sha(output_dir / "TERMINAL.json"), "accelerator": "nvidia-h200-sxm", "disk_gib": 250, "image": json.loads((PROJECT / "BINDINGS.json").read_text())["runtime"]["image"], "max_provider_minutes": 70, "max_wall_minutes": 90, "spend_cap_usd": 3.25, "requested_state": "available_shared_bench", "provider_create_owner": "director", "researcher_must_not_create_provider": True}
    write(PROJECT / "artifacts" / "director-bench" / "BENCH_REQUEST.json", request)
    return terminal


def post(base, body):
    encoded = canonical(body).encode()
    request = urllib.request.Request(base.rstrip("/") + "/generate", data=encoded, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=600) as response:
        raw = response.read()
    return json.loads(raw), {"request": body, "request_sha256": hashlib.sha256(encoded).hexdigest(), "response_sha256": hashlib.sha256(raw).hexdigest(), "response": raw.decode("utf-8", "replace")}


def generate(checkpoint, base, output_dir):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    bindings, manifest, cases, checks = frozen()
    adapter, scorer = load_module("bound_adapter", ADAPTER), load_module("bound_scorer", SCORER)
    transform = load_module("safe_code_contract", SOURCE / "safe_code_contract.py")
    policy = json.loads((SOURCE / "suite" / "policy.json").read_text())
    tokenizer = AutoTokenizer.from_pretrained(checkpoint)
    model = AutoModelForCausalLM.from_pretrained(checkpoint, torch_dtype=torch.bfloat16).cuda().eval()
    eos_ids = tokenizer.eos_token_id if isinstance(tokenizer.eos_token_id, list) else [tokenizer.eos_token_id]
    eos_ids = [value for value in eos_ids if isinstance(value, int)]
    rows, transformer_raw, sglang_raw = [], [], []
    for case in cases:
        raw_request, transformed = request_bytes(case, policy, transform)
        request = json.loads(raw_request)
        ids = tokenizer.apply_chat_template(request["messages"], tokenize=True, add_generation_prompt=True)
        if hasattr(ids, "keys"):
            ids = ids["input_ids"]
        if hasattr(ids, "tolist"):
            ids = ids.tolist()
        if isinstance(ids, list) and len(ids) == 1 and isinstance(ids[0], list):
            ids = ids[0]
        if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
            raise ValueError("tokenizer did not produce token IDs")
        input_tensor = torch.tensor([ids], device="cuda")
        started = time.monotonic()
        with torch.inference_mode():
            generated = model.generate(input_tensor, do_sample=False, max_new_tokens=128, eos_token_id=eos_ids or None, pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id)
        direct_ids = generated[0, len(ids):].tolist()
        direct_text = tokenizer.decode(direct_ids, skip_special_tokens=True)
        direct = {"output_ids": direct_ids, "output_text": direct_text, "finish_reason": "eos" if direct_ids and direct_ids[-1] in eos_ids else "length", "elapsed_seconds": time.monotonic() - started}
        direct.update(score(case, raw_request, direct_text, adapter, scorer))
        transformer_raw.append({"case_id": case["case_id"], "input_ids": ids, "raw_request": raw_request, "result": direct})
        body = {"input_ids": ids, "sampling_params": {"temperature": 0.0, "top_p": 1.0, "max_new_tokens": 128, "stop_token_ids": eos_ids}, "return_logprob": True, "add_special_tokens": False}
        started = time.monotonic()
        response, raw = post(base, body)
        meta = response.get("meta_info") or {}
        output_ids = meta.get("output_ids") or response.get("output_ids")
        if not isinstance(output_ids, list) or not all(isinstance(value, int) for value in output_ids):
            raise ValueError("SGLang response omitted native output token IDs")
        sglang = {"output_ids": output_ids, "output_text": response.get("text"), "finish_reason": meta.get("finish_reason", {}).get("type") if isinstance(meta.get("finish_reason"), dict) else meta.get("finish_reason", "unknown"), "elapsed_seconds": time.monotonic() - started}
        if not isinstance(sglang["output_text"], str):
            raise ValueError("SGLang response omitted output text")
        sglang.update(score(case, raw_request, sglang["output_text"], adapter, scorer))
        sglang_raw.append({"case_id": case["case_id"], "input_ids": ids, "raw_request": raw_request, "http": raw, "result": sglang})
        rows.append({"case_id": case["case_id"], "request_sha256": hashlib.sha256(raw_request.encode()).hexdigest(), "request_transform": {"transformed": transformed.transformed, "original_sha256": transformed.original_sha256, "transformed_sha256": transformed.transformed_sha256}, "input_ids": ids, "input_ids_sha256": digest(ids), "transformers": direct, "sglang": sglang, "input_token_ids_equal": True, "output_token_ids_equal": direct_ids == output_ids, "first_output_divergence": first_divergence(direct_ids, output_ids)})
    write(output_dir / "transformers_raw.json", transformer_raw)
    write(output_dir / "sglang_raw.json", sglang_raw)
    shared_failure = rows[0]["transformers"]["score"] == 0.0 and rows[0]["sglang"]["score"] == 0.0
    transformers_only_pass = rows[0]["transformers"]["score"] == 1.0 and rows[0]["sglang"]["score"] == 0.0
    decision = "shared_primary_failure_close_model_quality_branch" if shared_failure else "transformers_only_primary_pass_deep_first_divergence" if transformers_only_pass else "both_primary_pass_request_path_discrepancy" if rows[0]["transformers"]["score"] == rows[0]["sglang"]["score"] == 1.0 else "mixed_or_transformers_failure_review_raw_artifacts"
    terminal = {"classification": "gemma4_sglang_transformers_generation_equivalence_terminal", "frozen_bindings": checks, "suite_sha256": manifest["suite_sha256"], "case_ids": list(CASES), "cases": rows, "raw_artifact_sha256": {"transformers": sha(output_dir / "transformers_raw.json"), "sglang": sha(output_dir / "sglang_raw.json")}, "branch_decision": decision, "provider_spend_usd": None, "bench_release_state": "owner_must_update_pool_and_release_after_result"}
    write(output_dir / "TERMINAL.json", terminal)
    return terminal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("validate", "precreate", "generate"))
    parser.add_argument("--output-dir", type=Path, default=PROJECT / "artifacts" / "precreate-terminal")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--sglang-base")
    args = parser.parse_args()
    if args.mode == "validate":
        local_fixture(args.output_dir)
        print(sha(args.output_dir / "LOCAL_VALIDATION.json"))
    elif args.mode == "precreate":
        print(canonical(precreate(args.output_dir)))
    else:
        if args.checkpoint is None or not args.sglang_base:
            raise SystemExit("generate requires --checkpoint and --sglang-base")
        print(canonical(generate(args.checkpoint, args.sglang_base, args.output_dir)))


if __name__ == "__main__":
    main()
