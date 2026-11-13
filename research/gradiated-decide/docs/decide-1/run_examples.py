"""Send the post's examples to a running decision server (/v1/systemone) and record answers and latency.

Usage: python run_examples.py EXAMPLES.json URL MODEL_NAME OUT.jsonl
Each example is sent once to warm the prefix cache, then REPEATS times; latency is the median of the timed sends.
"""

import json
import statistics
import sys
import time

import requests

REPEATS = 5


def main() -> None:
    examples, url, model, out = json.load(open(sys.argv[1])), sys.argv[2].rstrip("/"), sys.argv[3], sys.argv[4]
    with open(out, "a") as f:
        for ex in examples:
            body = {"state": ex["state"], "questions": ex["questions"]}
            first = requests.post(f"{url}/v1/systemone", json=body, timeout=600)
            first.raise_for_status()
            times = []
            for _ in range(REPEATS):
                t = time.perf_counter()
                r = requests.post(f"{url}/v1/systemone", json=body, timeout=600)
                times.append((time.perf_counter() - t) * 1000)
                r.raise_for_status()
            row = {"model": model, "example": ex["name"], "answers": first.json()["answers"],
                   "usage": first.json().get("usage", {}), "latency_ms_median": round(statistics.median(times), 1),
                   "deterministic": r.json()["answers"] == first.json()["answers"]}
            f.write(json.dumps(row) + "\n")
            print(model, ex["name"], json.dumps(row["answers"])[:300], row["latency_ms_median"], flush=True)


if __name__ == "__main__":
    main()
