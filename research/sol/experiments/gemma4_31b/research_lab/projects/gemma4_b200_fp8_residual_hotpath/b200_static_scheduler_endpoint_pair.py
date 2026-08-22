#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
import urllib.request


MODEL = "google/gemma-4-31B-it"


def atomic_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def request(index: int, body: dict, host: str, output: Path) -> dict:
    (output / f"request-{index:02}.json").write_bytes(canonical(body))
    start = time.monotonic()
    raw: list[bytes] = []
    ids: list[int] = []
    text = ""
    usage: dict = {}
    error = None
    try:
        req = urllib.request.Request(
            host + "/v1/completions", canonical(body), {"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=1800) as response:
            for line in response:
                raw.append(line)
                if line.startswith(b"data: ") and line.strip() != b"data: [DONE]":
                    item = json.loads(line[6:])
                    choice = (item.get("choices") or [{}])[0]
                    ids.extend(choice.get("token_ids") or [])
                    text += choice.get("text") or ""
                    usage = item.get("usage") or usage
    except Exception as exc:
        error = repr(exc)
    (output / f"response-{index:02}.sse").write_bytes(b"".join(raw))
    return {
        "index": index, "error": error, "seconds": time.monotonic() - start,
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "returned_token_ids": len(ids), "nonempty": bool(text),
        "token_ids_sha256": hashlib.sha256(canonical(ids)).hexdigest(),
        "request_sha256": hashlib.sha256(canonical(body)).hexdigest(),
    }


def driver(args: argparse.Namespace) -> int:
    args.output.mkdir(parents=True, exist_ok=True)
    prefix = [1000 + ((j * 7919 + 17) % 48000) for j in range(535)]
    bodies = []
    for index in range(32):
        suffix = [60000 + index] + [
            1000 + ((index * 4214 + j * 1543) % 48000) for j in range(3678)
        ]
        bodies.append({"model": MODEL, "prompt": prefix + suffix, "max_tokens": 358,
                       "min_tokens": 358, "ignore_eos": True, "temperature": 0,
                       "seed": 20260728 + index, "stream": True,
                       "stream_options": {"include_usage": True},
                       "return_token_ids": True, "add_special_tokens": False})
    start = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as executor:
        rows = list(executor.map(lambda x: request(x[0], x[1], args.host, args.output), enumerate(bodies)))
    complete = all(
        r["error"] is None and r["prompt_tokens"] == 4214
        and r["completion_tokens"] == 358 and r["returned_token_ids"] == 358
        and r["nonempty"] and math.isfinite(r["seconds"]) for r in rows
    )
    atomic_json(args.output / "TERMINAL.json", {
        "schema_version": 1, "classification": "endpoint_measurement" if complete else "endpoint_invalid",
        "arm": args.arm, "complete_requests": sum(r["error"] is None for r in rows),
        "batch_seconds": time.monotonic() - start,
        "service_seconds_per_request": (time.monotonic() - start) / 32,
        "rows": rows, "workload": "c32/4214/358/text-only/non-reasoning",
    })
    return 0


PATCH = r'''
import importlib.util, os, torch
from vllm import _custom_ops as ops
path=os.environ.get("M32_STATIC_SCHEDULER_MODULE")
if path:
 spec=importlib.util.spec_from_file_location("m32_static_scheduler_ext",path)
 module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
 stock=ops.cutlass_scaled_mm
 def patched(a,b,scale_a=None,scale_b=None,out_dtype=None,*args,**kwargs):
  if a.ndim==2 and a.shape[0]==32 and out_dtype==torch.bfloat16 and scale_a is not None and scale_b is not None:
   return module.m32_static_persistent(a,b,scale_a,scale_b)
  return stock(a,b,scale_a=scale_a,scale_b=scale_b,out_dtype=out_dtype,*args,**kwargs)
 ops.cutlass_scaled_mm=patched
'''


def call(command: list[str], output: Path) -> None:
    with output.open("a") as handle:
        subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, check=True)


def wait_ready(port: int, name: str, root: Path) -> None:
    for _ in range(240):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=2).read()
            return
        except Exception:
            time.sleep(2)
    raise RuntimeError(f"server_not_ready:{name}")


def remote(args: argparse.Namespace) -> int:
    root = args.root.resolve()
    artifacts = root / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    patch = root / "patch"
    patch.mkdir(exist_ok=True)
    (patch / "sitecustomize.py").write_text(PATCH)
    states = {"candidate_science_started": False, "stock_science_started": False}
    atomic_json(artifacts / "INVOCATION_STATE.json", states)
    arms = (("stock", 31000, False), ("candidate", 31001, True))
    for name, port, candidate in arms:
        arm = artifacts / name
        arm.mkdir(exist_ok=True)
        container = f"b200-static-endpoint-{name}"
        subprocess.run(["sudo", "-n", "docker", "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        command = ["sudo", "-n", "docker", "run", "-d", "--name", container, "--gpus", "all", "--ipc=host", "--network", "host",
                   "-v", f"{args.checkpoint}:/checkpoint:ro", "-v", f"{patch}:/patch:ro"]
        if candidate:
            command += ["-v", f"{args.build}:/build:ro", "-e", "PYTHONPATH=/patch", "-e", f"M32_STATIC_SCHEDULER_MODULE=/build/{args.module}"]
        command += ["--entrypoint", "vllm", args.image, "serve", "/checkpoint", "--served-model-name", MODEL,
                    "--host", "127.0.0.1", "--port", str(port), "--dtype", "bfloat16",
                    "--quantization", "fp8", "--max-model-len", "4608", "--max-num-seqs", "32",
                    "--max-num-batched-tokens", "134848", "--gpu-memory-utilization", "0.90", "--enable-prefix-caching"]
        call(command, arm / "server.log")
        wait_ready(port, name, root)
        states[f"{name}_science_started"] = True
        atomic_json(artifacts / "INVOCATION_STATE.json", states)
        call(["python3", str(Path(__file__).resolve()), "--driver", "--host", f"http://127.0.0.1:{port}", "--arm", name, "--output", str(arm)], arm / "driver.log")
        call(["sudo", "-n", "docker", "logs", container], arm / "server.log")
        subprocess.run(["sudo", "-n", "docker", "rm", "-f", container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    stock = json.loads((artifacts / "stock/TERMINAL.json").read_text())
    candidate = json.loads((artifacts / "candidate/TERMINAL.json").read_text())
    semantic = [r["token_ids_sha256"] for r in stock["rows"]] == [r["token_ids_sha256"] for r in candidate["rows"]]
    valid = stock["classification"] == candidate["classification"] == "endpoint_measurement" and semantic
    atomic_json(artifacts / "PAIR_TERMINAL.json", {
        "schema_version": 1, "classification": "static_scheduler_endpoint_pair" if valid else "endpoint_pair_invalid",
        "stock": stock, "candidate": candidate, "semantic_token_ids_equal": semantic,
        "candidate_reduction_fraction": 1 - candidate["service_seconds_per_request"] / stock["service_seconds_per_request"] if valid else None,
    })
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--driver", action="store_true")
    parser.add_argument("--remote", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--arm")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--image")
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--build", type=Path)
    parser.add_argument("--module")
    args = parser.parse_args()
    if args.driver:
        return driver(args)
    if args.remote:
        return remote(args)
    parser.error("--driver or --remote required")


if __name__ == "__main__":
    raise SystemExit(main())
