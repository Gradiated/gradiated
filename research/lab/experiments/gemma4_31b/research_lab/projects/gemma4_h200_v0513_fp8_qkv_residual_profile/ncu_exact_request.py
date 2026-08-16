#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import urllib.request


MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
COMMON_TOKENS = 535
SEED = "gemma4-background-exact-mix-c32-20260718"


def tokens(label: str, count: int) -> list[int]:
    result: list[int] = []
    index = 0
    while len(result) < count:
        digest = hashlib.sha256(f"{SEED}|{label}|{index}".encode()).digest()
        for offset in range(0, len(digest), 4):
            result.append(1000 + int.from_bytes(digest[offset : offset + 4], "big") % 249000)
            if len(result) == count:
                return result
        index += 1
    return result


prefix = tokens("common-prefix", COMMON_TOKENS)
suffix = tokens("suffix-0", PROMPT_TOKENS - COMMON_TOKENS)
suffix[0] = 200000
body = {
    "model": MODEL,
    "prompt": prefix + suffix,
    "max_tokens": 1,
    "min_tokens": 1,
    "ignore_eos": True,
    "temperature": 0,
    "seed": 20260718,
    "stream": False,
    "return_token_ids": True,
    "add_special_tokens": False,
}
request = urllib.request.Request(
    "http://127.0.0.1:30000/v1/completions",
    json.dumps(body).encode(),
    {"Content-Type": "application/json"},
)
with urllib.request.urlopen(request, timeout=900) as response:
    result = json.load(response)
usage = result.get("usage", {})
terminal = {
    "schema_version": 1,
    "pass": usage.get("prompt_tokens") == PROMPT_TOKENS,
    "prompt_tokens": usage.get("prompt_tokens"),
    "completion_tokens": usage.get("completion_tokens"),
    "request_sha256": hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
}
print(json.dumps(terminal, sort_keys=True))
raise SystemExit(0 if terminal["pass"] else 72)
