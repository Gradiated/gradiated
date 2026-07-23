#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import pathlib
import sys


LOCAL_LAYER_IDS = set(i for i in range(60) if (i + 1) % 6)
GLOBAL_LAYER_IDS = set(range(5, 60, 6))


def rows(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    root = pathlib.Path(sys.argv[1])
    prior = json.loads(pathlib.Path(sys.argv[2]).read_text())
    output = pathlib.Path(sys.argv[3])
    args = pathlib.Path(sys.argv[4]).read_text()
    server_log = pathlib.Path(sys.argv[5]).read_text(errors="replace")
    init = json.loads((root / "init.json").read_text())
    producer = rows(root / "producer.jsonl")
    consumer = rows(root / "consumer.jsonl")
    init_layers = {row["layer_id"]: row for row in init["layers"]}
    expected_keys = {("extend", layer) for layer in range(60)}
    producer_map = {(row["phase"], row["layer_id"]): row for row in producer}
    consumer_map = {(row["phase"], row["layer_id"]): row for row in consumer}
    failures = []
    if set(init_layers) != set(range(60)):
        failures.append("init_layer_set")
    if set(producer_map) != expected_keys:
        failures.append("producer_layer_set")
    if set(consumer_map) != expected_keys:
        failures.append("consumer_layer_set")
    if not init.get("alias_free"):
        failures.append("cross_pool_alias")
    if (
        "--kv-cache-dtype fp8_e5m2" not in args
        or args.count("attention-backend triton") != 2
        or "flash" in args.lower()
        or "--page-size 1" not in args
    ):
        failures.append("server_path")
    if "Capture cuda graph end" not in server_log or "bs [1, 2, 4, 8, 12, 16, 24, 32]" not in server_log:
        failures.append("cuda_graph_capture")
    if not all(row.get("coherent") for row in prior.get("coherence", [])):
        failures.append("coherence")

    for layer_id in range(60):
        expected_pool = "local" if layer_id in LOCAL_LAYER_IDS else "global"
        expected_dtype = (
            "torch.float8_e4m3fn"
            if layer_id in LOCAL_LAYER_IDS
            else "torch.float8_e5m2"
        )
        init_row = init_layers.get(layer_id)
        producer_row = producer_map.get(("extend", layer_id))
        consumer_row = consumer_map.get(("extend", layer_id))
        if init_row is None or producer_row is None or consumer_row is None:
            continue
        if (
            init_row["pool"] != expected_pool
            or producer_row["pool"] != expected_pool
            or consumer_row["pool"] != expected_pool
        ):
            failures.append(f"pool:{layer_id}")
        if any(
            row["dtype"] != expected_dtype
            for row in (
                init_row["key"],
                init_row["value"],
                producer_row["storage_key"],
                producer_row["storage_value"],
                consumer_row["key"],
                consumer_row["value"],
            )
        ):
            failures.append(f"dtype:{layer_id}")
        if (
            producer_row["storage_key"]["data_ptr"] != consumer_row["key"]["data_ptr"]
            or producer_row["storage_value"]["data_ptr"]
            != consumer_row["value"]["data_ptr"]
            or producer_row["storage_key"]["data_ptr"] != init_row["key"]["data_ptr"]
            or producer_row["storage_value"]["data_ptr"]
            != init_row["value"]["data_ptr"]
        ):
            failures.append(f"pointer:{layer_id}")
        if producer_row["used_swa_loc"] != (layer_id in LOCAL_LAYER_IDS):
            failures.append(f"slot_router:{layer_id}")
        allocation = init["allocations"][0 if layer_id in LOCAL_LAYER_IDS else 1]
        if (
            producer_row["loc_count"] < 1
            or producer_row["loc_min"] < 0
            or producer_row["loc_max"] >= allocation["size"] + allocation["page_size"]
            or not producer_row["sample_finite"]
            or not consumer_row["output_finite"]
        ):
            failures.append(f"slot_or_numeric:{layer_id}")
        for scale_name in ("k_scale", "v_scale"):
            scale = producer_row[scale_name]
            descale = consumer_row[scale_name + "_float"]
            if scale is None:
                if descale != 1.0:
                    failures.append(f"scale:{scale_name}:{layer_id}")
            elif (
                not math.isfinite(scale)
                or scale <= 0
                or not math.isclose(scale, descale, rel_tol=0, abs_tol=1e-12)
            ):
                failures.append(f"scale:{scale_name}:{layer_id}")

    value = {
        "schema_version": 1,
        "kind": "exact_component_path_check",
        "pass": not failures,
        "failures": sorted(set(failures)),
        "repair_classification": "telemetry_guard_repair_no_component_replay",
        "prior_invalid_guard": prior.get("failures"),
        "local_layer_ids": sorted(LOCAL_LAYER_IDS),
        "global_layer_ids": sorted(GLOBAL_LAYER_IDS),
        "producer_events": len(producer),
        "consumer_events": len(consumer),
        "coherence": prior.get("coherence"),
        "source_sha256": init["source_sha256"],
        "alias_free": init["alias_free"],
        "cuda_graph_capture_bound": "Capture cuda graph end" in server_log,
        "server_args": args,
    }
    atomic(output, value)
    return 0 if value["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
