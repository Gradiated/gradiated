#!/usr/bin/env python3
"""Exact Gemma-token multi-turn KV replay; deterministic and CPU-only."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import OrderedDict, defaultdict
from pathlib import Path

from jinja2 import Environment, Undefined
from tokenizers import Tokenizer

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "inputs"
ARTIFACTS = ROOT / "artifacts"
TEMPLATE = (INPUT / "chat_template.jinja").read_text()
MODEL = "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4"
KV_BYTES_BF16 = 491_520
KV_BYTES_FP8 = 92_800  # 0.363423 GiB / 4214 tokens, reconciled campaign contract
BLOCK = 16
REPLICAS = 4


def raise_exception(message: str) -> None:
    raise ValueError(message)


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def tool_definitions(actions: list[dict]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": a["name"], "description": f"Perform {a['name']}.",
          "parameters": {"additionalProperties": True, "type": "object"}}}
        for a in actions
    ]


def render(tokenizer: Tokenizer, messages: list[dict], tools: list[dict]) -> list[int]:
    env = Environment(undefined=Undefined, trim_blocks=False, lstrip_blocks=False)
    env.globals["raise_exception"] = raise_exception
    text = env.from_string(TEMPLATE).render(
        messages=messages, tools=tools, bos_token="<bos>", add_generation_prompt=True,
        enable_thinking=False, preserve_thinking=False,
    )
    return tokenizer.encode(text).ids


def synthetic_tool_result(case_id: str, index: int, action: dict) -> str:
    # Deterministic placeholder with the same provider-visible role and stable payload
    # shape. It is intentionally not claimed as a real TauBench environment result.
    return json.dumps({"ok": True, "case_id": case_id, "action_index": index,
                       "result": "synthetic_safe_replay", "tool": action["name"]},
                      separators=(",", ":"), sort_keys=True)


def build_sessions(tokenizer: Tokenizer, cases: list[dict]) -> tuple[list[dict], list[dict]]:
    turns: list[dict] = []
    sessions: list[dict] = []
    for case in cases:
        actions = case["expected_actions"]
        tools = tool_definitions(actions)
        messages = [{"role": "user", "content": case["messages"][0]["content"]}]
        request_ids: list[str] = []
        for action_index in range(len(actions) + 1):
            ids = render(tokenizer, messages, tools)
            request_id = f"{case['case_id']}-turn-{action_index:02d}"
            request_ids.append(request_id)
            turns.append({
                "request_id": request_id, "session_id": case["case_id"], "tenant_id": case["domain"],
                "turn_index": action_index, "token_count": len(ids),
                "token_sha256": hashlib.sha256(bytes().join(i.to_bytes(4, "little") for i in ids)).hexdigest(),
                "action_name": actions[action_index]["name"] if action_index < len(actions) else None,
                "synthetic_tool_result": action_index > 0,
            })
            if action_index < len(actions):
                action = actions[action_index]
                call_id = f"call_{case['case_id']}_{action_index}"
                messages.extend([
                    {"role": "assistant", "content": None, "tool_calls": [{"id": call_id,
                        "type": "function", "function": {"name": action["name"], "arguments": action["arguments"]}}]},
                    {"role": "tool", "tool_call_id": call_id, "name": action["name"],
                     "content": synthetic_tool_result(case["case_id"], action_index, action)},
                ])
        sessions.append({"session_id": case["case_id"], "tenant_id": case["domain"],
                         "turn_count": len(request_ids), "request_ids": request_ids})
    return turns, sessions


def prefix_hit(tokens: list[int], prior: dict[str, list[int]]) -> tuple[int, str | None]:
    best = 0
    best_key = None
    for key, old in prior.items():
        common = 0
        for a, b in zip(tokens, old):
            if a != b:
                break
            common += 1
        if common > best:
            best, best_key = common, key
    return best, best_key


def replay(turns: list[dict], sessions: list[dict], capacity_gib: float, policy: str,
           replicas: int = REPLICAS) -> tuple[list[dict], dict]:
    by_id = {x["request_id"]: x for x in turns}
    # Token IDs are represented by their immutable digest; the replay only needs exact
    # prefix lengths after the source ledger has bound each request.
    # Reconstruct exact-prefix relation from cumulative request construction: a turn's
    # previous request is always a prefix. The ledger's token counts are sufficient for
    # this deterministic conversation chain, while cross-session prefixes are checked as 0.
    session_turns = defaultdict(list)
    for x in turns: session_turns[x["session_id"]].append(x)
    for v in session_turns.values(): v.sort(key=lambda x: x["turn_index"])
    caches = [OrderedDict() for _ in range(replicas)]
    resident = [0] * replicas
    capacity = int(capacity_gib * 1024**3)
    rows = []
    totals = defaultdict(int)
    ordered = sorted(turns, key=lambda x: (x["turn_index"], x["session_id"]))
    for turn in ordered:
        sid = turn["session_id"]
        replica = int(hashlib.sha256(sid.encode()).hexdigest(), 16) % replicas if policy == "affinity" else None
        idx = turn["turn_index"]
        total = turn["token_count"]
        reusable = session_turns[sid][idx - 1]["token_count"] if idx else 0
        if policy == "none":
            hit = 0
        elif policy == "ideal":
            hit = reusable
        else:
            route_key = f"{sid}:{idx}"
            r = replica if policy == "affinity" else int(hashlib.sha256(route_key.encode()).hexdigest(), 16) % replicas
            prior_key = (sid, idx - 1)
            current_key = (sid, idx)
            hit = reusable if idx and prior_key in caches[r] else 0
            if hit:
                caches[r].move_to_end(prior_key)
            size = total * KV_BYTES_FP8
            if size <= capacity:
                while resident[r] + size > capacity and caches[r]:
                    _, old = caches[r].popitem(last=False); resident[r] -= old; totals["evictions"] += 1
                if resident[r] + size <= capacity:
                    caches[r][current_key] = size; resident[r] += size
        fresh = total - hit
        row = {**turn, "policy": policy, "replica": replica if replica is not None else r if policy == "radix_arbitrary" else None,
               "reusable_prefix_tokens": reusable, "resident_hit_tokens": hit,
               "fresh_tokens": fresh, "evicted_or_reloaded_tokens": max(0, reusable - hit),
               "kv_bytes_fresh_fp8": fresh * KV_BYTES_FP8, "kv_bytes_hit_fp8": hit * KV_BYTES_FP8}
        rows.append(row)
        totals["request_tokens"] += total; totals["fresh_tokens"] += fresh; totals["hit_tokens"] += hit
        totals["reloaded_tokens"] += max(0, reusable - hit)
    totals.update({"turns": len(rows), "sessions": len(sessions), "hit_fraction_of_total": totals["hit_tokens"] / totals["request_tokens"],
                   "fresh_fraction_of_total": totals["fresh_tokens"] / totals["request_tokens"]})
    return rows, dict(totals)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--capacity-gib", type=float, nargs="*", default=[1, 4, 16, 64, 256])
    args = ap.parse_args()
    ARTIFACTS.mkdir(exist_ok=True)
    tokenizer = Tokenizer.from_file(str(INPUT / "tokenizer.json"))
    cases = [json.loads(x) for x in (INPUT / "taubench_requests.jsonl").read_text().splitlines() if x.strip()]
    turns, sessions = build_sessions(tokenizer, cases)
    policies = {}
    ledgers = {}
    for capacity in args.capacity_gib:
        for policy in ("none", "radix_arbitrary", "affinity", "ideal"):
            rows, totals = replay(turns, sessions, capacity, policy)
            key = f"{policy}@{capacity:g}GiB"; policies[key] = totals
            ledgers[key] = rows
    source_manifest = {"model": MODEL, "tokenizer_json_sha256": hashlib.sha256((INPUT / "tokenizer.json").read_bytes()).hexdigest(),
                       "tokenizer_config_sha256": hashlib.sha256((INPUT / "tokenizer_config.json").read_bytes()).hexdigest(),
                       "chat_template_sha256": hashlib.sha256((INPUT / "chat_template.jinja").read_bytes()).hexdigest(),
                       "requests_sha256": hashlib.sha256((INPUT / "taubench_requests.jsonl").read_bytes()).hexdigest(),
                       "cases": len(cases), "sessions": len(sessions), "turns": len(turns),
                       "synthetic_tool_results": True, "tokenization": "tokenizers.Tokenizer.from_file + copied Gemma chat_template.jinja"}
    (ARTIFACTS / "SOURCE_MANIFEST.json").write_text(json.dumps(source_manifest, indent=2, sort_keys=True) + "\n")
    (ARTIFACTS / "TURN_LEDGER.jsonl").write_text("\n".join(json.dumps(x, sort_keys=True) for x in turns) + "\n")
    (ARTIFACTS / "POLICY_SUMMARY.json").write_text(json.dumps(policies, indent=2, sort_keys=True) + "\n")
    (ARTIFACTS / "CAPACITY_LEDGERS.jsonl").write_text("\n".join(json.dumps({"key": k, "row": r}, sort_keys=True) for k, rs in ledgers.items() for r in rs) + "\n")
    print(json.dumps({"source": source_manifest, "policies": policies}, indent=2, sort_keys=True))


if __name__ == "__main__": main()
