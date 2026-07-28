#!/usr/bin/env python3
import argparse
import concurrent.futures
import hashlib
import json
import threading
import time
import urllib.request
from decimal import Decimal, getcontext
from pathlib import Path


getcontext().prec = 60
MODEL = "google/gemma-4-31B-it"
CALIBRATION_END = 32


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    part.replace(path)


def validate_packet(root):
    manifest_path = root / "PACKET_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text())
    for row in manifest["files"]:
        path = root / row["path"]
        if path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise RuntimeError("packet_manifest_mismatch:" + row["path"])
    expected = "sha256:" + digest(manifest_path)
    packet_id = json.loads((root / "PACKET_ID.json").read_text())
    if packet_id["content_address"] != expected:
        raise RuntimeError("packet_content_address_mismatch")
    return expected


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


class Endpoint:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")

    def get(self, path, timeout=10):
        return urllib.request.urlopen(self.base_url + path, timeout=timeout).read()

    def post_json(self, path, value, timeout=1200):
        request = urllib.request.Request(
            self.base_url + path,
            json.dumps(value, separators=(",", ":")).encode(),
            {"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as reply:
            return json.loads(reply.read())

    def generate(self, body):
        began = time.monotonic()
        parsed = self.post_json(
            "/generate",
            {
                "input_ids": body["prompt"],
                "sampling_params": {
                    "temperature": 0,
                    "max_new_tokens": body["max_tokens"],
                    "min_new_tokens": body["min_tokens"],
                    "ignore_eos": body["ignore_eos"],
                },
            },
        )
        meta = parsed.get("meta_info") or {}
        usage = {
            "prompt_tokens": meta.get("prompt_tokens", len(body["prompt"])),
            "completion_tokens": meta.get(
                "completion_tokens", body["max_tokens"]
            ),
        }
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
        return {
            "finish_reason": meta.get("finish_reason")
            or parsed.get("finish_reason"),
            "latency_seconds": time.monotonic() - began,
            "output_ids": parsed.get("output_ids")
            or meta.get("output_ids")
            or meta.get("completion_token_ids"),
            "usage": usage,
        }

    def metrics(self):
        raw = self.get("/metrics").decode()
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

    def wait_ready(self):
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            try:
                payload = json.loads(self.get("/v1/models", 4))
                if MODEL in [row.get("id") for row in payload.get("data", [])]:
                    return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("server_not_ready")

    def flush_and_wait_idle(self):
        before = self.metrics()
        if before.get("sglang:num_queue_reqs", 0) != 0 or before.get(
            "sglang:num_running_reqs", 0
        ) != 0:
            raise RuntimeError("server_not_idle_before_flush")
        self.post_json("/flush_cache", {})
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            values = self.metrics()
            if values.get("sglang:num_queue_reqs", 0) == 0 and values.get(
                "sglang:num_running_reqs", 0
            ) == 0:
                return
            time.sleep(0.25)
        raise RuntimeError("server_not_idle_after_flush")


def semantic(answer):
    return {
        key: answer[key] for key in ("output_ids", "finish_reason", "usage")
    }


def invoke(endpoint, index, planned, released, body, expected, origin):
    began = time.monotonic() - origin
    try:
        answer = endpoint.generate(body)
        actual_semantic = semantic(answer)
        expected_semantic = {
            key: expected["semantic"][key]
            for key in ("output_ids", "finish_reason", "usage")
        }
        return {
            "actual_release_seconds": str(released),
            "client_started_seconds": began,
            "completed_seconds": time.monotonic() - origin,
            "planned_release_seconds": str(planned),
            "release_drift_seconds": str(released - planned),
            "request_sha256": hashlib.sha256(
                json.dumps(body, sort_keys=True).encode()
            ).hexdigest(),
            "semantic": actual_semantic,
            "semantic_matches_bound": actual_semantic == expected_semantic,
            "server_seconds": answer["latency_seconds"],
            "source_index": index,
        }
    except Exception as exc:
        return {
            "client_started_seconds": began,
            "completed_seconds": time.monotonic() - origin,
            "error": repr(exc),
            "planned_release_seconds": str(planned),
            "source_index": index,
        }


def sample_metrics(endpoint, stop, values, origin):
    while not stop.wait(0.5):
        row = {"elapsed_seconds": time.monotonic() - origin}
        try:
            row["metrics"] = endpoint.metrics()
        except Exception as exc:
            row["error"] = repr(exc)
        values.append(row)


def execute_phase(endpoint, schedule, bodies, expected):
    origin = time.monotonic()
    telemetry = []
    stop = threading.Event()
    thread = threading.Thread(
        target=sample_metrics,
        args=(endpoint, stop, telemetry, origin),
        daemon=True,
    )
    thread.start()
    submissions = []
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=44) as executor:
            futures = []
            for index, planned in schedule:
                time.sleep(
                    max(0.0, float(planned) - (time.monotonic() - origin))
                )
                released = Decimal(str(time.monotonic() - origin))
                futures.append(
                    executor.submit(
                        invoke,
                        endpoint,
                        index,
                        planned,
                        released,
                        bodies[index],
                        expected[index],
                        origin,
                    )
                )
                submissions.append(
                    {
                        "actual_release_seconds": str(released),
                        "planned_release_seconds": str(planned),
                        "release_drift_seconds": str(released - planned),
                        "source_index": index,
                    }
                )
            rows = [future.result() for future in futures]
    finally:
        stop.set()
        thread.join(5)
    rows.sort(key=lambda row: row["source_index"])
    return rows, submissions, telemetry


def schedule_for(mode, end, arrivals, geometry):
    if mode == "control":
        origin = arrivals[CALIBRATION_END]
        return [
            (index, arrivals[index] - origin)
            for index in range(CALIBRATION_END, end)
        ]
    if end == 791:
        return [
            (row["source_index"], Decimal(row["aggregate_release_seconds"]))
            for row in geometry
        ]
    if end != 171:
        raise RuntimeError("candidate discriminator end must be 171 or 791")
    split = 102
    phase = (arrivals[CALIBRATION_END + 1] - arrivals[CALIBRATION_END]) / 2
    schedule = []
    for index in range(CALIBRATION_END, end):
        if index < split:
            planned = arrivals[index] - arrivals[CALIBRATION_END]
        else:
            planned = phase + arrivals[index] - arrivals[split]
        schedule.append((index, planned))
    return sorted(schedule, key=lambda row: (row[1], row[0]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-root", type=Path, default=Path(__file__).parent)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--end", type=int, choices=(171, 791), default=171)
    parser.add_argument("--mode", choices=("control", "candidate"), default="candidate")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    root = args.packet_root.resolve()
    content_address = validate_packet(root)
    inputs = root / "inputs"
    expected = [
        json.loads(line)
        for line in (inputs / "exact_semantic_rows.jsonl").read_text().splitlines()
    ]
    trace = json.loads((inputs / "TRACE_PACKET.json").read_text())
    template = next(
        row for row in trace["primary_groups"] if row["name"] == "primary_c1"
    )["scored"][0]
    bodies = [request_body(template, index) for index in range(args.end)]
    for index, body in enumerate(bodies):
        actual = hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest()
        if actual != expected[index]["request_sha256"]:
            raise RuntimeError(f"request_hash_mismatch:{index}")
    if args.validate_only:
        print(content_address)
        return
    if args.out is None:
        raise RuntimeError("--out is required for execution")

    geometry = [
        json.loads(line)
        for line in (root / "geometry.jsonl").read_text().splitlines()
    ]
    arrivals = [Decimal(str(row["arrival_s"])) for row in expected]
    endpoint = Endpoint(args.base_url)
    endpoint.wait_ready()
    endpoint.flush_and_wait_idle()

    calibration_schedule = [
        (index, arrivals[index] - arrivals[0])
        for index in range(CALIBRATION_END)
    ]
    calibration_rows, calibration_submissions, calibration_telemetry = execute_phase(
        endpoint, calibration_schedule, bodies, expected
    )
    calibration_failures = [row for row in calibration_rows if "error" in row]
    if calibration_failures or not all(
        row.get("semantic_matches_bound") for row in calibration_rows
    ):
        atomic_json(
            args.out / "CALIBRATION_TERMINAL.json",
            {
                "failures": calibration_failures,
                "result": "calibration_reject",
                "rows": calibration_rows,
            },
        )
        raise RuntimeError("calibration_rejected")
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        metrics = endpoint.metrics()
        if metrics.get("sglang:num_queue_reqs", 0) == 0 and metrics.get(
            "sglang:num_running_reqs", 0
        ) == 0:
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("calibration_did_not_drain")

    scored_schedule = schedule_for(args.mode, args.end, arrivals, geometry)
    rows, submissions, telemetry = execute_phase(
        endpoint, scored_schedule, bodies, expected
    )
    failures = [row for row in rows if "error" in row]
    queue_values = [
        row["metrics"].get("sglang:num_queue_reqs")
        for row in telemetry
        if row.get("metrics", {}).get("sglang:num_queue_reqs") is not None
    ]
    accept_lengths = [
        row["metrics"].get("sglang:spec_accept_length")
        for row in telemetry
        if row.get("metrics", {}).get("sglang:spec_accept_length") is not None
    ]
    final_metrics = endpoint.metrics()
    decision = {
        "all_normalized_semantics_exact": not failures
        and all(row.get("semantic_matches_bound") for row in rows),
        "failures_zero": not failures,
        "final_queue_zero": final_metrics.get("sglang:num_queue_reqs") == 0,
        "native_ngram_activation": bool(accept_lengths)
        and max(accept_lengths) > 1,
        "peak_queue_at_most_30": bool(queue_values) and max(queue_values) <= 30,
        "release_drift_bounded": all(
            abs(Decimal(row["release_drift_seconds"])) <= Decimal("0.25")
            for row in submissions
        ),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "calibration_requests.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in calibration_rows)
    )
    (args.out / "requests.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    )
    (args.out / "telemetry.jsonl").write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in telemetry)
    )
    terminal = {
        "calibration": {
            "requests": len(calibration_rows),
            "submissions": calibration_submissions,
            "telemetry_samples": len(calibration_telemetry),
        },
        "candidate_sample_consumed": args.mode == "candidate",
        "decision": decision,
        "elapsed_seconds": max(row["completed_seconds"] for row in rows),
        "failures": failures,
        "final_metrics": final_metrics,
        "identity": {
            "mode": args.mode,
            "packet_content_address": content_address,
            "request_end_exclusive": args.end,
        },
        "queue_peak": max(queue_values) if queue_values else None,
        "requests": len(rows),
        "result": "measured_demand_multiplexing_discriminator",
        "retain_candidate": all(decision.values()),
    }
    atomic_json(args.out / "FINAL_TERMINAL.json", terminal)
    print(json.dumps(terminal, sort_keys=True))


if __name__ == "__main__":
    main()
