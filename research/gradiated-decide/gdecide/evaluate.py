"""Batched Decision Index runs for Decider-protocol checkpoints, sharded one process per GPU.

    torchrun --nproc-per-node 8 -m gdecide.evaluate --suite SUITE_DIR --checkpoint CKPT [--adapter DIR] --out RUN_DIR
        [--sample sample-ids.json] [--backend knowline [--option KEY=VALUE ...]]

Each rank answers the rows whose index modulo the world size equals its rank and appends them to
``results-<rank>.jsonl`` in the kit's result format. Resume skips run ids that already have a non-error status.
``gdecide.score`` merges the shards and scores them with the kit's own scorer.

``--backend knowline`` runs a KnowLine (Gemma 4) checkpoint through ``gdecide.backends.knowline`` instead of the
Decider; ``--option`` passes its front-end settings (read_twice, twice_max_tokens, header_when_long, temperatures,
front_end_dir), which default to KnowLine's release settings.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path


def stamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def suite_rows(suite_dir: str, edition: str, sample: set[str] | None):
    from decision_index.suite.io import Suite

    for row in Suite(suite_dir, edition).rows(apply_exclusions=True):
        if sample is None or row["_evaluation"]["run_id"] in sample:
            yield row


def load_decider(checkpoint: str, adapter: str | None, device: str, max_length: int, batch_tokens: int):
    import torch
    from safetensors.torch import load_file

    from pplx_decider import Decider

    decider = Decider.from_pretrained(checkpoint, device=device, max_length=max_length, batch_tokens=batch_tokens)
    if adapter:
        from peft import PeftModel

        merged = PeftModel.from_pretrained(decider.backbone, adapter).merge_and_unload()
        decider.backbone = merged.requires_grad_(False).eval()
        readout = Path(adapter) / "readout.safetensors"
        if readout.exists():
            decider.readout.load_state_dict(load_file(str(readout)))
        config = Path(adapter) / "gdecide.json"
        if config.exists():
            temperature = json.loads(config.read_text()).get("temperature")
            if temperature:
                decider.temperature = float(temperature)
        torch.cuda.empty_cache()
    return decider


def backend_options(pairs: list[str]) -> dict:
    out = {}
    for pair in pairs:
        key, _, value = pair.partition("=")
        try:
            out[key] = json.loads(value)
        except json.JSONDecodeError:
            out[key] = value
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", required=True)
    parser.add_argument("--edition", default="0.3")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--adapter")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sample", help="JSON list of run ids to evaluate")
    parser.add_argument("--chunk", type=int, default=64)
    parser.add_argument("--max-length", type=int, default=131072)
    parser.add_argument("--batch-tokens", type=int, default=32768)
    parser.add_argument("--temperature", type=float)
    parser.add_argument("--backend", choices=("pplx", "knowline", "knowline-http", "mammoth"), default="pplx")
    parser.add_argument("--option", action="append", default=[], help="backend option KEY=VALUE (knowline)")
    args = parser.parse_args()

    rank = int(os.environ.get("RANK", 0))
    world = int(os.environ.get("WORLD_SIZE", 1))
    local = int(os.environ.get("LOCAL_RANK", 0))
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"results-{rank}.jsonl"
    done = set()
    if path.exists():
        lines = path.read_text().splitlines()
        good = []
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if record["status"] != "error":
                done.add(record["run_id"])
                good.append(line)
        path.write_text("".join(x + "\n" for x in good))

    sample = set(json.loads(Path(args.sample).read_text())) if args.sample else None
    rows = [r for i, r in enumerate(suite_rows(args.suite, args.edition, sample)) if i % world == rank]
    rows = [r for r in rows if r["_evaluation"]["run_id"] not in done]
    rows.sort(key=lambda r: r["_evaluation"].get("proxy_tokens", 0))

    import torch

    device = f"cuda:{local}"
    torch.cuda.set_device(local)
    if args.backend == "mammoth":
        from gdecide.backends.mammoth import MammothDecider

        decider = MammothDecider(args.checkpoint, device)
        unsupported = decider.unsupported
        temperature = None
        engine = f"mammoth:{Path(args.checkpoint).name}"
        settings = decider.settings
    elif args.backend == "knowline-http":
        from gdecide.backends.knowline_http import KnowLineHTTP

        options = backend_options(args.option)
        port = int(options.pop("base_port", 8080)) + local
        decider = KnowLineHTTP(f"http://127.0.0.1:{port}", **options)
        unsupported = decider.unsupported
        temperature = None
        engine = f"knowline-http:{Path(args.checkpoint).name}"
        settings = decider.settings
        decider.temperature = 1.0
    elif args.backend == "knowline":
        from gdecide.backends.knowline import KnowLineDecider

        if args.adapter:
            raise SystemExit("--adapter is not supported with --backend knowline")
        options = backend_options(args.option)
        decider = KnowLineDecider.from_pretrained(args.checkpoint, device=device, max_length=args.max_length, batch_tokens=args.batch_tokens, temperature=args.temperature or 1.0, **options)
        unsupported = decider.unsupported
        temperature = None
        engine = f"knowline:{Path(args.checkpoint).name}"
        settings = decider.renderer.settings
    else:
        from pplx_decider.protocol import LengthError, RequestError

        decider = load_decider(args.checkpoint, args.adapter, device, args.max_length, args.batch_tokens)
        unsupported = (LengthError, RequestError)
        temperature = args.temperature
        engine = "gradiated-decide" + (f":{Path(args.adapter).name}" if args.adapter else ":base")
        settings = {}
    (out / "environment.json").write_text(json.dumps({"backend": args.backend, "checkpoint": args.checkpoint, "adapter": args.adapter, "temperature": temperature or decider.temperature, "max_length": args.max_length, "batch_tokens": args.batch_tokens, "settings": settings, "world": world, "torch": torch.__version__, "gpu": torch.cuda.get_device_name(local)}, indent=2))

    def record(row, status, response=None, error=None, ms=0.0):
        r = {**row["_evaluation"], "started_utc": stamp(), "engine": engine, "status": status, "completed_utc": stamp(), "total_wall_ms": ms, "model_request_wall_ms": ms}
        if response is not None:
            r["response"] = {"model": engine, **response}
        if error is not None:
            r["error"] = error
        return r

    started = time.perf_counter()
    with path.open("a") as log:
        for start in range(0, len(rows), args.chunk):
            chunk = rows[start : start + args.chunk]
            requests = [{"state": r["state"], "questions": r["questions"]} for r in chunk]
            t = time.perf_counter()
            try:
                responses = decider.decide(requests, temperature=temperature)
                ms = (time.perf_counter() - t) * 1000 / len(chunk)
                records = [record(r, "ok", response=resp, ms=ms) for r, resp in zip(chunk, responses, strict=True)]
            except Exception:
                torch.cuda.empty_cache()
                records = []
                for r, req in zip(chunk, requests, strict=True):
                    t = time.perf_counter()
                    try:
                        records.append(record(r, "ok", response=decider.decide(req, temperature=temperature), ms=(time.perf_counter() - t) * 1000))
                    except unsupported as exc:
                        records.append(record(r, "unsupported", error=str(exc)))
                    except torch.OutOfMemoryError as exc:
                        torch.cuda.empty_cache()
                        records.append(record(r, "unsupported", error=f"out of memory: {exc}"))
                    except Exception as exc:
                        records.append(record(r, "error", error=f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}"))
            log.write("".join(json.dumps(x, separators=(",", ":")) + "\n" for x in records))
            log.flush()
            if rank == 0 and (start // args.chunk) % 20 == 0:
                print(json.dumps({"rank": rank, "done": start + len(chunk), "of": len(rows), "elapsed_s": round(time.perf_counter() - started, 1)}), flush=True)
    print(json.dumps({"rank": rank, "complete": len(rows), "elapsed_s": round(time.perf_counter() - started, 1)}), flush=True)


if __name__ == "__main__":
    main()
