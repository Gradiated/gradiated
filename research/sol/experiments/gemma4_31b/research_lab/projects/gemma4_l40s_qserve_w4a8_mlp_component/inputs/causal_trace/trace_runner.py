#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import time
import urllib.request

from transformers import AutoTokenizer


BASE = "http://127.0.0.1:30000"
DEPTHS = (0, 1, 15, 30, 45, 60)
PROMPT = "Reply with exactly: cobalt:17"
ROOT = pathlib.Path("/work/artifacts/qserve-causal-trace")
CONTROL = ROOT / "TRACE_CONTROL.json"
EVENTS = ROOT / "trace-events.jsonl"


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def post(path: str, body: dict[str, object], timeout: int = 1800) -> tuple[dict, bytes]:
    raw_body = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    request = urllib.request.Request(
        BASE + path,
        data=raw_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        parsed = {"raw_text": raw.decode("utf-8", errors="replace")}
    return parsed, raw


def output_ids(response: dict) -> list[int]:
    meta = response.get("meta_info") or {}
    values = meta.get("output_ids") or response.get("output_ids")
    if not isinstance(values, list) or not all(isinstance(value, int) for value in values):
        raise ValueError("native response omitted output token IDs")
    return values


def first_divergence(reference: list[int], candidate: list[int]) -> int | None:
    for index, (left, right) in enumerate(zip(reference, candidate)):
        if left != right:
            return index
    return None if len(reference) == len(candidate) else min(len(reference), len(candidate))


def event_counts(run_id: str) -> dict[str, object]:
    routes: dict[str, int] = {}
    layers: dict[str, set[int]] = {}
    rows = []
    if EVENTS.is_file():
        for line in EVENTS.read_text().splitlines():
            event = json.loads(line)
            if event.get("event") != "layer_route" or event.get("run_id") != run_id:
                continue
            route = str(event["route"])
            routes[route] = routes.get(route, 0) + 1
            layers.setdefault(route, set()).add(int(event["layer"]))
            rows.append(event)
    return {
        "routes": routes,
        "layers": {name: sorted(values) for name, values in layers.items()},
        "event_count": len(rows),
    }


def run_request(input_ids: list[int], depth: int, run_id: str) -> dict[str, object]:
    atomic(
        CONTROL,
        {
            "schema_version": 1,
            "run_id": run_id,
            "depth": depth,
            "capture_layer": -1,
            "capture_step": -1,
        },
    )
    flush, flush_raw = post("/flush_cache", {}, timeout=60)
    body = {
        "input_ids": input_ids,
        "sampling_params": {
            "temperature": 0.0,
            "max_new_tokens": 32,
        },
        "return_logprob": True,
        "top_logprobs_num": 10,
        "add_special_tokens": False,
    }
    started = time.monotonic()
    response, raw = post("/generate", body)
    elapsed = time.monotonic() - started
    ids = output_ids(response)
    row = {
        "schema_version": 1,
        "run_id": run_id,
        "depth": depth,
        "request": body,
        "request_sha256": hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "flush_response": flush,
        "flush_response_sha256": hashlib.sha256(flush_raw).hexdigest(),
        "response": response,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "output_ids": ids,
        "text": response.get("text"),
        "finish_reason": (response.get("meta_info") or {}).get("finish_reason"),
        "top_logprobs": (response.get("meta_info") or {}).get(
            "output_top_logprobs"
        ),
        "elapsed_seconds": elapsed,
        "path_counts": event_counts(run_id),
    }
    atomic(ROOT / f"DEPTH_{depth}.json", row)
    return row


def main() -> int:
    ROOT.mkdir(parents=True, exist_ok=True)
    atomic(
        ROOT / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "model_probe_passed": True,
            "trace_science_started": True,
            "depths_completed": [],
            "oracle_started": False,
        },
    )
    tokenizer = AutoTokenizer.from_pretrained("/work/checkpoint")
    input_ids = tokenizer.apply_chat_template(
        [{"role": "user", "content": PROMPT}],
        tokenize=True,
        add_generation_prompt=True,
    )
    if hasattr(input_ids, "get") and input_ids.get("input_ids") is not None:
        input_ids = input_ids["input_ids"]
    if hasattr(input_ids, "tolist"):
        input_ids = input_ids.tolist()
    if input_ids and isinstance(input_ids[0], list):
        input_ids = input_ids[0]
    if not isinstance(input_ids, list) or not all(
        isinstance(value, int) for value in input_ids
    ):
        raise ValueError("tokenizer did not produce integer token IDs")
    rows = []
    for depth in DEPTHS:
        rows.append(run_request(input_ids, depth, f"depth-{depth}"))
        state = json.loads((ROOT / "INVOCATION_STATE.json").read_text())
        state["depths_completed"].append(depth)
        atomic(ROOT / "INVOCATION_STATE.json", state)
    baseline = rows[0]["output_ids"]
    curve = []
    for row in rows:
        divergence = first_divergence(baseline, row["output_ids"])
        curve.append(
            {
                "depth": row["depth"],
                "first_output_divergence": divergence,
                "output_ids_equal": divergence is None,
                "path_counts": row["path_counts"],
            }
        )
    divergent = [item for item in curve[1:] if item["first_output_divergence"] is not None]
    if not divergent:
        target = None
    else:
        first = divergent[0]
        target = {
            "depth": first["depth"],
            "layer": int(first["depth"]) - 1,
            "output_token_index": first["first_output_divergence"],
            "decode_step": int(first["first_output_divergence"]),
        }
    terminal = {
        "schema_version": 1,
        "classification": "layer_depth_trace_complete",
        "prompt": PROMPT,
        "input_ids": input_ids,
        "depths": list(DEPTHS),
        "curve": curve,
        "first_divergent_target": target,
        "rows": rows,
    }
    atomic(ROOT / "TRACE_TERMINAL.json", terminal)
    if target is None:
        return 74
    atomic(
        CONTROL,
        {
            "schema_version": 1,
            "run_id": "oracle-capture",
            "depth": target["depth"],
            "capture_layer": target["layer"],
            "capture_step": target["decode_step"],
        },
    )
    state = json.loads((ROOT / "INVOCATION_STATE.json").read_text())
    state["oracle_started"] = True
    atomic(ROOT / "INVOCATION_STATE.json", state)
    post("/flush_cache", {}, timeout=60)
    capture_body = rows[int(DEPTHS.index(target["depth"]))]["request"]
    response, raw = post("/generate", capture_body)
    capture = {
        "schema_version": 1,
        "target": target,
        "response": response,
        "response_sha256": hashlib.sha256(raw).hexdigest(),
        "output_ids": output_ids(response),
        "matches_trace_row": output_ids(response)
        == rows[int(DEPTHS.index(target["depth"]))]["output_ids"],
        "path_counts": event_counts("oracle-capture"),
    }
    atomic(ROOT / "ORACLE_CAPTURE_REQUEST.json", capture)
    if not (ROOT / "captured-hidden.pt").is_file():
        raise RuntimeError("trace completed without hidden-state capture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
