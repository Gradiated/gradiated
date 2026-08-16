#!/usr/bin/env python3
"""Capture one frozen V2 development split from a running vLLM server."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import urllib.request
from pathlib import Path

MODEL = "glm-4.7-flash-bf16"
REQUIRED = ("raw-response-bytes", "normalized-output-bytes", "transform-decisions", "responses.jsonl", "runtime-evidence.json", "identity-manifest.json", "capture-result.json")

def canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()

def token_sequence_sha256(token_ids):
    if not isinstance(token_ids, list) or not all(isinstance(token_id, int) for token_id in token_ids):
        raise RuntimeError("returned prompt token IDs malformed")
    return hashlib.sha256(canon({"serialization": "json_utf8_canonical_array_of_int32_token_ids_v1", "token_ids": token_ids})).hexdigest()

def post(endpoint, payload):
    request = urllib.request.Request("http://127.0.0.1:30000" + endpoint, data=canon(payload), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=300) as response:
        raw = response.read()
    value = json.loads(raw)
    if not isinstance(value, dict) or "error" in value:
        raise RuntimeError("vLLM returned an error object")
    return value, raw

def messages(case):
    if case["category"] == "long_context_retrieval":
        return [{"role": "user", "content": case["synthetic_context"] + "\n\n" + case["prompt"]}]
    if case["category"] == "multi_turn_continuation":
        return case["history"] + [{"role": "user", "content": case["prompt"]}]
    return [{"role": "user", "content": case["prompt"]}]

def capture_request(case):
    if case["category"] == "teacher_forced_loss":
        return {"endpoint": "/v1/completions", "payload": {"model": MODEL, "prompt": case["teacher_forced_text"], "temperature": 0, "max_tokens": 1, "prompt_logprobs": 1, "return_token_ids": True}}
    return {"endpoint": "/v1/chat/completions", "payload": {"model": MODEL, "messages": messages(case), "temperature": 0, "top_p": 1, "max_tokens": 256, "seed": 470200, "chat_template_kwargs": {"enable_thinking": False}}}

def capture(case):
    request = capture_request(case)
    return post(request["endpoint"], request["payload"])

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--suite-sha256", required=True)
    args = parser.parse_args()
    cases = [json.loads(line) for line in args.suite.read_text().splitlines()]
    raw_rows, responses, decisions = [], [], []
    for case in cases:
        value, raw = capture(case)
        raw_rows.append(raw)
        raw_hash = hashlib.sha256(raw).hexdigest()
        if case["category"] == "teacher_forced_loss":
            choice = value["choices"][0]
            token_ids, rows = choice.get("prompt_token_ids"), choice.get("prompt_logprobs")
            if not isinstance(token_ids, list) or not isinstance(rows, list) or len(token_ids) != len(rows):
                raise RuntimeError("prompt logprob evidence missing or misaligned")
            scored = []
            for token_id, row in zip(token_ids, rows):
                if row is None: continue
                item = row.get(str(token_id), row.get(token_id)) if isinstance(row, dict) else None
                if not isinstance(item, dict) or not isinstance(item.get("logprob"), (int, float)) or not math.isfinite(float(item["logprob"])):
                    raise RuntimeError("prompt logprob token evidence malformed")
                scored.append({"token_id": int(token_id), "logprob": float(item["logprob"])})
            if len(scored) < int(case["scorer"]["minimum_scored_tokens"]): raise RuntimeError("too few prompt logprob tokens")
            runtime_ids = [int(token_id) for token_id in token_ids]
            output = {"source": "runtime_teacher_forced_input_token_logprobs", "returned_prompt_token_ids": runtime_ids, "token_sequence_sha256": token_sequence_sha256(runtime_ids), "input_token_logprobs": scored}
            mode = "completion_prompt_logprobs"
        else:
            choice = value["choices"][0]
            message = choice.get("message", {})
            output = message.get("content")
            if output is None and message.get("tool_calls"):
                fn = message["tool_calls"][0]["function"]
                output = json.dumps({"name": fn["name"], "arguments": json.loads(fn["arguments"])}, sort_keys=True, separators=(",", ":"))
            if not isinstance(output, str) or choice.get("finish_reason") == "length": raise RuntimeError("invalid or truncated chat response")
            mode = "chat_completion"
        responses.append({"case_id": case["case_id"], "output": output})
        decisions.append({"case_id": case["case_id"], "mode": mode, "raw_response_sha256": raw_hash, "request": capture_request(case), "finish_reason": choice.get("finish_reason")})
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "raw-response-bytes").write_bytes(b"\n".join(raw_rows) + b"\n")
    (args.output / "normalized-output-bytes").write_bytes(b"".join(canon(row) + b"\n" for row in responses))
    (args.output / "responses.jsonl").write_bytes((args.output / "normalized-output-bytes").read_bytes())
    (args.output / "transform-decisions").write_text(json.dumps(decisions, sort_keys=True) + "\n")
    (args.output / "runtime-evidence.json").write_text(json.dumps({"schema_version": 2, "cases": decisions, "raw_response_sha256": hashlib.sha256((args.output / "raw-response-bytes").read_bytes()).hexdigest()}, sort_keys=True) + "\n")
    (args.output / "identity-manifest.json").write_text(json.dumps({"model_revision": args.revision, "suite_sha256": args.suite_sha256, "model": MODEL}, sort_keys=True) + "\n")
    result = {"schema_version": 1, "capture_pass": True, "case_count": len(cases), "required_artifacts": list(REQUIRED), "model_revision": args.revision}
    (args.output / "capture-result.json").write_text(json.dumps(result, sort_keys=True) + "\n")

if __name__ == "__main__":
    main()
