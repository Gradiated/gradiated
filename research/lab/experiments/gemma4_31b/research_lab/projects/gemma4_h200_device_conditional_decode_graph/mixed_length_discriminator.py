from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import time
import urllib.request


def request(port: int, completion_tokens: int) -> dict[str, object]:
    body = {
        "model": "google/gemma-4-31B-it",
        "messages": [
            {
                "role": "user",
                "content": f"Count upward using single words. Produce exactly {completion_tokens} tokens.",
            }
        ],
        "temperature": 0,
        "max_tokens": completion_tokens,
        "min_tokens": completion_tokens,
    }
    started = time.monotonic()
    raw = json.load(
        urllib.request.urlopen(
            urllib.request.Request(
                f"http://127.0.0.1:{port}/v1/chat/completions",
                json.dumps(body).encode(),
                {"Content-Type": "application/json"},
            ),
            timeout=300,
        )
    )
    elapsed = time.monotonic() - started
    usage = raw["usage"]
    return {
        "requested_completion_tokens": completion_tokens,
        "completion_tokens": usage["completion_tokens"],
        "prompt_tokens": usage["prompt_tokens"],
        "elapsed_seconds": elapsed,
        "finish_reason": raw["choices"][0]["finish_reason"],
        "response_nonempty": bool(raw["choices"][0]["message"]["content"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=30000)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda length: request(args.port, length), [1, 2, 3, 4]))
    ended = time.monotonic()
    rows.sort(key=lambda row: row["requested_completion_tokens"])
    passed = all(
        row["completion_tokens"] == row["requested_completion_tokens"]
        and row["response_nonempty"]
        for row in rows
    )
    result = {
        "schema_version": 1,
        "pass": passed,
        "mixed_completion_lengths": [1, 2, 3, 4],
        "started_monotonic_s": started,
        "ended_monotonic_s": ended,
        "rows": rows,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
