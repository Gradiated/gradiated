#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parent
SEED = "gemma4-background-exact-mix-c32-20260718"
MODEL = "google/gemma-4-31B-it"
PROMPT_TOKENS = 4214
COMMON_TOKENS = 535
OUTPUT_TOKENS = 358


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


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


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    workload = json.loads((ROOT / "inputs" / "WORKLOAD.json").read_text())
    prefix = tokens("common-prefix", COMMON_TOKENS)
    body_root = ROOT / "inputs" / "request_bodies"
    body_hashes = []
    for index in range(32):
        suffix = tokens(f"suffix-{index}", PROMPT_TOKENS - COMMON_TOKENS)
        suffix[0] = 200000 + index
        body = {
            "model": MODEL,
            "prompt": prefix + suffix,
            "max_tokens": OUTPUT_TOKENS,
            "min_tokens": OUTPUT_TOKENS,
            "ignore_eos": True,
            "temperature": 0,
            "seed": 20260718,
            "stream": True,
            "stream_options": {"include_usage": True},
            "return_token_ids": True,
            "add_special_tokens": False,
        }
        raw = canonical(body)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != workload["request_sha256"][index]:
            raise RuntimeError(f"request body {index} does not match frozen workload")
        (body_root / f"request-{index:02d}.json").write_bytes(raw)
        body_hashes.append(digest)

    record_root = ROOT / "inputs" / "request_records"
    record_lines = [f"{sha256(path)}  {path.name}\n" for path in sorted(record_root.glob("request-*.json"))]
    record_manifest = "".join(record_lines).encode()
    record_digest = hashlib.sha256(record_manifest).hexdigest()
    if record_digest != "e73a44c6fdaa84caaee5c9303c3295e84f39a3876130acda1c54c3ba90fc01aa":
        raise RuntimeError(f"frozen request record manifest mismatch: {record_digest}")
    (ROOT / "inputs" / "REQUEST_RECORDS.sha256").write_bytes(record_manifest)

    body_lines = [f"{sha256(path)}  {path.name}\n" for path in sorted(body_root.glob("request-*.json"))]
    body_manifest = "".join(body_lines).encode()
    result = {
        "schema_version": 1,
        "request_count": len(body_hashes),
        "request_record_manifest_sha256": record_digest,
        "request_body_manifest_sha256": hashlib.sha256(body_manifest).hexdigest(),
        "workload_sha256": sha256(ROOT / "inputs" / "WORKLOAD.json"),
        "all_body_hashes_match_workload": body_hashes == workload["request_sha256"],
    }
    (ROOT / "inputs" / "REQUEST_BODIES.sha256").write_bytes(body_manifest)
    (ROOT / "inputs" / "MATERIALIZATION.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
