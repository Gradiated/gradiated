#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.request


CASES = (
    ("early", 617, "CINDER-ORBIT-617"),
    ("middle", 5003, "MARBLE-LANTERN-503"),
    ("late", 9419, "QUARTZ-HARBOR-419"),
)


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def post_json(url: str, body: dict, timeout: float) -> tuple[int, dict, float]:
    encoded = json.dumps(body, separators=(",", ":")).encode()
    request = urllib.request.Request(
        url,
        data=encoded,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = response.status
    except urllib.error.HTTPError as error:
        payload = error.read()
        status = error.code
    return status, json.loads(payload), time.perf_counter() - started


def make_context(tokenizer, case_name: str, target_tokens: int, needle: str) -> tuple[str, int, int]:
    preamble = (
        "This is a deterministic archival ledger. Read every entry and answer the final question "
        "using only the exact secret code stated in the ledger.\n"
    )
    query = "\nQuestion: What is the exact secret code? Reply with the code only."
    needle_line = f"\nIMPORTANT LEDGER ENTRY: The exact secret code is {needle}.\n"
    filler_line = "Record 000000: cedar basalt river violet compass; this line carries no secret.\n"

    # The repeated numbered ledger is deterministic but not overly compressible. Binary
    # search makes the rendered user message land close to the declared 10K-token gate.
    low, high = 1, 16000
    best = None
    while low <= high:
        count = (low + high) // 2
        rows = [
            f"Record {index:06d}: cedar basalt river violet compass {index % 997:03d}; this line carries no secret."
            for index in range(count)
        ]
        insert_at = {"early": count // 16, "middle": count // 2, "late": (count * 15) // 16}[case_name]
        rows.insert(insert_at, needle_line.strip())
        content = preamble + "\n".join(rows) + query
        messages = [{"role": "user", "content": content}]
        tokens = len(tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=True))
        distance = abs(tokens - target_tokens)
        if best is None or distance < best[0]:
            best = (distance, content, tokens, count)
        if tokens < target_tokens:
            low = count + 1
        else:
            high = count - 1
    assert best is not None
    return best[1], best[2], best[3]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=pathlib.Path, required=True)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:30000")
    parser.add_argument("--model", default="google/gemma-4-31B-it")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint, local_files_only=True)
    rows = []
    for case_name, target_tokens, needle in CASES:
        content, local_tokens, filler_rows = make_context(tokenizer, case_name, 10000, needle)
        if not 9900 <= local_tokens <= 10100:
            raise RuntimeError(f"{case_name} prompt did not bind to 10K geometry: {local_tokens}")
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
            "max_tokens": 32,
            "stream": False,
        }
        status, response, elapsed = post_json(
            args.base_url.rstrip("/") + "/v1/chat/completions", body, 300.0
        )
        text = ""
        if status == 200 and response.get("choices"):
            text = response["choices"][0].get("message", {}).get("content", "").strip()
        usage = response.get("usage", {})
        row = {
            "case": case_name,
            "needle_position_hint": target_tokens,
            "expected": needle,
            "observed": text,
            "exact_match": text == needle,
            "http_status": status,
            "elapsed_seconds": elapsed,
            "local_prompt_tokens": local_tokens,
            "server_prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "filler_rows": filler_rows,
            "request_sha256": hashlib.sha256(
                json.dumps(body, separators=(",", ":"), sort_keys=True).encode()
            ).hexdigest(),
            "response": response,
        }
        rows.append(row)
        atomic_json(args.output / f"{case_name}.json", row)

    passed = bool(
        len(rows) == 3
        and all(
            row["http_status"] == 200
            and row["exact_match"]
            and 9900 <= row["local_prompt_tokens"] <= 10100
            and isinstance(row["server_prompt_tokens"], int)
            and 9900 <= row["server_prompt_tokens"] <= 10100
            for row in rows
        )
    )
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "pass": passed,
        "cases": 3,
        "exact_matches": sum(row["exact_match"] for row in rows),
        "rows": rows,
    }
    atomic_json(args.output / "TERMINAL.json", terminal)
    return 0 if passed else 3


if __name__ == "__main__":
    raise SystemExit(main())
