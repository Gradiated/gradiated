#!/usr/bin/env python3
"""One sequential, matched exact-c32 stock/candidate endpoint pair."""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import pathlib
import subprocess
import time
import urllib.request


MODEL = "google/gemma-4-31B-it"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
PROMPT_TOKENS, COMMON_TOKENS, OUTPUT_TOKENS, CONCURRENCY = 4214, 535, 358, 32


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def tokens(label: str, count: int) -> list[int]:
    values: list[int] = []
    index = 0
    while len(values) < count:
        digest = hashlib.sha256(f"gemma4-fixed-floor-c32|{label}|{index}".encode()).digest()
        values.extend(1000 + int.from_bytes(digest[offset:offset + 4], "big") % 249000 for offset in range(0, 32, 4))
        index += 1
    return values[:count]


def workload() -> list[dict]:
    prefix = tokens("shared-prefix", COMMON_TOKENS)
    requests = []
    for index in range(CONCURRENCY):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        requests.append({"model": MODEL, "prompt": prefix + suffix, "max_tokens": OUTPUT_TOKENS, "min_tokens": OUTPUT_TOKENS, "ignore_eos": True, "temperature": 0, "seed": 20260730, "stream": True, "stream_options": {"include_usage": True}, "return_token_ids": True, "add_special_tokens": False})
    return requests


def request(url: str, body: dict) -> tuple[bytes, dict]:
    started = time.monotonic()
    chunks: list[bytes] = []
    ids: list[int] = []
    usage: dict = {}
    first = None
    error = None
    try:
        query = urllib.request.Request(url + "/v1/completions", canonical(body), {"Content-Type": "application/json"})
        with urllib.request.urlopen(query, timeout=900) as response:
            for raw in response:
                chunks.append(raw)
                if raw.startswith(b"data: ") and raw.strip() != b"data: [DONE]":
                    item = json.loads(raw[6:]); choice = (item.get("choices") or [{}])[0]
                    ids.extend(choice.get("token_ids") or []); usage = item.get("usage") or usage
                    if choice.get("text") and first is None: first = time.monotonic()
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
    ended = time.monotonic(); raw = b"".join(chunks)
    return raw, {"wall_seconds": ended-started, "ttft_seconds": None if first is None else first-started, "error": error, "token_ids": ids, "usage": usage, "request_sha256": hashlib.sha256(canonical(body)).hexdigest()}


def wait_ready(name: str, url: str) -> None:
    for _ in range(180):
        state = subprocess.run(["sudo", "-n", "docker", "inspect", "-f", "{{.State.Running}}", name], text=True, capture_output=True, check=False, timeout=20)
        if state.returncode or state.stdout.strip() != "true": raise RuntimeError("server_exited_before_ready:" + name)
        try:
            if MODEL in urllib.request.urlopen(url + "/v1/models", timeout=5).read().decode(): return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError("server_readiness_timeout:" + name)


def arm(project: pathlib.Path, checkpoint: pathlib.Path, root: pathlib.Path, arm_name: str, candidate: bool, port: int) -> dict:
    arm_root = root / arm_name
    if arm_root.exists(): raise RuntimeError("existing_arm_root:" + str(arm_root))
    arm_root.mkdir(parents=True)
    name, url = f"gemma4-fixed-floor-{arm_name}", f"http://127.0.0.1:{port}"
    mounts = ["-v", f"{project}:/work/project:ro", "-v", f"{checkpoint}:/work/checkpoint:ro", "-v", f"{arm_root}:/work/output"]
    if candidate: mounts += ["-v", f"{project}/endpoint_candidate_gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro"]
    command = ["sudo", "-n", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network=host", *mounts, "-e", "PYTHONPATH=/work/project:/sgl-workspace/sglang/python", "-e", "FIXED_FLOOR_CROSSOP_AUDIT=/work/output/candidate-path.jsonl", IMAGE, "python3", "-m", "sglang.launch_server", "--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint", "--served-model-name", MODEL, "--dtype", "bfloat16", "--quantization", "fp8", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--port", str(port), "--context-length", "5000", "--max-running-requests", "32", "--mem-fraction-static", "0.85", "--skip-server-warmup", "--enable-dynamic-chunking", "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32", "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1", "--num-continuous-decode-steps", "1", "--tool-call-parser", "gemma4"]
    launched = subprocess.run(command, text=True, capture_output=True, check=False, timeout=120); atomic(arm_root / "launch.json", {"returncode": launched.returncode, "stderr": launched.stderr, "candidate": candidate})
    if launched.returncode: raise RuntimeError("server_launch_failed:" + arm_name)
    try:
        wait_ready(name, url); bodies = workload(); started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool: results = list(pool.map(lambda body: request(url, body), bodies))
        elapsed = time.monotonic() - started; rows=[]
        for index,(raw,row) in enumerate(results): (arm_root / f"response-{index:02d}.sse").write_bytes(raw); rows.append(row)
        valid = all(not row["error"] and row["usage"].get("prompt_tokens") == PROMPT_TOKENS and row["usage"].get("completion_tokens") == OUTPUT_TOKENS and len(row["token_ids"]) == OUTPUT_TOKENS for row in rows)
        terminal={"schema_version":1,"arm":arm_name,"pass":valid,"complete_requests":sum(not r["error"] for r in rows),"service_seconds_per_request":elapsed/CONCURRENCY,"rows":rows,"candidate_path":(arm_root/"candidate-path.jsonl").read_text().splitlines() if candidate and (arm_root/"candidate-path.jsonl").exists() else []}; atomic(arm_root/"TERMINAL.json",terminal); return terminal
    finally:
        logs=subprocess.run(["sudo","-n","docker","logs",name],text=True,capture_output=True,check=False,timeout=120); (arm_root/"server.stdout").write_text(logs.stdout); (arm_root/"server.stderr").write_text(logs.stderr); subprocess.run(["sudo","-n","docker","rm","-f",name],text=True,capture_output=True,check=False,timeout=120)


def main() -> None:
    parser=argparse.ArgumentParser(); parser.add_argument("--project",type=pathlib.Path,required=True); parser.add_argument("--checkpoint",type=pathlib.Path,required=True); parser.add_argument("--output",type=pathlib.Path,required=True); parser.add_argument("--port",type=int,default=30000); args=parser.parse_args()
    if args.output.exists(): raise SystemExit("output_root_must_not_exist")
    control=arm(args.project,args.checkpoint,args.output,"control",False,args.port); candidate=arm(args.project,args.checkpoint,args.output,"candidate",True,args.port)
    exact=[r["token_ids"] for r in control["rows"]]==[r["token_ids"] for r in candidate["rows"]]
    proof={json.loads(line)["class"] for line in candidate["candidate_path"]} if candidate["candidate_path"] else set()
    atomic(args.output/"PAIR_TERMINAL.json",{"schema_version":1,"classification":"fixed_floor_crossop_matched_exact_c32_endpoint_pair","valid":bool(control["pass"] and candidate["pass"] and exact and proof=={"local","global"}),"control":control,"candidate":candidate,"request_token_ids_exact":exact,"candidate_local_global_proof":sorted(proof),"service_seconds_delta":candidate["service_seconds_per_request"]-control["service_seconds_per_request"]})


if __name__ == "__main__": main()
