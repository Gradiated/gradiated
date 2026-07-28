#!/usr/bin/env python3
"""Execute one bound stock control or two-stream arm without speculation."""
import argparse
import json
import math
from pathlib import Path

import multiplex_runner as base


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("control", "candidate"), required=True)
    parser.add_argument("--end", type=int, choices=(171, 791), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.packet_root.resolve()
    packet_address = base.validate_packet(root)
    rows = [json.loads(line) for line in (root / "inputs/exact_semantic_rows.jsonl").read_text().splitlines()]
    launch = json.loads((root / "STOCK_LAUNCH.json").read_text())["args"]
    if any("ngram" in value.lower() or "speculative" in value.lower() for value in launch):
        raise RuntimeError("stock_launch_contains_forbidden_flag")
    trace = json.loads((root / "inputs/TRACE_PACKET.json").read_text())
    template = next(row for row in trace["primary_groups"] if row["name"] == "primary_c1")["scored"][0]
    bodies = [base.request_body(template, index) for index in range(args.end)]
    for index, body in enumerate(bodies):
        if base.hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != rows[index]["request_sha256"]:
            raise RuntimeError(f"bound_request_hash_mismatch:{index}")
    endpoint = base.Endpoint("http://127.0.0.1:30000")
    endpoint.wait_ready()
    endpoint.flush_and_wait_idle()
    arrivals = [base.Decimal(str(row["arrival_s"])) for row in rows]
    calibration = [(index, arrivals[index] - arrivals[0]) for index in range(base.CALIBRATION_END)]
    cal_rows, cal_submissions, cal_telemetry = base.execute_phase(endpoint, calibration, bodies, rows)
    cal_failures = [row for row in cal_rows if "error" in row or not row.get("semantic_matches_bound")]
    if cal_failures:
        args.out.mkdir(parents=True, exist_ok=True)
        base.atomic_json(args.out / "FINAL_TERMINAL.json", {"result":"calibration_reject", "candidate_sample_consumed":False, "calibration_failures":cal_failures})
        return
    schedule = base.schedule_for(args.mode, args.end, arrivals, [json.loads(line) for line in (root / "geometry.jsonl").read_text().splitlines()])
    measured, submissions, telemetry = base.execute_phase(endpoint, schedule, bodies, rows)
    failures = [row for row in measured if "error" in row]
    semantic_failures = [row for row in measured if not row.get("semantic_matches_bound", False)]
    queue = [row["metrics"].get("sglang:num_queue_reqs") for row in telemetry if row.get("metrics", {}).get("sglang:num_queue_reqs") is not None]
    final_metrics = endpoint.metrics()
    latencies = [row["server_seconds"] for row in measured if "server_seconds" in row]
    mean = sum(latencies) / len(latencies) if latencies else None
    variance = sum((value - mean) ** 2 for value in latencies) / max(1, len(latencies) - 1) if mean is not None else None
    terminal = {"result":"measured_stock_multiplex_arm", "candidate_sample_consumed":args.mode == "candidate", "identity":{"mode":args.mode,"request_end_exclusive":args.end,"packet_content_address":packet_address,"stock_no_speculation":True,"launch_args":launch}, "calibration":{"requests":len(cal_rows),"submissions":cal_submissions,"telemetry_samples":len(cal_telemetry)}, "rows":len(measured), "elapsed_seconds":max(row["completed_seconds"] for row in measured), "server_seconds_mean":mean, "server_seconds_sample_variance":variance, "failures":failures, "semantic_failures":semantic_failures, "queue_peak":max(queue) if queue else None, "final_metrics":final_metrics, "gates":{"normalized_semantics_exact":not failures and not semantic_failures, "failures_zero":not failures, "peak_queue_at_most_30":bool(queue) and max(queue) <= 30, "final_queue_zero":final_metrics.get("sglang:num_queue_reqs") == 0, "release_drift_bounded":all(abs(base.Decimal(row["release_drift_seconds"])) <= base.Decimal("0.25") for row in submissions), "request_bytes_unchanged":True, "within_stream_order_unchanged":True}}
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "requests.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in measured))
    (args.out / "telemetry.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in telemetry))
    base.atomic_json(args.out / "FINAL_TERMINAL.json", terminal)


if __name__ == "__main__":
    main()
