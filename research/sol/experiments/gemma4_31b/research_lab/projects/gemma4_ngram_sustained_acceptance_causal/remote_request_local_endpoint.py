#!/usr/bin/env python3
import concurrent.futures, hashlib, json, math, os, statistics, subprocess, threading, time, urllib.request
from pathlib import Path

ROOT = Path(os.environ["REQUEST_LOCAL_ROOT"])
OUT = Path(os.environ.get("REQUEST_LOCAL_RESULT_OUT", str(ROOT / "out")))
OVERLAY_OUT = Path(os.environ.get("REQUEST_LOCAL_CONTAINER_OUT", "/home/glmrunner/gemma4-ngram-tail-overlap/out"))
INPUT = ROOT / "inputs" / "bound"
MODEL = "google/gemma-4-31B-it"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
CONTAINER = "gemma4-ngram-tail-overlap"
N = int(os.environ.get("REQUEST_LOCAL_REQUESTS", "1036"))

def atomic(name, value):
    OUT.mkdir(parents=True, exist_ok=True); path = OUT / name; part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n"); part.replace(path)

def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(cmd, timeout=180): return subprocess.run(cmd, text=True, capture_output=True, check=False, timeout=timeout)
def get(url, timeout=10): return urllib.request.urlopen(url, timeout=timeout).read()

def metric_snapshot():
    error = None
    for _ in range(8):
        try:
            raw = get("http://127.0.0.1:30000/metrics").decode()
            break
        except Exception as exc:
            error = exc
            time.sleep(0.25)
    else:
        raise RuntimeError("metrics_unavailable_after_retries") from error
    values = {}
    wanted = ("sglang:num_queue_reqs", "sglang:num_running_reqs", "sglang:kv_used_tokens", "sglang:kv_available_tokens", "sglang:token_usage", "sglang:spec_accept_rate", "sglang:spec_accept_length")
    for line in raw.splitlines():
        if line and not line.startswith("#"):
            name = line.split("{", 1)[0]
            if name in wanted:
                try: values[name] = float(line.rsplit(" ", 1)[1])
                except ValueError: pass
    return values, raw

def post(body):
    native = {"input_ids": body["prompt"], "sampling_params": {"temperature": 0, "max_new_tokens": body["max_tokens"], "min_new_tokens": body["min_tokens"], "ignore_eos": body["ignore_eos"]}}
    request = urllib.request.Request("http://127.0.0.1:30000/generate", json.dumps(native, separators=(",", ":")).encode(), {"Content-Type": "application/json"})
    began = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as reply: response = reply.read()
    parsed = json.loads(response); meta = parsed.get("meta_info") or {}
    usage = {"prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])), "completion_tokens": meta.get("completion_tokens", body["max_tokens"])}
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {"usage": usage, "output_ids": parsed.get("output_ids") or meta.get("output_ids") or meta.get("completion_token_ids"), "finish_reason": meta.get("finish_reason") or parsed.get("finish_reason"), "latency_seconds": time.monotonic() - began}

def body(template, index):
    value = dict(template["request_body"]); value.update({"model": MODEL, "ignore_eos": True, "min_tokens": 358, "max_tokens": 358, "request_id": f"tail-overlap-{index}"})
    value["prompt"] = list(value["prompt"])
    if isinstance(index, int): value["prompt"][535] = 200000 + index
    return value

def wait_server():
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            if MODEL.encode() in get("http://127.0.0.1:30000/v1/models", 4): return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")

def verify_resident_server():
    payload = json.loads(get("http://127.0.0.1:30000/v1/models", 10))
    ids = [row.get("id") for row in payload.get("data", [])]
    if MODEL not in ids: raise RuntimeError("resident_model_mismatch:" + repr(ids))
    atomic("RESIDENT_SERVER_VERIFIED.json", {"container": CONTAINER, "model": MODEL, "model_ids": ids, "reused_without_docker_run": True})

def invoke(index, arrival, released, request, expected, origin):
    began = time.monotonic() - origin
    try:
        answer = post(request); complete = time.monotonic() - origin
        semantic = {key: answer[key] for key in ("output_ids", "finish_reason", "usage")}
        expected_semantic = {key: expected["semantic"][key] for key in ("output_ids", "finish_reason", "usage")}
        return {"i": index, "arrival_s": arrival, "released_s": released, "client_started_s": began, "completed_s": complete, "buffer_wait_seconds": released-arrival, "request_sha256": hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest(), "semantic": semantic, "semantic_matches_bound": semantic == expected_semantic, "server_seconds": answer["latency_seconds"]}
    except Exception as exc:
        return {"i": index, "arrival_s": arrival, "released_s": released, "client_started_s": began, "completed_s": time.monotonic()-origin, "buffer_wait_seconds": released-arrival, "error": repr(exc)}

def sampler(stop, rows, origin):
    while not stop.wait(2):
        row = {"elapsed_s": time.monotonic()-origin}
        s = run(["nvidia-smi", "--query-gpu=timestamp,utilization.gpu,power.draw,memory.used", "--format=csv,noheader,nounits"], 20); row["nvidia_smi"] = s.stdout.strip()
        try: row["metrics"] = metric_snapshot()[0]
        except Exception as exc: row["metrics_error"] = repr(exc)
        rows.append(row)

def percentile(xs, q): return sorted(xs)[min(len(xs)-1, math.ceil(q*len(xs))-1)] if xs else None

def main():
    OUT.mkdir(parents=True, exist_ok=True); atomic("INVOCATION_STATE.json", {"science_started": False, "phase": "request_local_verified_trunk_reload"})
    hashes = json.loads((INPUT / "SHA256SUMS.json").read_text())
    for name, expected in hashes.items():
        if digest(INPUT / name) != expected: raise RuntimeError("input_hash_mismatch:" + name)
    controls = [json.loads(line) for line in (INPUT / "exact_semantic_rows.jsonl").read_text().splitlines()][:N]
    if len(controls) != N or [x["i"] for x in controls] != list(range(N)): raise RuntimeError("bound_row_identity_mismatch")
    trace = json.loads((INPUT / "TRACE_PACKET.json").read_text()); template = next(x for x in trace["primary_groups"] if x["name"] == "primary_c1")["scored"][0]
    launch = json.loads((INPUT / "ngram-launch.json").read_text())["args"]
    # The controller installs the hash-bound sitecustomize overlay and performs this in-place restart.
    wait_server(); verify_resident_server()
    overlay_path = OVERLAY_OUT / "OVERLAY_STATE.json"
    trace_path = OVERLAY_OUT / "request-local-ngram.jsonl"
    if not overlay_path.exists():
        raise RuntimeError("activation_proof_missing:" + str(overlay_path))
    overlay = json.loads(overlay_path.read_text())
    if overlay.get("overlay") != "request_local_verified_trunk":
        raise RuntimeError("activation_proof_invalid:" + repr(overlay))
    if not trace_path.exists() or not any(json.loads(line).get("event") == "worker_initialized" for line in trace_path.read_text().splitlines()):
        raise RuntimeError("worker_activation_trace_missing:" + str(trace_path))
    atomic("ACTIVATION_PROOF.json", {"overlay": overlay, "overlay_path": str(overlay_path), "trace_path": str(trace_path), "worker_initialized": True})
    atomic("LAUNCH.json", {"reused_healthy_resident_server": True, "container": CONTAINER, "docker_run": False, "docker_reload": True, "docker_removal": False, "overlay": "request_local_verified_trunk"})
    before, raw = metric_snapshot(); (OUT / "metrics-before-primary.prom").write_text(raw)
    atomic("INVOCATION_STATE.json", {"science_started": True, "phase": "candidate_request_local_verified_trunk_full_arrival", "requests": N, "release_policy": "individual_bound_arrival_s_every_request"})
    origin = time.monotonic(); telemetry = []; stop = threading.Event(); thread = threading.Thread(target=sampler, args=(stop, telemetry, origin), daemon=True); thread.start()
    submissions, future_rows = [], []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=44) as executor:
            for i in range(N):
                planned = controls[i]["arrival_s"]
                time.sleep(max(0, origin + planned - time.monotonic()))
                released = time.monotonic() - origin
                snapshot = metric_snapshot()[0]
                future = executor.submit(invoke, i, planned, released, body(template, i), controls[i], origin)
                submissions.append({"request": i, "kind": "individual_arrival", "request_begin": i, "request_end_exclusive": i + 1, "planned_release_s": planned, "actual_release_s": released, "release_drift_seconds": released-planned, "upstream_queue_depth": snapshot.get("sglang:num_queue_reqs"), "cache_realization": snapshot, "futures": [future]})
            for submitted in submissions:
                wave_rows = [f.result() for f in submitted.pop("futures")]; future_rows.extend(wave_rows); valid = [x for x in wave_rows if "error" not in x]
                submitted.update({"server_completion_s": max(x["completed_s"] for x in wave_rows), "server_span_seconds": max(x["completed_s"] for x in wave_rows)-submitted["actual_release_s"], "completed": len(valid), "failures": len(wave_rows)-len(valid)})
    finally:
        stop.set(); thread.join(5)
    after, raw = metric_snapshot(); (OUT / "metrics-after-primary.prom").write_text(raw)
    future_rows.sort(key=lambda x: x["i"]); (OUT / "requests.jsonl").write_text("".join(json.dumps(x, sort_keys=True)+"\n" for x in future_rows)); (OUT / "waves.jsonl").write_text("".join(json.dumps({k:v for k,v in x.items() if k != "futures"}, sort_keys=True)+"\n" for x in submissions)); (OUT / "telemetry.jsonl").write_text("".join(json.dumps(x, sort_keys=True)+"\n" for x in telemetry))
    valid, failures = [x for x in future_rows if "error" not in x], [x for x in future_rows if "error" in x]; elapsed = max(x["completed_s"] for x in future_rows); total = sum(x["semantic"]["usage"]["total_tokens"] for x in valid); cost = 3.25*(elapsed/3600)/(total/1e6) if total else None
    drifts = [x["release_drift_seconds"] for x in submissions]; completion = [x["completed_s"]-x["arrival_s"] for x in valid]
    queue_samples = [x.get("metrics", {}).get("sglang:num_queue_reqs", 0) for x in telemetry if "metrics" in x]; max_queue = max([0, *[x.get("upstream_queue_depth") or 0 for x in submissions], *queue_samples])
    growing = len(drifts)>1 and drifts[-1] > drifts[0] and sum(b>a for a,b in zip(drifts, drifts[1:])) > len(drifts) // 2
    decision = {"all_complete": len(valid)==N, "normalized_semantics_exact": len(valid)==N and all(x["semantic_matches_bound"] for x in valid), "failures_zero": not failures, "all_requests_released_individually_at_bound_arrivals": len(submissions) == N and all(abs(x) <= 0.25 for x in drifts), "max_server_queue_at_most_30": max_queue <= 30, "final_server_queue_zero": (after.get("sglang:num_queue_reqs") or 0) == 0, "no_growing_release_drift": not growing, "planning_cost_at_or_below_target": cost is not None and cost <= 0.14}
    overlay = json.loads(overlay_path.read_text())
    trace = trace_path.read_text().splitlines()
    atomic("FINAL_TERMINAL.json", {"result": "measured_request_local_verified_trunk_full_arrival" if N == 1036 else "measured_request_local_verified_trunk_discriminator", "candidate_science_consumed": True, "identity": {"model": MODEL, "image": IMAGE, "ngram": "native_depth_12_every_load", "launch_sha256": digest(INPUT / "ngram-launch.json"), "bound_semantic_rows_sha256": digest(INPUT / "exact_semantic_rows.jsonl"), "intervention": f"request_local_verified_trunk;requests_0_through_{N-1}_released_individually_at_bound_arrival_s"}, "primary": {"requests": N, "elapsed_seconds": elapsed, "total_tokens": total, "failures": failures, "planning_cost_usd_per_million_total_tokens": cost, "completion_seconds": {"mean": statistics.mean(completion) if completion else None, "p95": percentile(completion, .95), "max": max(completion) if completion else None}, "queue": {"max_server_queue_requests": max_queue, "final_server_queue_requests": after.get("sglang:num_queue_reqs"), "samples": len(queue_samples)}, "metrics_before": before, "metrics_after": after, "gpu_samples": len(telemetry)}, "overlay": overlay, "overlay_trace_rows": len(trace), "arrival_timing": {"requests": submissions, "release_drift_seconds": drifts}, "decision": decision, "retain_request_local_verified_trunk": all(decision.values())})

if __name__ == "__main__":
    try: main()
    except Exception as exc:
        atomic("ATTEMPT_TERMINAL.json", {"classification": "recoverable_or_typed_remote_failure", "error": repr(exc), "candidate_science_consumed": False}); raise
