#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.request


ROOT = pathlib.Path("/home/glmrunner/gemma4-h200-ngram-token-trace")
INPUT = ROOT / "input"
OUT = ROOT / "artifacts"
CHECKPOINT = "/home/glmrunner/gemma4-async-result-pipeline/checkpoint"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MODEL = "google/gemma-4-31B-it"
BASE = ["--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint", "--served-model-name", MODEL, "--dtype", "bfloat16", "--quantization", "fp8", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--context-length", "5000", "--max-running-requests", "32", "--mem-fraction-static", "0.85", "--enable-metrics", "--skip-server-warmup", "--enable-dynamic-chunking", "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32", "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1", "--num-continuous-decode-steps", "1", "--triton-attention-num-kv-splits", "8", "--tool-call-parser", "gemma4"]


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def wait(port: int) -> None:
    for _ in range(240):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=5) as response:
                if MODEL in response.read().decode():
                    return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError(f"model_readiness_timeout:{port}")


def post(port: int, body: dict) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/v1/chat/completions", data=json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=180) as response:
        return json.loads(response.read())


def cases() -> list[dict]:
    text = [{"id": "ordinary", "body": {"model": MODEL, "messages": [{"role": "user", "content": "State the capital of France in one word."}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}}, {"id": "stop_length", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Reply exactly with OK."}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}}, {"id": "cached_prefix", "body": {"model": MODEL, "messages": [{"role": "system", "content": "You are concise. Reply with only the requested word."}, {"role": "user", "content": "What color is a clear daytime sky?"}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}}, {"id": "repeated_pattern", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Continue this pattern with four letters: ababab"}], "temperature": 0, "seed": 20260718, "max_tokens": 16, "return_logprob": True, "top_logprobs_num": 1}}]
    tools = [{"type": "function", "function": {"name": "lookup_user", "description": "Look up a user by id.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}, {"type": "function", "function": {"name": "get_user_details", "description": "Get details for a user.", "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}, "required": ["user_id"]}}}]
    return text + [{"id": "single_tool", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Call lookup_user for user_id demo_user."}], "tools": tools, "tool_choice": "required", "temperature": 0, "seed": 20260718, "max_tokens": 128}}, {"id": "multi_tool", "body": {"model": MODEL, "messages": [{"role": "user", "content": "Call lookup_user for user_id demo_user, then get_user_details for user_id demo_user. Use both tools in that order."}], "tools": tools, "tool_choice": "required", "temperature": 0, "seed": 20260718, "max_tokens": 128}}]


def normalize(response: dict) -> dict:
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    calls = []
    for call in message.get("tool_calls") or []:
        function = call.get("function") or {}
        calls.append({"name": function.get("name"), "arguments": function.get("arguments"), "type": call.get("type"), "index": call.get("index")})
    return {"content": message.get("content"), "tool_calls": calls, "finish_reason": choice.get("finish_reason"), "usage": response.get("usage")}


def launch(arm: str, ngram: bool) -> str:
    name = f"gemma-ngram-token-trace-{arm}"
    run(["sudo", "docker", "rm", "-f", name])
    events = f"/work/artifacts/{arm}-trace-events.jsonl"
    env = ["-e", "PYTHONPATH=/work/input:/sgl-workspace/sglang/python", "-e", f"TOKEN_TRACE_EVENTS={events}", "-e", f"FP8_MODULE_AUDIT=/work/artifacts/{arm}.modules.jsonl", "-e", f"FP8_CONSUMER_AUDIT=/work/artifacts/{arm}.consumers.jsonl", "-e", f"FP8_RUNTIME_AUDIT=/work/artifacts/{arm}.runtime.json", "-e", f"FP8_STACK_MODULE_AUDIT=/work/artifacts/{arm}.stack-modules.jsonl", "-e", f"FP8_STACK_CONSUMER_AUDIT=/work/artifacts/{arm}.stack-consumers.jsonl"]
    args = BASE + ["--port", "30000"] + (["--speculative-algorithm", "NGRAM"] if ngram else [])
    result = run(["sudo", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network", "host", "-v", f"{ROOT}:/work", "-v", f"{INPUT}:/work/input:ro", "-v", f"{CHECKPOINT}:/work/checkpoint:ro", *env, IMAGE, "python3", "/work/input/endpoint_entrypoint.py", *args])
    atomic(OUT / f"{arm}-launch.json", {"args": args, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "name": name})
    if result.returncode:
        raise RuntimeError(f"launch_failed:{arm}:{result.stderr[-800:]}")
    wait(30000)
    return name


def capture(arm: str) -> list[dict]:
    rows = []
    work = cases()
    for case in work:
        response = post(30000, case["body"])
        rows.append({"mode": "serial", "id": case["id"], "request": case["body"], "response": response, "normalized": normalize(response)})
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        responses = list(executor.map(lambda case: post(30000, case["body"]), work[:4]))
    for case, response in zip(work[:4], responses):
        rows.append({"mode": "batched", "id": case["id"], "request": case["body"], "response": response, "normalized": normalize(response)})
    atomic(OUT / f"{arm}-api-rows.json", rows)
    for _ in range(30):
        trace_path = OUT / f"{arm}-trace-events.jsonl"
        if trace_path.exists() and sum(1 for line in trace_path.read_text().splitlines() if 'post_generation_pre_parser_final' in line) == 10:
            return rows
        time.sleep(1)
    raise RuntimeError(f"trace_final_rows_missing:{arm}")


def read_events(arm: str) -> list[dict]:
    return [json.loads(line) for line in (OUT / f"{arm}-trace-events.jsonl").read_text().splitlines() if line]


def final_events(events: list[dict]) -> list[dict]:
    return [event for event in events if event["stage"] == "post_generation_pre_parser_final"]


def scheduler_sequences(events: list[dict]) -> dict[str, list[int]]:
    value: dict[str, list[int]] = {}
    for event in events:
        if event["stage"] == "scheduler_to_detokenizer":
            value.setdefault(event["rid"], []).extend(event["scheduler_output_ids_delta"])
    return value


def canonical_final(events: list[dict]) -> list[dict]:
    scheduler = scheduler_sequences(events)
    rows = []
    for event in final_events(events):
        item = dict(event)
        item["scheduler_output_ids_from_deltas"] = scheduler.get(event["rid"], [])
        rows.append(item)
    return sorted(rows, key=lambda item: json.dumps({key: value for key, value in item.items() if key not in {"rid", "at_monotonic"}}, sort_keys=True))


def token_projection(rows: list[dict]) -> list[dict]:
    return [{key: row[key] for key in ("scheduler_output_ids", "emitted_token_ids", "scheduler_output_ids_from_deltas", "parser_input_utf8_hex", "finish_reason")} for row in rows]


def semantics_projection(rows: list[dict]) -> list[dict]:
    return [{key: row["normalized"][key] for key in ("content", "tool_calls", "finish_reason")} for row in rows]


def empty_proof() -> dict:
    compute = run(["nvidia-smi", "--query-compute-apps=pid,used_memory", "--format=csv,noheader"])
    gpu = run(["nvidia-smi", "--query-gpu=memory.used,utilization.gpu", "--format=csv,noheader"])
    return {"compute_processes": compute.stdout.strip(), "compute_query_returncode": compute.returncode, "gpu": gpu.stdout.strip(), "zero": not compute.stdout.strip() and gpu.stdout.strip().startswith("0 MiB")}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    reconstructed = OUT / "control-post-reconstructed.json"
    if reconstructed.exists():
        control_rows = json.loads((OUT / "control-api-rows.json").read_text())
        control_final = json.loads(reconstructed.read_text())
        for row in control_final:
            row["scheduler_output_ids_from_deltas"] = row["scheduler_output_ids"]
        candidate = launch("candidate", True)
        atomic(OUT / "INVOCATION_STATE.json", {"control_science_started": True, "candidate_science_started": True, "control_trace_consumer_reconstructed": True})
        candidate_rows = capture("candidate")
        candidate_events = read_events("candidate")
        atomic(OUT / "CANDIDATE_TRACE_STAGE.json", {"api_rows": candidate_rows, "events": candidate_events})
        candidate_final = canonical_final(candidate_events)
        scheduler_complete = all(row["scheduler_output_ids"] == row["scheduler_output_ids_from_deltas"] for row in control_final + candidate_final)
        token_exact = token_projection(sorted(control_final, key=lambda item: json.dumps(item, sort_keys=True))) == token_projection(candidate_final)
        api_exact = semantics_projection(control_rows) == semantics_projection(candidate_rows)
        accounting_exact = all(row["completion_counter"] == row["completion_counter_inputs"]["emitted_token_count"] for row in control_final + candidate_final) and [row["normalized"]["usage"] for row in control_rows] == [row["normalized"]["usage"] for row in candidate_rows]
        atomic(OUT / "TERMINAL.json", {"schema_version": 1, "classification": "server_side_token_trace_after_control_consumer_repair", "control_final_rows": len(control_final), "candidate_final_rows": len(candidate_final), "scheduler_delta_reconstructs_final": scheduler_complete, "exact_scheduler_and_emitted_tokens": token_exact, "exact_normalized_api_payload": api_exact, "exact_completion_accounting": accounting_exact, "pass": scheduler_complete and token_exact and api_exact and accounting_exact, "candidate_scientific_invocation_started": True})
        run(["sudo", "docker", "rm", "-f", candidate])
        return
    atomic(OUT / "INVOCATION_STATE.json", {"control_science_started": False, "candidate_science_started": False})
    control = launch("control", False)
    state = json.loads((OUT / "INVOCATION_STATE.json").read_text()); state["control_science_started"] = True; atomic(OUT / "INVOCATION_STATE.json", state)
    control_rows = capture("control")
    control_events = read_events("control")
    atomic(OUT / "CONTROL_TRACE_STAGE.json", {"api_rows": control_rows, "events": control_events})
    run(["sudo", "docker", "rm", "-f", control]); time.sleep(3)
    zero = empty_proof(); atomic(OUT / "ZERO_HBM_AFTER_CONTROL_TRACE.json", zero)
    if not zero["zero"]:
        raise RuntimeError(f"control_cleanup_not_zero:{zero}")
    candidate = launch("candidate", True)
    state = json.loads((OUT / "INVOCATION_STATE.json").read_text()); state["candidate_science_started"] = True; atomic(OUT / "INVOCATION_STATE.json", state)
    candidate_rows = capture("candidate")
    candidate_events = read_events("candidate")
    atomic(OUT / "CANDIDATE_TRACE_STAGE.json", {"api_rows": candidate_rows, "events": candidate_events})
    control_final, candidate_final = canonical_final(control_events), canonical_final(candidate_events)
    scheduler_complete = all(row["scheduler_output_ids"] == row["scheduler_output_ids_from_deltas"] for row in control_final + candidate_final)
    token_exact = token_projection(control_final) == token_projection(candidate_final)
    api_exact = semantics_projection(control_rows) == semantics_projection(candidate_rows)
    accounting_exact = all(row["completion_counter"] == row["completion_counter_inputs"]["emitted_token_count"] for row in control_final + candidate_final) and [row["normalized"]["usage"] for row in control_rows] == [row["normalized"]["usage"] for row in candidate_rows]
    terminal = {"schema_version": 1, "classification": "server_side_token_trace", "control_final_rows": len(control_final), "candidate_final_rows": len(candidate_final), "scheduler_delta_reconstructs_final": scheduler_complete, "exact_scheduler_and_emitted_tokens": token_exact, "exact_normalized_api_payload": api_exact, "exact_completion_accounting": accounting_exact, "pass": scheduler_complete and token_exact and api_exact and accounting_exact, "candidate_scientific_invocation_started": True}
    atomic(OUT / "TERMINAL.json", terminal)
    run(["sudo", "docker", "rm", "-f", candidate])


if __name__ == "__main__":
    main()
