#!/usr/bin/env python3
import concurrent.futures
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request
from pathlib import Path


ROOT = Path(os.environ["UPSTREAM_REBASE_ROOT"])
OUT = Path(os.environ.get("UPSTREAM_REBASE_OUT", str(ROOT / "out")))
INPUT = ROOT / "inputs"
MODEL = "google/gemma-4-31B-it"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
)
COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
CONTAINER = os.environ.get("UPSTREAM_REBASE_CONTAINER", "gemma4-ngram-upstream-v0515")
REQUESTS = int(os.environ.get("UPSTREAM_REBASE_REQUESTS", "171"))


def atomic(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    part.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def get(url, timeout=10):
    return urllib.request.urlopen(url, timeout=timeout).read()


def post(body):
    payload = {
        "input_ids": body["prompt"],
        "sampling_params": {
            "temperature": 0,
            "max_new_tokens": body["max_tokens"],
            "min_new_tokens": body["min_tokens"],
            "ignore_eos": body["ignore_eos"],
        },
    }
    request = urllib.request.Request(
        "http://127.0.0.1:30000/generate",
        json.dumps(payload, separators=(",", ":")).encode(),
        {"Content-Type": "application/json"},
    )
    began = time.monotonic()
    with urllib.request.urlopen(request, timeout=1200) as reply:
        parsed = json.loads(reply.read())
    meta = parsed.get("meta_info") or {}
    usage = {
        "prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])),
        "completion_tokens": meta.get("completion_tokens", body["max_tokens"]),
    }
    usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return {
        "usage": usage,
        "output_ids": (
            parsed.get("output_ids")
            or meta.get("output_ids")
            or meta.get("completion_token_ids")
        ),
        "finish_reason": meta.get("finish_reason") or parsed.get("finish_reason"),
        "latency_seconds": time.monotonic() - began,
    }


def request_body(template, index):
    value = dict(template["request_body"])
    value.update(
        {
            "model": MODEL,
            "ignore_eos": True,
            "min_tokens": 358,
            "max_tokens": 358,
            "request_id": f"tail-overlap-{index}",
        }
    )
    value["prompt"] = list(value["prompt"])
    value["prompt"][535] = 200000 + index
    return value


def metrics():
    raw = get("http://127.0.0.1:30000/metrics").decode()
    values = {}
    for line in raw.splitlines():
        if not line or line.startswith("#"):
            continue
        name = line.split("{", 1)[0]
        if name in {
            "sglang:num_queue_reqs",
            "sglang:num_running_reqs",
            "sglang:spec_accept_rate",
            "sglang:spec_accept_length",
        }:
            try:
                values[name] = float(line.rsplit(" ", 1)[1])
            except ValueError:
                pass
    return values


def wait_server():
    deadline = time.monotonic() + 720
    while time.monotonic() < deadline:
        try:
            payload = json.loads(get("http://127.0.0.1:30000/v1/models", 4))
            if MODEL in [row.get("id") for row in payload.get("data", [])]:
                return
        except Exception:
            pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")


def inspect_container(launch):
    result = subprocess.run(
        ["docker", "inspect", CONTAINER],
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError("container_inspect_failed:" + result.stderr[-1000:])
    rows = json.loads(result.stdout)
    if len(rows) != 1:
        raise RuntimeError("container_inspect_cardinality")
    row = rows[0]
    labels = row.get("Config", {}).get("Labels") or {}
    configured_image = row.get("Config", {}).get("Image") or ""
    expected_digest = IMAGE.rsplit("@", 1)[1]
    actual_command = row.get("Config", {}).get("Cmd") or []
    expected_command = ["python3", "-m", "sglang.launch_server", *launch]
    identity = {
        "configured_image": configured_image,
        "container_image_id": row.get("Image"),
        "revision_label": labels.get("org.opencontainers.image.revision"),
        "entrypoint": row.get("Config", {}).get("Entrypoint"),
        "actual_command": actual_command,
        "expected_command": expected_command,
    }
    if expected_digest not in configured_image:
        raise RuntimeError("container_image_digest_mismatch:" + repr(identity))
    if identity["revision_label"] != COMMIT:
        raise RuntimeError("container_commit_label_mismatch:" + repr(identity))
    if actual_command != expected_command:
        raise RuntimeError("container_launch_argv_mismatch:" + repr(identity))
    return identity


def invoke(index, arrival, released, request, expected, origin):
    began = time.monotonic() - origin
    try:
        answer = post(request)
        semantic = {
            key: answer[key] for key in ("output_ids", "finish_reason", "usage")
        }
        expected_semantic = {
            key: expected["semantic"][key]
            for key in ("output_ids", "finish_reason", "usage")
        }
        mismatch_index = None
        if semantic["output_ids"] != expected_semantic["output_ids"]:
            pairs = zip(semantic["output_ids"], expected_semantic["output_ids"])
            mismatch_index = next(
                (
                    token_index
                    for token_index, (actual, bound) in enumerate(pairs)
                    if actual != bound
                ),
                min(len(semantic["output_ids"]), len(expected_semantic["output_ids"])),
            )
        return {
            "i": index,
            "arrival_s": arrival,
            "released_s": released,
            "client_started_s": began,
            "completed_s": time.monotonic() - origin,
            "request_sha256": hashlib.sha256(
                json.dumps(request, sort_keys=True).encode()
            ).hexdigest(),
            "semantic": semantic,
            "semantic_matches_bound": semantic == expected_semantic,
            "first_output_token_mismatch": mismatch_index,
            "server_seconds": answer["latency_seconds"],
        }
    except Exception as exc:
        return {
            "i": index,
            "arrival_s": arrival,
            "released_s": released,
            "client_started_s": began,
            "completed_s": time.monotonic() - origin,
            "error": repr(exc),
        }


def sample(stop, rows, origin):
    while not stop.wait(0.5):
        row = {"elapsed_s": time.monotonic() - origin}
        try:
            row["metrics"] = metrics()
        except Exception as exc:
            row["metrics_error"] = repr(exc)
        rows.append(row)


def main():
    atomic(
        "INVOCATION_STATE.json",
        {"science_started": False, "phase": "identity_and_input_verification"},
    )
    if REQUESTS != 171:
        raise RuntimeError("immutable_discriminator_requires_171_requests")
    manifest = json.loads((INPUT / "INPUT_MANIFEST.json").read_text())
    for name, expected in manifest.items():
        if name == "support_two_terminal.json":
            continue
        if digest(INPUT / name) != expected:
            raise RuntimeError("input_hash_mismatch:" + name)
    runtime = json.loads((ROOT / "CANDIDATE_RUNTIME.json").read_text())
    candidate = runtime["candidate"]
    if candidate["commit"] != COMMIT or candidate["official_image"] != IMAGE:
        raise RuntimeError("candidate_identity_mismatch")
    controls = [
        json.loads(line)
        for line in (INPUT / "exact_semantic_rows.jsonl").read_text().splitlines()
    ][:REQUESTS]
    if [row["i"] for row in controls] != list(range(REQUESTS)):
        raise RuntimeError("bound_row_identity_mismatch")
    trace = json.loads((INPUT / "TRACE_PACKET.json").read_text())
    template = next(
        row for row in trace["primary_groups"] if row["name"] == "primary_c1"
    )["scored"][0]
    launch = json.loads((INPUT / "ngram-launch.json").read_text())["args"]
    if launch[launch.index("--speculative-algorithm") + 1] != "NGRAM":
        raise RuntimeError("launch_not_native_ngram")
    if "--speculative-ngram-external-corpus-path" in launch:
        raise RuntimeError("launch_uses_external_corpus")
    container_identity = inspect_container(launch)
    wait_server()
    atomic(
        "ACTIVATION_IDENTITY.json",
        {
            "container": CONTAINER,
            "candidate_image": IMAGE,
            "candidate_commit": COMMIT,
            "model": MODEL,
            "native_ngram": True,
            "depth": 12,
            "launch_args": launch,
            "container_identity": container_identity,
        },
    )
    atomic(
        "INVOCATION_STATE.json",
        {
            "science_started": True,
            "phase": "candidate_requests_0_through_170",
            "requests": REQUESTS,
        },
    )
    origin = time.monotonic()
    telemetry = []
    stop = threading.Event()
    thread = threading.Thread(target=sample, args=(stop, telemetry, origin), daemon=True)
    thread.start()
    submissions = []
    rows = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=44) as executor:
            futures = []
            for index in range(REQUESTS):
                arrival = controls[index]["arrival_s"]
                time.sleep(max(0, origin + arrival - time.monotonic()))
                released = time.monotonic() - origin
                future = executor.submit(
                    invoke,
                    index,
                    arrival,
                    released,
                    request_body(template, index),
                    controls[index],
                    origin,
                )
                futures.append(future)
                submissions.append(
                    {
                        "request": index,
                        "planned_release_s": arrival,
                        "actual_release_s": released,
                        "release_drift_seconds": released - arrival,
                    }
                )
            rows = [future.result() for future in futures]
    finally:
        stop.set()
        thread.join(5)
    rows.sort(key=lambda row: row["i"])
    (OUT / "requests.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (OUT / "telemetry.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in telemetry)
    )
    failures = [row for row in rows if "error" in row]
    mismatches = [
        {
            "request": row["i"],
            "first_output_token_mismatch": row["first_output_token_mismatch"],
        }
        for row in rows
        if not row.get("semantic_matches_bound", False) and "error" not in row
    ]
    accept_lengths = [
        row["metrics"].get("sglang:spec_accept_length")
        for row in telemetry
        if row.get("metrics", {}).get("sglang:spec_accept_length") is not None
    ]
    activation = bool(accept_lengths and max(accept_lengths) > 1)
    decision = {
        "all_171_complete": len(rows) == REQUESTS and not failures,
        "normalized_semantics_exact": not mismatches and not failures,
        "failures_zero": not failures,
        "native_ngram_activation_observed": activation,
        "release_drift_bounded": all(
            abs(row["release_drift_seconds"]) <= 0.25 for row in submissions
        ),
    }
    atomic(
        "FINAL_TERMINAL.json",
        {
            "result": "measured_upstream_runtime_activation_semantic_discriminator",
            "candidate_sample_consumed": True,
            "identity": {
                "image": IMAGE,
                "commit": COMMIT,
                "model": MODEL,
                "ngram": "native_depth_12",
                "requests": "0_through_170_at_bound_arrivals",
            },
            "decision": decision,
            "first_semantic_divergence": mismatches[0] if mismatches else None,
            "failures": failures,
            "requests": REQUESTS,
            "elapsed_seconds": max(row["completed_s"] for row in rows),
            "max_spec_accept_length": max(accept_lengths) if accept_lengths else None,
            "endpoint_admitted": all(decision.values()),
        },
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        atomic(
            "ATTEMPT_TERMINAL.json",
            {
                "classification": "recoverable_integration_or_typed_runtime_failure",
                "error": repr(exc),
                "candidate_sample_consumed": False,
            },
        )
        raise
