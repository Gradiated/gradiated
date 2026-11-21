#!/usr/bin/env python3
"""Prompt-cartridge serving benchmark for the SGLang bundle, using only the stdlib.

Subcommands (see CARTRIDGE.md):
  synth        write synthetic cartridges that reuse a slot-ID set
  resolver     serve SGLANG_LORA_RESOLVER_URL for a directory of cartridges
  decode       mixed-batch decode throughput and ITL: N cartridges vs none
  prefill      cold and warm cartridge TTFT against base-model controls
  correctness  first-token logprobs against a research reference
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import http.server
import itertools
import json
import math
import os
import statistics
import struct
import sys
import time
import urllib.request
import uuid
from pathlib import Path

WORKSPACE = "01980000-0000-7000-8000-00000000c0de"
FORMAT = "gradiated.cartridge/1"
# bf16 high byte: keep the sign, force a small exponent (|x| in [2^-7, 2^-5)).
_HIGH = bytes((value & 0x80) | 0x3C for value in range(256))


def read_header(path: Path) -> tuple[dict, int]:
    with path.open("rb") as source:
        size = struct.unpack("<Q", source.read(8))[0]
        return json.loads(source.read(size)), 8 + size


def slot_ids(path: Path) -> list[int]:
    header, start = read_header(path)
    entry = header["slot_token_ids"]
    with path.open("rb") as source:
        source.seek(start + entry["data_offsets"][0])
        count = entry["shape"][0]
        return list(struct.unpack(f"<{count}q", source.read(8 * count)))


def synth(args: argparse.Namespace) -> None:
    """Random cartridges with the slot IDs of ``--slots-from`` (read, never copied)."""
    slots = slot_ids(Path(args.slots_from))[: args.tokens]
    if len(slots) != args.tokens:
        raise SystemExit("--slots-from has fewer slot IDs than --tokens")
    root = Path(args.output)
    for index in range(args.count):
        rows = bytearray(os.urandom(args.tokens * args.hidden * 2))
        rows[1::2] = bytes(rows[1::2]).translate(_HIGH)
        ids = struct.pack(f"<{args.tokens}q", *slots)
        header = {
            "__metadata__": {"format": FORMAT, "placement": "system_prompt_start"},
            "embeddings": {
                "dtype": "BF16",
                "shape": [args.tokens, args.hidden],
                "data_offsets": [0, len(rows)],
            },
            "slot_token_ids": {
                "dtype": "I64",
                "shape": [args.tokens],
                "data_offsets": [len(rows), len(rows) + len(ids)],
            },
        }
        encoded = json.dumps(header).encode()
        directory = root / f"bench-{index:04d}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "cartridge.safetensors").write_bytes(
            struct.pack("<Q", len(encoded)) + encoded + bytes(rows) + ids
        )
    print(json.dumps({"cartridges": args.count, "output": str(root)}))


def resolver(args: argparse.Namespace) -> None:
    root = Path(args.root).resolve()
    known: dict[str, dict] = {}

    def describe(name: str) -> dict:
        if name not in known:
            path = root / name / "cartridge.safetensors"
            if path.parent.parent != root or not path.is_file():
                raise KeyError(name)
            header, _ = read_header(path)
            known[name] = {
                "kind": "cartridge",
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "num_tokens": header["embeddings"]["shape"][0],
            }
        return known[name]

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                if body.get("workspace_id") != WORKSPACE:
                    raise KeyError(body.get("workspace_id"))
                payload, status = json.dumps(describe(body["name"])).encode(), 200
            except KeyError:
                payload, status = b'{"error":"adapter_unavailable"}', 503
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(json.dumps({"resolver": f"http://127.0.0.1:{args.port}/resolve"}), flush=True)
    server.serve_forever()


def model_name(args: argparse.Namespace, index: int | None) -> str:
    return args.base_model if index is None else f"{WORKSPACE}/bench-{index:04d}"


def post(args: argparse.Namespace, path: str, body: dict):
    request = urllib.request.Request(
        args.base_url.rstrip("/") + path,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return urllib.request.urlopen(request, timeout=args.timeout)


def stream_chat(args: argparse.Namespace, model: str, messages: list, max_tokens: int):
    """Token timestamps of one streamed completion (DSPARK may emit several per chunk).

    Tokens are counted from per-chunk usage, not logprobs: SGLang builds streamed
    logprobs on the HTTP event loop, which at 64 streams becomes the bottleneck.
    """
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0,
        "ignore_eos": True,
        "stream": True,
        "stream_options": {"include_usage": True, "continuous_usage_stats": True},
    }
    sent = time.perf_counter()
    stamps, usage, seen = [], {}, 0
    with post(args, "/v1/chat/completions", body) as response:
        for raw in response:
            line = raw.decode().strip()
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            event = json.loads(line[6:])
            if event.get("usage"):
                usage = event["usage"]
                completed = usage.get("completion_tokens") or 0
                stamps.extend([time.perf_counter()] * (completed - seen))
                seen = max(seen, completed)
    return {"sent": sent, "stamps": stamps, "usage": usage}


def unique_messages(index: int, words: int) -> list:
    return [
        {"role": "system", "content": "You are a careful assistant."},
        {
            "role": "user",
            "content": f"Request {index} {uuid.uuid4()}. "
            + "Describe the plan in detail. " * words,
        },
    ]


def decode_round(args: argparse.Namespace, with_cartridges: bool) -> dict:
    with concurrent.futures.ThreadPoolExecutor(args.batch) as pool:
        results = list(
            pool.map(
                lambda index: stream_chat(
                    args,
                    model_name(args, index if with_cartridges else None),
                    unique_messages(index, args.prompt_words),
                    args.output_tokens,
                ),
                range(args.batch),
            )
        )
    # Steady state: every request is decoding and none has finished.
    start = max(result["stamps"][0] for result in results)
    end = min(result["stamps"][-1] for result in results)
    if end <= start:
        raise SystemExit("no steady decode window; raise --output-tokens")
    tokens = sum(
        sum(start <= stamp <= end for stamp in result["stamps"]) for result in results
    )
    gaps = []
    for result in results:
        window = [stamp for stamp in result["stamps"] if start <= stamp <= end]
        gaps.extend(b - a for a, b in itertools.pairwise(window) if b > a)
    itl = [
        (result["stamps"][-1] - result["stamps"][0]) / (len(result["stamps"]) - 1)
        for result in results
    ]
    return {
        "cartridges": with_cartridges,
        "decode_tokens_per_second": tokens / (end - start),
        "itl_mean_ms": 1000 * statistics.fmean(itl),
        "chunk_gap_p50_ms": 1000 * statistics.median(gaps),
        "chunk_gap_p99_ms": 1000 * sorted(gaps)[int(0.99 * (len(gaps) - 1))],
        "window_seconds": end - start,
        "prompt_tokens": [result["usage"].get("prompt_tokens") for result in results],
    }


def decode(args: argparse.Namespace) -> int:
    decode_round(args, True)  # resolve and load every cartridge
    decode_round(args, False)
    rounds = []
    for repeat in range(args.repeats):
        order = (True, False) if repeat % 2 == 0 else (False, True)
        rounds.extend(decode_round(args, arm) for arm in order)

    def mean(arm: bool, key: str) -> float:
        return statistics.fmean(r[key] for r in rounds if r["cartridges"] == arm)

    throughput = mean(True, "decode_tokens_per_second") / mean(
        False, "decode_tokens_per_second"
    )
    itl = mean(True, "itl_mean_ms") / mean(False, "itl_mean_ms")
    summary = {
        "batch": args.batch,
        "rounds": rounds,
        "throughput_ratio": throughput,
        "itl_ratio": itl,
        "pass": throughput >= 1 - args.tolerance and itl <= 1 + args.tolerance,
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


def ttft(args: argparse.Namespace, model: str, messages: list) -> tuple[float, dict]:
    body = {"model": model, "messages": messages, "max_tokens": 1, "temperature": 0}
    started = time.perf_counter()
    with post(args, "/v1/chat/completions", body) as response:
        usage = json.loads(response.read())["usage"]
    return time.perf_counter() - started, usage


def flush(args: argparse.Namespace) -> None:
    post(args, "/flush_cache", {}).close()


def prefill(args: argparse.Namespace) -> int:
    system = "You are a careful assistant. " * args.system_words
    padding = "Background note. " * args.cartridge_tokens

    def messages(nonce: str, extra: str = "") -> list:
        return [
            {"role": "system", "content": extra + system},
            {
                "role": "user",
                "content": f"{nonce} " + "Summarize the plan. " * args.prompt_words,
            },
        ]

    samples = {
        name: [] for name in ("base", "base_plus_k", "cold", "warm", "base_warm")
    }
    usage = {}
    for trial in range(args.repeats):
        cartridge = args.first_cold + trial
        flush(args)
        samples["base"].append(
            ttft(args, args.base_model, messages(str(uuid.uuid4())))[0]
        )
        flush(args)
        elapsed, usage["base_plus_k"] = ttft(
            args, args.base_model, messages(str(uuid.uuid4()), padding)
        )
        samples["base_plus_k"].append(elapsed)
        flush(args)
        elapsed, usage["cold"] = ttft(
            args, model_name(args, cartridge), messages(str(uuid.uuid4()))
        )
        samples["cold"].append(elapsed)
        elapsed, usage["warm"] = ttft(
            args, model_name(args, cartridge), messages(str(uuid.uuid4()))
        )
        samples["warm"].append(elapsed)
        ttft(args, args.base_model, messages(str(uuid.uuid4())))
        samples["base_warm"].append(
            ttft(args, args.base_model, messages(str(uuid.uuid4())))[0]
        )
    summary = {
        name: {"median_ms": 1000 * statistics.median(values), "samples": len(values)}
        for name, values in samples.items()
    }
    summary["usage"] = usage
    summary["cold_vs_base_plus_k"] = (
        summary["cold"]["median_ms"] / summary["base_plus_k"]["median_ms"]
    )
    summary["warm_vs_base_warm"] = (
        summary["warm"]["median_ms"] / summary["base_warm"]["median_ms"]
    )
    print(json.dumps(summary, indent=2))
    return 0


def top_logprobs(
    args: argparse.Namespace, model: str, messages: list
) -> dict[str, float]:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 1,
        "temperature": 0,
        "logprobs": True,
        "top_logprobs": args.top_k,
    }
    if messages and messages[-1]["role"] == "assistant":
        body["continue_final_message"] = True
    with post(args, "/v1/chat/completions", body) as response:
        entry = json.loads(response.read())["choices"][0]["logprobs"]["content"][0]
    return {item["token"]: item["logprob"] for item in entry["top_logprobs"]}


def compare(reference: dict[str, float], served: dict[str, float], top: int) -> dict:
    ranked = sorted(reference, key=reference.get, reverse=True)[:top]
    deltas = [abs(reference[token] - served.get(token, -math.inf)) for token in ranked]
    return {
        "same_argmax": max(served, key=served.get) == ranked[0],
        "max_abs_logprob_delta": max(deltas),
    }


def correctness(args: argparse.Namespace) -> int:
    cases = json.loads(Path(args.cases).read_text())["cases"]
    if args.record:
        reference = [
            {"top_logprobs": top_logprobs(args, args.cartridge_model, case["messages"])}
            for case in cases
        ]
        Path(args.record).write_text(json.dumps({"cases": reference}))
        print(json.dumps({"recorded": len(reference), "output": args.record}))
        return 0
    references = json.loads(Path(args.reference).read_text())["cases"]
    background = None
    if args.background:
        pool = concurrent.futures.ThreadPoolExecutor(args.background)
        background = [
            pool.submit(
                stream_chat,
                args,
                model_name(args, None if index % 4 == 0 else index),
                unique_messages(index, 64),
                256,
            )
            for index in range(1, args.background + 1)
        ]
        time.sleep(args.background_delay)
    report = []
    for case, reference in zip(cases, references, strict=True):
        served = top_logprobs(args, args.cartridge_model, case["messages"])
        base = top_logprobs(args, args.base_model, case["messages"])
        result = compare(reference["top_logprobs"], served, args.compare_top)
        result["base_max_abs_logprob_delta"] = compare(
            reference["top_logprobs"], base, args.compare_top
        )["max_abs_logprob_delta"]
        result["pass"] = (
            result["same_argmax"]
            and result["max_abs_logprob_delta"] <= args.logprob_tolerance
            and result["base_max_abs_logprob_delta"] > args.applied_threshold
        )
        report.append(result)
    if background:
        for future in background:
            future.result()
    summary = {"cases": report, "pass": all(case["pass"] for case in report)}
    print(json.dumps(summary, indent=2))
    return 0 if summary["pass"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)

    command = commands.add_parser("synth")
    command.add_argument("--slots-from", required=True)
    command.add_argument("--output", required=True)
    command.add_argument("--count", type=int, default=96)
    command.add_argument("--tokens", type=int, default=256)
    command.add_argument("--hidden", type=int, default=5120)

    command = commands.add_parser("resolver")
    command.add_argument("--root", required=True)
    command.add_argument("--port", type=int, default=31999)

    for name in ("decode", "prefill", "correctness"):
        command = commands.add_parser(name)
        command.add_argument("--base-url", default="http://127.0.0.1:30000")
        command.add_argument(
            "--base-model", default="deepseek-ai/DeepSeek-V4.1-Flash-1017"
        )
        command.add_argument("--timeout", type=float, default=900)
        command.add_argument("--repeats", type=int, default=4)
        command.add_argument("--prompt-words", type=int, default=64)
        command.add_argument("--tolerance", type=float, default=0.02)
        if name == "decode":
            command.add_argument("--batch", type=int, default=64)
            command.add_argument("--output-tokens", type=int, default=512)
        if name == "prefill":
            command.add_argument("--system-words", type=int, default=256)
            command.add_argument("--cartridge-tokens", type=int, default=256)
            command.add_argument("--first-cold", type=int, default=64)
        if name == "correctness":
            command.add_argument("--cases", required=True)
            reference = command.add_mutually_exclusive_group(required=True)
            reference.add_argument("--reference")
            reference.add_argument("--record")
            command.add_argument("--cartridge-model", required=True)
            command.add_argument("--logprob-tolerance", type=float, default=0.02)
            command.add_argument("--top-k", type=int, default=20)
            command.add_argument("--compare-top", type=int, default=5)
            command.add_argument("--applied-threshold", type=float, default=0.1)
            command.add_argument("--background", type=int, default=0)
            command.add_argument("--background-delay", type=float, default=2.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    handlers = {
        "synth": synth,
        "resolver": resolver,
        "decode": decode,
        "prefill": prefill,
        "correctness": correctness,
    }
    return handlers[args.command](args) or 0


if __name__ == "__main__":
    sys.exit(main())
