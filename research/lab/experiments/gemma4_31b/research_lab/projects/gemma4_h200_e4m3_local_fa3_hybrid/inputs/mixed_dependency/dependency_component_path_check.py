#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import pathlib
import sys
import time
import urllib.request


BASE = "http://127.0.0.1:30000"
MODEL = "google/gemma-4-31B-it"
LOCAL_LAYER_IDS = set(i for i in range(60) if (i + 1) % 6)
GLOBAL_LAYER_IDS = set(range(5, 60, 6))


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def completion(prompt: str) -> dict:
    body = json.dumps(
        {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 32,
        }
    ).encode()
    request = urllib.request.Request(
        BASE + "/v1/chat/completions", body, {"Content-Type": "application/json"}
    )
    return json.load(urllib.request.urlopen(request, timeout=180))


def main() -> int:
    root = pathlib.Path(sys.argv[1])
    output = pathlib.Path(sys.argv[2])
    args = pathlib.Path(sys.argv[3]).read_text()
    init = json.loads((root / "init.json").read_text())
    if init.get("pass") is not True:
        raise RuntimeError("mixed pool initialization did not pass")
    pathlib.Path(root.parent / "COMPONENT_ARMED").touch()
    component_body = json.dumps(
        {
            "model": MODEL,
            "prompt": list(range(1000, 1064)),
            "max_tokens": 2,
            "min_tokens": 2,
            "ignore_eos": True,
            "temperature": 0,
            "stream": False,
            "add_special_tokens": False,
        }
    ).encode()
    component_request = urllib.request.Request(
        BASE + "/v1/completions",
        component_body,
        {"Content-Type": "application/json"},
    )
    component_response = json.load(
        urllib.request.urlopen(component_request, timeout=180)
    )
    if not component_response.get("choices"):
        raise RuntimeError("empty component response")

    responses = []
    for expected, prompt in (
        ("READY", "Reply with exactly: READY"),
        ("4", "What is 2+2? Reply with only the number."),
        ("json", 'Return only a JSON object with key "status" and string value "ok".'),
    ):
        raw = completion(prompt)
        text = raw["choices"][0]["message"]["content"].strip()
        if expected == "json":
            normalized = text.strip("`json\n ")
            coherent = json.loads(normalized) == {"status": "ok"}
        else:
            coherent = text == expected
        responses.append(
            {
                "expected": expected,
                "text": text,
                "coherent": coherent,
                "finish_reason": raw["choices"][0].get("finish_reason"),
            }
        )

    deadline = time.monotonic() + 180
    producer = []
    consumer = []
    while time.monotonic() < deadline:
        producer = rows(root / "producer.jsonl")
        consumer = rows(root / "consumer.jsonl")
        if len(producer) >= 120 and len(consumer) >= 120:
            break
        time.sleep(0.5)

    init_layers = {row["layer_id"]: row for row in init["layers"]}
    expected_keys = {(phase, layer) for phase in ("extend", "decode") for layer in range(60)}
    producer_map = {(row["phase"], row["layer_id"]): row for row in producer}
    consumer_map = {(row["phase"], row["layer_id"]): row for row in consumer}
    failures = []
    if set(init_layers) != set(range(60)):
        failures.append("init_layer_set")
    if set(producer_map) != expected_keys:
        failures.append("producer_layer_phase_set")
    if set(consumer_map) != expected_keys:
        failures.append("consumer_layer_phase_set")
    if not init.get("alias_free"):
        failures.append("cross_pool_alias")
    if (
        "--kv-cache-dtype fp8_e5m2" not in args
        or args.count("attention-backend triton") != 2
        or "flash" in args.lower()
        or "--page-size 1" not in args
    ):
        failures.append("server_path")
    if not all(row["coherent"] for row in responses):
        failures.append("coherence")

    for layer_id in range(60):
        expected_pool = "local" if layer_id in LOCAL_LAYER_IDS else "global"
        expected_dtype = (
            "torch.float8_e4m3fn"
            if layer_id in LOCAL_LAYER_IDS
            else "torch.float8_e5m2"
        )
        init_row = init_layers.get(layer_id)
        if init_row is None:
            continue
        if init_row["pool"] != expected_pool:
            failures.append(f"init_pool:{layer_id}")
        if (
            init_row["key"]["dtype"] != expected_dtype
            or init_row["value"]["dtype"] != expected_dtype
        ):
            failures.append(f"init_dtype:{layer_id}")
        for phase in ("extend", "decode"):
            producer_row = producer_map.get((phase, layer_id))
            consumer_row = consumer_map.get((phase, layer_id))
            if producer_row is None or consumer_row is None:
                continue
            if producer_row["pool"] != expected_pool or consumer_row["pool"] != expected_pool:
                failures.append(f"pool:{phase}:{layer_id}")
            if (
                producer_row["storage_key"]["dtype"] != expected_dtype
                or producer_row["storage_value"]["dtype"] != expected_dtype
                or consumer_row["key"]["dtype"] != expected_dtype
                or consumer_row["value"]["dtype"] != expected_dtype
            ):
                failures.append(f"dtype:{phase}:{layer_id}")
            if (
                producer_row["storage_key"]["data_ptr"]
                != consumer_row["key"]["data_ptr"]
                or producer_row["storage_value"]["data_ptr"]
                != consumer_row["value"]["data_ptr"]
                or producer_row["storage_key"]["data_ptr"]
                != init_row["key"]["data_ptr"]
                or producer_row["storage_value"]["data_ptr"]
                != init_row["value"]["data_ptr"]
            ):
                failures.append(f"pointer:{phase}:{layer_id}")
            if producer_row["used_swa_loc"] != (layer_id in LOCAL_LAYER_IDS):
                failures.append(f"slot_router:{phase}:{layer_id}")
            allocation = init["allocations"][0 if layer_id in LOCAL_LAYER_IDS else 1]
            if (
                producer_row["loc_count"] < 1
                or producer_row["loc_min"] < 0
                or producer_row["loc_max"] >= allocation["size"] + allocation["page_size"]
                or not producer_row["sample_finite"]
                or not consumer_row["output_finite"]
            ):
                failures.append(f"slot_or_numeric:{phase}:{layer_id}")
            for scale_name in ("k_scale", "v_scale"):
                scale = producer_row[scale_name]
                descale = consumer_row[scale_name + "_float"]
                if scale is None:
                    if descale != 1.0:
                        failures.append(f"scale:{scale_name}:{phase}:{layer_id}")
                elif (
                    not math.isfinite(scale)
                    or scale <= 0
                    or not math.isclose(scale, descale, rel_tol=0, abs_tol=1e-12)
                ):
                    failures.append(f"scale:{scale_name}:{phase}:{layer_id}")

    value = {
        "schema_version": 1,
        "kind": "exact_component_path_check",
        "pass": not failures,
        "failures": sorted(set(failures)),
        "local_layer_ids": sorted(LOCAL_LAYER_IDS),
        "global_layer_ids": sorted(GLOBAL_LAYER_IDS),
        "producer_events": len(producer),
        "consumer_events": len(consumer),
        "coherence": responses,
        "source_sha256": init["source_sha256"],
        "alias_free": init["alias_free"],
        "server_args": args,
    }
    atomic(output, value)
    return 0 if value["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
