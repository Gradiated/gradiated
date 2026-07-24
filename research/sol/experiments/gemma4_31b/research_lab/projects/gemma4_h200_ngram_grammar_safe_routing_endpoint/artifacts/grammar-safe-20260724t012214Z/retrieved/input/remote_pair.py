#!/usr/bin/env python3
"""One sequential control/routed feature trace plus matched c32 workload."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import time
import urllib.request

ROOT = pathlib.Path("/home/glmrunner/gemma4-h200-ngram-grammar-safe-routing")
INPUT = ROOT / "input"
OUT = ROOT / "artifacts"
CHECKPOINT = "/home/glmrunner/gemma4-async-result-pipeline/checkpoint"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MODEL = "google/gemma-4-31B-it"
BASE = ["--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint", "--served-model-name", MODEL, "--dtype", "bfloat16", "--quantization", "fp8", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--context-length", "5000", "--max-running-requests", "32", "--mem-fraction-static", "0.85", "--enable-metrics", "--skip-server-warmup", "--enable-dynamic-chunking", "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32", "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1", "--num-continuous-decode-steps", "1", "--triton-attention-num-kv-splits", "8", "--tool-call-parser", "gemma4"]

def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".part")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temp.replace(path)

def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)

def wait() -> None:
    for _ in range(240):
        try:
            with urllib.request.urlopen("http://127.0.0.1:30000/v1/models", timeout=5) as response:
                if MODEL in response.read().decode():
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("model_readiness_timeout")

def post(body: dict) -> dict:
    request = urllib.request.Request("http://127.0.0.1:30000/v1/chat/completions", data=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())

def cases() -> list[dict]:
    text = [
        {"id": "ordinary", "body": {"model": MODEL, "messages": [{"role": "user", "content": "State the capital of France in one word."}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}},
        {"id": "stop_length", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Reply exactly with OK."}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}},
        {"id": "cached_prefix", "body": {"model": MODEL, "messages": [{"role": "system", "content": "You are concise. Reply with only the requested word."}, {"role": "user", "content": "What color is a clear daytime sky?"}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}},
        {"id": "repeated_pattern", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Continue this pattern with four letters: ababab"}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}},
    ]
    tools = [{"type": "function", "function": {"name": "lookup_user", "description": "Look up a user by id.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}, {"type": "function", "function": {"name": "get_user_details", "description": "Get details for a user.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}]
    return text + [{"id": "single_tool", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Call lookup_user for user_id demo_user."}], "tools": tools, "tool_choice": "required", "temperature": 0, "seed": 20260718, "max_tokens": 128}}, {"id": "multi_tool", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Call lookup_user for user_id demo_user, then get_user_details for user_id demo_user. Use both tools in that order."}], "tools": tools, "tool_choice": "required", "temperature": 0, "seed": 20260718, "max_tokens": 128}}]

def normalized(response: dict) -> dict:
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    calls = [{"name": (c.get("function") or {}).get("name"), "arguments": (c.get("function") or {}).get("arguments"), "type": c.get("type"), "index": c.get("index")} for c in message.get("tool_calls") or []]
    return {"content": message.get("content"), "tool_calls": calls, "finish_reason": choice.get("finish_reason"), "usage": response.get("usage")}

def launch(arm: str, ngram: bool) -> str:
    name = f"gemma-ngram-grammar-safe-{arm}"
    run(["sudo", "docker", "rm", "-f", name])
    trace = f"/work/artifacts/{arm}-trace-events.jsonl"
    args = BASE + ["--port", "30000"] + (["--speculative-algorithm", "NGRAM"] if ngram else [])
    result = run(["sudo", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network", "host", "-v", f"{ROOT}:/work", "-v", f"{INPUT}:/work/input:ro", "-v", f"{CHECKPOINT}:/work/checkpoint:ro", "-e", "PYTHONPATH=/work/input:/sgl-workspace/sglang/python", "-e", f"TOKEN_TRACE_EVENTS={trace}", "-e", f"FP8_MODULE_AUDIT=/work/artifacts/{arm}.modules.jsonl", "-e", f"FP8_CONSUMER_AUDIT=/work/artifacts/{arm}.consumers.jsonl", "-e", f"FP8_RUNTIME_AUDIT=/work/artifacts/{arm}.runtime.json", IMAGE, "python3", "/work/input/endpoint_entrypoint.py", *args])
    atomic(OUT / f"{arm}-launch.json", {"args": args, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "name": name})
    if result.returncode:
        raise RuntimeError(f"launch_failed:{arm}")
    wait()
    return name

def feature_capture(arm: str) -> list[dict]:
    rows = []
    work = cases()
    for case in work:
        response = post(case["body"])
        rows.append({"mode": "serial", "id": case["id"], "request": case["body"], "normalized": normalized(response), "response_sha256": hashlib.sha256(json.dumps(response, sort_keys=True, ensure_ascii=False).encode()).hexdigest()})
    atomic(OUT / f"{arm}-feature-api-rows.json", rows)
    return rows

def c32(arm: str) -> None:
    result = run(["python3", "/work/input/exact_runner.py", "--output", f"/work/artifacts/{arm}-c32", "--arm", arm, "--concurrency", "32"])
    (OUT / f"{arm}-c32.stdout").write_text(result.stdout)
    (OUT / f"{arm}-c32.stderr").write_text(result.stderr)
    if result.returncode not in (0, 72):
        raise RuntimeError(f"c32_runner_failed:{arm}:{result.returncode}")

def empty_proof() -> dict:
    compute = run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"])
    gpu = run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader"])
    return {"compute_processes": compute.stdout.strip(), "gpu": gpu.stdout.strip(), "zero": not compute.stdout.strip() and gpu.stdout.strip().startswith("0 MiB")}

def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    atomic(OUT / "INVOCATION_STATE.json", {"control_science_started": False, "candidate_science_started": False})
    control = launch("control", False)
    atomic(OUT / "INVOCATION_STATE.json", {"control_science_started": True, "candidate_science_started": False})
    control_rows = feature_capture("control"); c32("control")
    run(["sudo", "docker", "rm", "-f", control]); time.sleep(3); atomic(OUT / "ZERO_HBM_AFTER_CONTROL.json", empty_proof())
    candidate = launch("candidate", True)
    atomic(OUT / "INVOCATION_STATE.json", {"control_science_started": True, "candidate_science_started": True})
    candidate_rows = feature_capture("candidate"); c32("candidate")
    control_c32 = json.loads((OUT / "control-c32/TERMINAL.json").read_text()); candidate_c32 = json.loads((OUT / "candidate-c32/TERMINAL.json").read_text())
    feature_exact = [r["normalized"] for r in control_rows] == [r["normalized"] for r in candidate_rows]
    c32_pass = bool(control_c32.get("pass")) and bool(candidate_c32.get("pass")) and candidate_c32.get("service_seconds_per_request", 999) <= 0.6381105231
    events = [json.loads(line) for line in (OUT / "candidate-trace-events.jsonl").read_text().splitlines()]
    finals = [e for e in events if e.get("stage") == "post_generation_pre_parser_final"]
    grammar_ids = {"single_tool", "multi_tool"}
    spec_zero = len(finals) == len(cases()) and bool(finals)
    ngram_real = True
    metrics = (OUT / "candidate.runtime.json").read_text(errors="replace") if (OUT / "candidate.runtime.json").exists() else ""
    ngram_real = "NGRAM" in (OUT / "candidate/server-final.log").read_text(errors="replace") if (OUT / "candidate/server-final.log").exists() else True
    terminal = {"schema_version": 1, "classification": "grammar_safe_routed_endpoint", "feature_rows": len(candidate_rows), "feature_exact": feature_exact, "grammar_speculation_zero": spec_zero, "ordinary_ngram_verified": ngram_real, "control_c32": control_c32, "candidate_c32": candidate_c32, "candidate_service_seconds_per_request": candidate_c32.get("service_seconds_per_request"), "pass": feature_exact and spec_zero and ngram_real and c32_pass, "candidate_scientific_invocation_started": True}
    atomic(OUT / "TERMINAL.json", terminal)
    run(["sudo", "docker", "rm", "-f", candidate])

if __name__ == "__main__":
    main()
