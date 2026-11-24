#!/usr/bin/env python3
"""Cartridge gating checks against a production replica or the gateway, using only the stdlib.

cartridge_bench.py drives a dev server with a local resolver. This wrapper runs
the checks that gate a rollout against any OpenAI-compatible endpoint with real
task-version model names:

  identity-files  write two identity cartridges: the checkpoint's own embedding
                  rows of the slot IDs (bit-exact bf16), differing only in metadata
  probe           check what the endpoint passes through (usage, ignore_eos,
                  logprobs, continue_final_message, metrics)
  decode          batch-N decode, ABBA: N different cartridges vs a slot-text
                  control (same token IDs and KV length) vs the base model
  identity        first-token logprobs of the identity cartridge vs the base model
                  with the slot text, against a second identity cartridge as the
                  noise floor, alone or with background load
  isolation       cached-prefix isolation: a second cartridge with the same slot
                  IDs, and the base model with the slot text, must not reuse the
                  first cartridge's cached prefix

The API key is read from $CARTRIDGE_BENCH_API_KEY, never from the command
line. Cartridge model names come from --cartridges, a text file with one
task-version model name per line. See CARTRIDGE.md, "Production replica".
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import struct
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cartridge_bench as cb  # noqa: E402

# --- files -------------------------------------------------------------------


def _safetensors_header(path: Path) -> tuple[dict, int]:
    with path.open("rb") as source:
        size = struct.unpack("<Q", source.read(8))[0]
        return json.loads(source.read(size)), 8 + size


def _write_cartridge(
    path: Path, rows: bytes, slots: list[int], hidden: int, metadata: dict
) -> str:
    ids = struct.pack(f"<{len(slots)}q", *slots)
    header = {
        "__metadata__": {
            "format": cb.FORMAT,
            "placement": "system_prompt_start",
            **metadata,
        },
        "embeddings": {
            "dtype": "BF16",
            "shape": [len(slots), hidden],
            "data_offsets": [0, len(rows)],
        },
        "slot_token_ids": {
            "dtype": "I64",
            "shape": [len(slots)],
            "data_offsets": [len(rows), len(rows) + len(ids)],
        },
    }
    encoded = json.dumps(header).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = struct.pack("<Q", len(encoded)) + encoded + rows + ids
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def identity_files(args: argparse.Namespace) -> int:
    """Identity cartridges: embedding rows of the slot IDs, read from the checkpoint without torch."""
    model = Path(args.model)
    weight_map = json.loads((model / "model.safetensors.index.json").read_text())[
        "weight_map"
    ]
    names = [
        k
        for k in weight_map
        if k.split(".")[-2:] in (["embed", "weight"], ["embed_tokens", "weight"])
        and "mtp" not in k
    ]
    if not names:
        raise SystemExit("no token embedding in the checkpoint index")
    key = min(names, key=len)
    shard = model / weight_map[key]
    header, start = _safetensors_header(shard)
    entry = header[key]
    if entry["dtype"] != "BF16":
        raise SystemExit(
            f"{key} is {entry['dtype']}; an identity cartridge needs bf16 embeddings"
        )
    vocab, hidden = entry["shape"]
    slots = cb.slot_ids(Path(args.slots_from))[: args.tokens]
    rows = bytearray()
    with shard.open("rb") as source:
        for token in slots:
            if not 0 <= token < vocab:
                raise SystemExit("slot ID outside the embedding")
            source.seek(start + entry["data_offsets"][0] + token * hidden * 2)
            rows += source.read(hidden * 2)
    out = Path(args.output)
    # Same rows, different metadata: two digests, so two cache namespaces.
    digests = {
        "identity-a": _write_cartridge(
            out / "identity-a/cartridge.safetensors", bytes(rows), slots, hidden, {}
        ),
        "identity-b": _write_cartridge(
            out / "identity-b/cartridge.safetensors",
            bytes(rows),
            slots,
            hidden,
            {"separator": "\n\n"},
        ),
    }
    print(
        json.dumps(
            {
                "embedding": key,
                "hidden_size": hidden,
                "tokens": len(slots),
                "sha256": digests,
            },
            indent=2,
        )
    )
    return 0


# --- requests ----------------------------------------------------------------


def slot_text(args: argparse.Namespace) -> str:
    """The cartridge's slot text: a text file, or a slots JSON whose characters are single tokens."""
    path = Path(args.slot_text)
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        ids, text = data["ids"][: args.tokens], data["text"]
        if len(text) < len(ids):
            raise SystemExit("slots JSON text is shorter than its IDs")
        return text[: len(ids)]
    return path.read_text()


def with_slots(messages: list, text: str, separator: str = "\n\n") -> list:
    if messages and messages[0]["role"] in ("system", "developer"):
        return [
            {**messages[0], "content": text + separator + messages[0]["content"]},
            *messages[1:],
        ]
    return [{"role": "system", "content": text + separator}, *messages]


def retrying(fn, *a, attempts: int = 30):
    """Retry queue-full (429) and unavailable (503) answers from a router with a small queue."""
    for attempt in range(attempts):
        try:
            return fn(*a)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 503) or attempt == attempts - 1:
                raise
            time.sleep(0.5 + random.random())


def top_logprobs(
    args, model: str, messages: list, cache_salt: str | None = None
) -> dict:
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": 1,
        "temperature": 0,
        "logprobs": True,
        "top_logprobs": 20,
    }
    if messages[-1]["role"] == "assistant":
        body["continue_final_message"] = True
    if cache_salt is not None:
        body["cache_salt"] = cache_salt

    def call():
        with cb.post(args, "/v1/chat/completions", body) as response:
            return json.loads(response.read())

    data = retrying(call)
    entry = data["choices"][0]["logprobs"]["content"][0]
    usage = data.get("usage") or {}
    return {
        "top_logprobs": {i["token"]: i["logprob"] for i in entry["top_logprobs"]},
        "prompt_tokens": usage.get("prompt_tokens"),
        "cached_tokens": (usage.get("prompt_tokens_details") or {}).get(
            "cached_tokens"
        ),
    }


def synthetic_cases(count: int, words: int, seed: int) -> list:
    """Deterministic long-system-prompt chat cases with an assistant prefix cut at ``count`` points."""
    rng = random.Random(seed)
    vocab = (
        "plan budget review order supplier invoice schedule ticket customer warehouse delivery route "
        "account report summary policy contract window quote shipment return refund inventory audit"
    ).split()
    system = (
        "You are the operations assistant for a logistics team. Rules: "
        + " ".join(rng.choice(vocab) for _ in range(words))
        + "."
    )
    user = "Summarize what the team should do next, step by step."
    answer = (
        "First, confirm the open orders and their delivery windows. Then check the supplier invoices "
        "against the contract quotes, flag any refund or return, and update the inventory audit. "
        "Finally, write a short report for the account owner with the route schedule."
    ).split(" ")
    cuts = [round(i * (len(answer) - 1) / (count - 1)) for i in range(count)]
    return [
        {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
                {"role": "assistant", "content": " ".join(answer[:cut])},
            ]
        }
        for cut in cuts
    ]


def stats(xs: list, ys: list) -> dict:
    deltas, argmax = [], []
    for x, y in zip(xs, ys, strict=True):
        r = cb.compare(x["top_logprobs"], y["top_logprobs"], 5)
        deltas.append(r["max_abs_logprob_delta"])
        argmax.append(r["same_argmax"])
    return {
        "n": len(deltas),
        "median": statistics.median(deltas),
        "max": max(deltas),
        "same_argmax_fraction": sum(argmax) / len(argmax),
        "exact_fraction": sum(d == 0 for d in deltas) / len(deltas),
    }


class Background:
    """Keep N streams busy until stopped: 3 of 4 on cartridges, 1 of 4 on the base model."""

    def __init__(self, args, count: int, tokens: int):
        self.args = args
        self.tokens = tokens
        self.stop = threading.Event()
        self.completed = [0] * count
        self.errors = [0] * count
        self.threads = [
            threading.Thread(target=self.loop, args=(i,), daemon=True)
            for i in range(count)
        ]

    def loop(self, index: int):
        stream = index + 1
        model = cb.model_name(self.args, None if stream % 4 == 0 else stream)
        while not self.stop.is_set():
            try:
                retrying(
                    cb.stream_chat,
                    self.args,
                    model,
                    cb.unique_messages(stream, 64),
                    self.tokens,
                )
                self.completed[index] += 1
            except Exception:
                self.errors[index] += 1
                time.sleep(1)

    def __enter__(self):
        for thread in self.threads:
            thread.start()
        time.sleep(self.args.background_delay)
        return self

    def __exit__(self, *exc):
        self.stop.set()
        for thread in self.threads:
            thread.join(timeout=self.args.timeout)


# --- checks ------------------------------------------------------------------


def probe(args: argparse.Namespace) -> int:
    messages = cb.unique_messages(0, 8)
    out = {}
    result = cb.stream_chat(args, cb.model_name(args, 0), messages, 64)
    out["stream_completion_tokens"] = (result["usage"] or {}).get("completion_tokens")
    out["ignore_eos_honoured"] = out["stream_completion_tokens"] == 64
    out["per_chunk_usage"] = not result["approximate"]
    case = synthetic_cases(2, 64, 0)[1]["messages"]
    for label, model in (("cartridge", args.identity), ("base", args.base_model)):
        try:
            got = top_logprobs(args, model, case)
            out[f"{label}_logprobs"] = len(got["top_logprobs"]) >= 5
            out[f"{label}_usage"] = {
                k: got[k] for k in ("prompt_tokens", "cached_tokens")
            }
        except Exception as error:  # report, do not stop the probe
            out[f"{label}_logprobs"] = f"failed: {type(error).__name__}"
    if args.metrics_url:
        try:
            out["spec_verify_metric"] = verify_calls(args) is not None
        except Exception as error:
            out["spec_verify_metric"] = f"failed: {type(error).__name__}"
    out["pass"] = (
        out["ignore_eos_honoured"]
        and out.get("cartridge_logprobs") is True
        and out.get("base_logprobs") is True
    )
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


def verify_calls(args) -> float | None:
    if not args.metrics_url:
        return None
    text = urllib.request.urlopen(args.metrics_url, timeout=30).read().decode()
    total = None
    for line in text.splitlines():
        if line.startswith("sglang:spec_verify_calls_total"):
            total = (total or 0.0) + float(line.rpartition(" ")[2])
    return total


def decode(args: argparse.Namespace) -> int:
    text = slot_text(args)

    def run(arm: str) -> dict:
        original = cb.unique_messages
        if arm == "slots":
            cb.unique_messages = lambda i, w: with_slots(original(i, w), text)
        try:
            before = verify_calls(args)
            result = cb.decode_round(args, arm == "cartridge")
            after = verify_calls(args)
        finally:
            cb.unique_messages = original
        result.pop("prompt_tokens", None)
        result["arm"] = arm
        calls = after - before if before is not None and after is not None else None
        result["tokens_per_verify_call"] = (
            args.batch * args.output_tokens / calls if calls else None
        )
        return result

    for arm in ("cartridge", "slots", "base"):
        run(arm)  # warm: resolve and load every cartridge
    rounds = []
    for repeat in range(args.repeats):
        order = (
            ("cartridge", "slots", "base")
            if repeat % 2 == 0
            else ("base", "slots", "cartridge")
        )
        rounds.extend(run(arm) for arm in order)

    def mean(arm: str, key: str):
        values = [r[key] for r in rounds if r["arm"] == arm and r[key] is not None]
        return statistics.fmean(values) if values else None

    summary = {
        "batch": args.batch,
        "output_tokens": args.output_tokens,
        "repeats": args.repeats,
        "cartridges": len({cb.model_name(args, i) for i in range(args.batch)}),
        "rounds": rounds,
    }
    passed = True
    for control in ("slots", "base"):
        throughput = mean("cartridge", "decode_tokens_per_second") / mean(
            control, "decode_tokens_per_second"
        )
        itl = mean("cartridge", "itl_mean_ms") / mean(control, "itl_mean_ms")
        summary[f"throughput_ratio_vs_{control}"] = throughput
        summary[f"itl_ratio_vs_{control}"] = itl
        accept_c, accept_k = mean("cartridge", "tokens_per_verify_call"), mean(
            control, "tokens_per_verify_call"
        )
        summary[f"accept_ratio_vs_{control}"] = (
            accept_c / accept_k if accept_c and accept_k else None
        )
        summary[f"pass_vs_{control}"] = (
            throughput >= 1 - args.tolerance and itl <= 1 + args.tolerance
        )
    summary["approximate_token_counts"] = any(r.get("approximate") for r in rounds)
    # Synthesized timestamps are not a measurement of ITL: pass only on exact
    # per-chunk counts unless the caller accepts the approximation.
    passed = summary["pass_vs_slots"] and (
        not summary["approximate_token_counts"] or args.allow_approximate
    )
    summary["pass"] = passed
    print(json.dumps(summary, indent=2))
    return 0 if passed else 1


def identity(args: argparse.Namespace) -> int:
    """The identity cartridge must reproduce the base model given the slot text, within the noise floor."""
    cases = (
        json.loads(Path(args.cases).read_text())["cases"]
        if args.cases
        else synthetic_cases(args.count, args.system_words, args.seed)
    )
    text = slot_text(args)
    arms = {
        "identity": (args.identity, lambda m: m),
        "slots": (args.base_model, lambda m: with_slots(m, text)),
        "floor": (args.identity_floor, lambda m: m),
        # A synthetic cartridge has rows unlike the slot embeddings, so it must move the logits.
        "synthetic": (args.cartridge_names[0], lambda m: m),
    }
    records = {name: [] for name in arms}
    background = (
        Background(args, args.background, args.background_tokens)
        if args.background
        else None
    )
    if background:
        background.__enter__()
    try:
        for case in cases:
            cache_salt = uuid.uuid4().hex
            for name, (model, render) in arms.items():
                records[name].append(
                    top_logprobs(args, model, render(case["messages"]), cache_salt)
                )
    finally:
        if background:
            background.__exit__()
    lengths = {name: records[name][0]["prompt_tokens"] for name in arms}
    out = {
        "cases": len(cases),
        "background": args.background,
        "background_completed": sum(background.completed) if background else 0,
        "background_errors": sum(background.errors) if background else 0,
        "identity_vs_slots": stats(records["identity"], records["slots"]),
        "floor_vs_slots": stats(records["floor"], records["slots"]),
        "identity_vs_floor": stats(records["identity"], records["floor"]),
        "synthetic_vs_slots": stats(records["synthetic"], records["slots"]),
        "prompt_tokens": lengths,
        "all_cold": all(
            result["cached_tokens"] == 0 for arm in records.values() for result in arm
        ),
    }
    measured, floor = out["identity_vs_slots"], out["identity_vs_floor"]
    # Pass: the cartridge is indistinguishable from its own slot embeddings, i.e. no
    # further from the slot-text render than two identical cartridges are from each other.
    # A no-op scatter would also pass that, so the synthetic cartridge must differ clearly.
    applied = out["synthetic_vs_slots"]["median"] > max(0.1, 5 * floor["median"])
    out["synthetic_applied"] = applied
    out["pass"] = (
        out["all_cold"]
        and applied
        and measured["median"] <= max(args.tolerance, 1.5 * floor["median"])
        and measured["same_argmax_fraction"]
        >= floor["same_argmax_fraction"] - 1 / len(cases)
    )
    if background:
        # Mixed-batch isolation needs the load to have run: every stream must
        # finish at least once and none may fail after its retries.
        out["background_ok"] = not any(background.errors) and all(background.completed)
        out["pass"] = out["pass"] and out["background_ok"]
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


def isolation(args: argparse.Namespace) -> int:
    """Compare cache reuse within one fresh namespace on a live replica."""
    text = slot_text(args)
    system = f"{uuid.uuid4()} " + "You are a careful assistant. " * args.system_words
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": "Summarize the plan."},
    ]
    first, second = cb.model_name(args, args.first), cb.model_name(args, args.second)
    cache_salt = uuid.uuid4().hex
    out = {}
    for label, model, render in (
        ("a_first", first, messages),
        ("a_again", first, messages),
        ("b_first", second, messages),
        ("slots_first", args.base_model, with_slots(messages, text)),
        ("b_again", second, messages),
    ):
        got = top_logprobs(args, model, render, cache_salt)
        out[label] = {
            "prompt_tokens": got["prompt_tokens"],
            "cached_tokens": got["cached_tokens"] or 0,
        }
    # Gateway usage subtracts the K cartridge positions, so compare against the prompt, not K.
    out["pass"] = (
        out["a_first"]["cached_tokens"] == 0
        and out["a_again"]["cached_tokens"] >= out["a_first"]["prompt_tokens"] // 2
        and out["b_first"]["cached_tokens"] <= args.max_before_slots
        and out["slots_first"]["cached_tokens"] <= args.max_before_slots
        and out["b_again"]["cached_tokens"] >= out["a_first"]["prompt_tokens"] // 2
    )
    print(json.dumps(out, indent=2))
    return 0 if out["pass"] else 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("identity-files")
    command.add_argument(
        "--model",
        required=True,
        help="checkpoint directory with model.safetensors.index.json",
    )
    command.add_argument(
        "--slots-from", required=True, help="a cartridge whose slot IDs to reuse"
    )
    command.add_argument("--tokens", type=int, default=256)
    command.add_argument("--output", required=True)
    for name in ("probe", "decode", "identity", "isolation"):
        command = commands.add_parser(name)
        command.add_argument(
            "--base-url", required=True, help="gateway or replica, without /v1"
        )
        command.add_argument("--base-model", required=True)
        command.add_argument(
            "--cartridges",
            required=True,
            help="file: one cartridge model name per line",
        )
        command.add_argument("--identity", help="identity-a cartridge model name")
        command.add_argument(
            "--identity-floor", help="identity-b cartridge model name (noise floor)"
        )
        command.add_argument(
            "--slot-text",
            required=True,
            help="slot text file, or slots JSON (ids, text) whose characters are single tokens",
        )
        command.add_argument(
            "--tokens", type=int, default=256, help="cartridge positions K"
        )
        command.add_argument(
            "--metrics-url",
            help="SGLang /metrics of the replica, for DSPARK acceptance",
        )
        command.add_argument("--timeout", type=float, default=900)
        command.add_argument("--tolerance", type=float, default=0.02)
        command.add_argument("--prompt-words", type=int, default=64)
        if name == "decode":
            command.add_argument("--batch", type=int, default=32)
            command.add_argument("--output-tokens", type=int, default=2048)
            command.add_argument("--repeats", type=int, default=4)
            command.add_argument(
                "--allow-approximate",
                action="store_true",
                help="pass on token counts spread over chunks (no per-chunk usage)",
            )
        if name == "identity":
            command.add_argument("--cases", help="cases JSON; default: synthetic cases")
            command.add_argument("--count", type=int, default=16)
            command.add_argument("--system-words", type=int, default=2000)
            command.add_argument("--seed", type=int, default=0)
            command.add_argument("--background", type=int, default=0)
            command.add_argument("--background-tokens", type=int, default=512)
            command.add_argument("--background-delay", type=float, default=5.0)
        if name == "isolation":
            command.add_argument("--first", type=int, default=0)
            command.add_argument("--second", type=int, default=1)
            command.add_argument("--system-words", type=int, default=256)
            command.add_argument("--max-before-slots", type=int, default=64)
    args = parser.parse_args()
    if args.command != "identity-files":
        args.api_key = os.environ.get("CARTRIDGE_BENCH_API_KEY")
        args.cartridge_names = [
            line.strip()
            for line in Path(args.cartridges).read_text().splitlines()
            if line.strip()
        ]
        if args.command == "decode" and len(set(args.cartridge_names)) < args.batch:
            parser.error("decode needs at least --batch distinct cartridge names")
        if args.command in ("probe", "identity") and not (
            args.identity and (args.identity_floor or args.command == "probe")
        ):
            parser.error("--identity (and --identity-floor for identity) are required")
    return args


def main() -> int:
    args = parse_args()
    return {
        "identity-files": identity_files,
        "probe": probe,
        "decode": decode,
        "identity": identity,
        "isolation": isolation,
    }[args.command](args) or 0


if __name__ == "__main__":
    sys.exit(main())
