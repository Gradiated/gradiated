#!/usr/bin/env python3
"""R5 candidate-only consumer using the frozen completion-shaped workload."""
import argparse
import concurrent.futures
import hashlib
import json
import pathlib
import subprocess
import time
import urllib.error
import urllib.request

from run_fixed_floor_crossop_endpoint_pair import CONCURRENCY, IMAGE, MODEL, canonical, workload


def put(path, value):
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def parse(raw):
    chunks, finish, usage, events = [], [], [], 0
    for line in raw.splitlines():
        if not line.startswith(b"data: ") or line == b"data: [DONE]":
            continue
        events += 1
        item = json.loads(line[6:])
        choice = (item.get("choices") or [{}])[0]
        if choice.get("text"):
            chunks.append(choice["text"])
        if choice.get("finish_reason") is not None:
            finish.append(choice["finish_reason"])
        if item.get("usage") is not None:
            usage.append(item["usage"])
    return {"sse_events": events, "chunks": chunks, "finish_reason": finish, "usage": usage}


def request(url, body):
    start, raw = time.monotonic(), b""
    query = urllib.request.Request(url + "/v1/completions", data=canonical(body), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(query, timeout=600) as response:
            raw = response.read()
        return raw, {"error": None, "http_status": 200, "http_error_body": None, "wall_seconds": time.monotonic() - start, "request_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    except urllib.error.HTTPError as error:
        raw = error.read(8192)
        return raw, {"error": f"HTTPError: {error}", "http_status": error.code, "http_error_body": raw.decode("utf-8", "replace"), "wall_seconds": time.monotonic() - start, "request_sha256": hashlib.sha256(canonical(body)).hexdigest()}
    except Exception as error:
        return raw, {"error": f"{type(error).__name__}: {error}", "http_status": None, "http_error_body": None, "wall_seconds": time.monotonic() - start, "request_sha256": hashlib.sha256(canonical(body)).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=pathlib.Path, required=True)
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--oracle", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--port", type=int, default=30001)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("fresh_candidate_output_required")
    args.output.mkdir(parents=True)
    name, url = "gemma4-fixed-floor-candidate-r5", f"http://127.0.0.1:{args.port}"
    command = ["sudo", "-n", "docker", "run", "-d", "--name", name, "--gpus", "all", "--ipc=host", "--network=host", "-v", f"{args.project}:/work/project:ro", "-v", f"{args.checkpoint}:/work/checkpoint:ro", "-v", f"{args.output}:/work/output", "-v", f"{args.project}/endpoint_candidate_gemma4_causal.py:/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py:ro", "-e", "PYTHONPATH=/work/project:/sgl-workspace/sglang/python", "-e", "FIXED_FLOOR_CROSSOP_AUDIT=/work/output/candidate-path.jsonl", IMAGE, "python3", "-m", "sglang.launch_server", "--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint", "--served-model-name", MODEL, "--dtype", "bfloat16", "--quantization", "fp8", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--port", str(args.port), "--context-length", "5000", "--max-running-requests", "32", "--mem-fraction-static", "0.85", "--skip-server-warmup", "--enable-dynamic-chunking", "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32", "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1", "--num-continuous-decode-steps", "1", "--tool-call-parser", "gemma4"]
    launch = subprocess.run(command, text=True, capture_output=True, timeout=120)
    put(args.output / "launch.json", {"returncode": launch.returncode, "stderr": launch.stderr})
    if launch.returncode:
        raise RuntimeError("candidate_launch_failed")
    try:
        for _ in range(180):
            running = subprocess.run(["sudo", "-n", "docker", "inspect", "-f", "{{.State.Running}}", name], text=True, capture_output=True, timeout=20)
            if running.returncode or running.stdout.strip() != "true":
                raise RuntimeError("candidate_server_exited_before_ready")
            try:
                if MODEL in urllib.request.urlopen(url + "/v1/models", timeout=5).read().decode():
                    break
            except Exception:
                pass
            time.sleep(2)
        else:
            raise RuntimeError("candidate_server_readiness_timeout")
        started = time.monotonic()
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
            results = list(pool.map(lambda body: request(url, body), workload()))
        oracle, rows, exact = json.loads(args.oracle.read_text()), [], True
        for index, (raw, row) in enumerate(results):
            (args.output / f"response-{index:02d}.sse").write_bytes(raw)
            observed, expected = parse(raw), oracle["rows"][index]
            match = not row["error"] and observed["chunks"] == expected["chunks"] and observed["finish_reason"] == expected["finish_reason"] and observed["usage"] == expected["usage"] and observed["sse_events"] == expected["sse_events"]
            exact &= match
            rows.append({**row, **observed, "exact_emitted_chunk_match": match})
        audit = (args.output / "candidate-path.jsonl").read_text().splitlines() if (args.output / "candidate-path.jsonl").exists() else []
        proof = {json.loads(line).get("class") for line in audit}
        complete = sum(not row["error"] for row in rows)
        put(args.output / "PAIR_TERMINAL.json", {"schema_version": 1, "classification": "candidate_only_exact_emitted_chunk_endpoint", "science_consumed": complete == 32, "valid": bool(exact and complete == 32 and proof == {"local", "global"}), "candidate": {"complete_requests": complete, "service_seconds_per_request": (time.monotonic() - started) / 32, "rows": rows}, "candidate_local_global_proof": sorted(proof), "oracle_sha256": hashlib.sha256(args.oracle.read_bytes()).hexdigest()})
    finally:
        logs = subprocess.run(["sudo", "-n", "docker", "logs", name], text=True, capture_output=True, timeout=120)
        (args.output / "server.stdout").write_text(logs.stdout)
        (args.output / "server.stderr").write_text(logs.stderr)
        subprocess.run(["sudo", "-n", "docker", "rm", "-f", name], text=True, capture_output=True, timeout=120)


if __name__ == "__main__":
    main()
