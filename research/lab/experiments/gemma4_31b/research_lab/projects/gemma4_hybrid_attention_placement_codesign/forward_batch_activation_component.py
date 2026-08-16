#!/usr/bin/env python3
"""Exercise the resident NGRAM target-forward boundary with the bound c32 shape."""
from __future__ import annotations

import concurrent.futures, hashlib, json, pathlib, time, urllib.request

BASE = "http://127.0.0.1:30000/v1/completions"
SEED = "gemma4-background-exact-mix-c32-20260718"

def tokens(label: str, count: int) -> list[int]:
    out: list[int] = []
    i = 0
    while len(out) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{i}".encode()).digest()
        out += [1000 + int.from_bytes(digest[j:j + 4], "big") % 249000 for j in range(0, 32, 4)]
        i += 1
    return out[:count]

def request(index: int) -> dict:
    prefix = tokens("common-prefix", 535)
    suffix = tokens(f"suffix-{index}", 4214 - 535); suffix[0] = 200000 + index
    body = {"model": "google/gemma-4-31B-it", "prompt": prefix + suffix,
            "max_tokens": 12, "min_tokens": 12, "ignore_eos": True,
            "temperature": 0, "seed": 20260718, "stream": False,
            "return_token_ids": True, "add_special_tokens": False}
    started = time.monotonic()
    try:
        raw = urllib.request.urlopen(urllib.request.Request(BASE, json.dumps(body).encode(), {"Content-Type": "application/json"}), timeout=600).read()
        return {"index": index, "ok": True, "seconds": time.monotonic() - started, "response_sha256": hashlib.sha256(raw).hexdigest()}
    except Exception as e:
        return {"index": index, "ok": False, "seconds": time.monotonic() - started, "error": repr(e)}

def main() -> int:
    root = pathlib.Path("/work/artifact/forward-batch-activation-c32"); root.mkdir(parents=True, exist_ok=True)
    (root / "PREPARED.json").write_text(json.dumps({"pre_science": True, "candidate_cuda_invocation_started": False, "science_started": False, "shape": [32, 12]}, sort_keys=True) + "\n")
    # The scientific boundary is submission, not a successful response.  Keep
    # response validity and candidate-CUDA evidence as separate terminal facts.
    (root / "INVOCATION.json").write_text(json.dumps({"pre_science": False, "candidate_cuda_invocation_started": False, "science_started": True, "submitted_requests": 32, "shape": [32, 12]}, sort_keys=True) + "\n")
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        rows = list(pool.map(request, range(32)))
    complete = sum(r["ok"] for r in rows)
    (root / "TERMINAL.json").write_text(json.dumps({"rows": rows, "complete": complete, "accepted_request_observed": complete > 0, "candidate_cuda_invocation_started": complete > 0, "science_started": True, "submitted_requests": 32, "kind": "activation_only_not_component_decision"}, sort_keys=True) + "\n")
    return 0 if all(r["ok"] for r in rows) else 72

if __name__ == "__main__": raise SystemExit(main())
