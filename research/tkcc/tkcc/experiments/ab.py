"""Interleaved A/B: alternate stock (no-op) and candidate jobs on one tier.

Each round submits a no-op then the candidate (order alternates per round), so
slow drift in the engine's baseline cancels in the paired ratios.

Usage on the GPU host: python3 -m tkcc.experiments.ab TIER CANDIDATE.py ROUNDS OUT.json
"""

from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

from tkcc import client

NOOP = '''def install(model, patch, ctx):
    patch(ctx["text_model"].layers[0], "_tkcc_marker", ctx["rank"])
'''


def _run(tier: str, source: str, name: str) -> dict:
    ticket = client.submit(tier, source, "ab", name, False)
    return client.wait(tier, ticket["job_id"], 3600).get("result", {})


def main() -> None:
    tier, candidate_path, rounds, out = sys.argv[1], sys.argv[2], int(sys.argv[3]), Path(sys.argv[4])
    candidate = Path(candidate_path).read_text()
    pairs = []
    for index in range(rounds):
        order = [("stock", NOOP), ("candidate", candidate)]
        if index % 2:
            order.reverse()
        results = {label: _run(tier, source, f"ab-{label}-{index}") for label, source in order}
        row = {label: {c: v["tps_per_user"] for c, v in r.get("measurement", {}).items()} for label, r in results.items()}
        row["status"] = {label: r.get("status") for label, r in results.items()}
        row["correctness"] = results["candidate"].get("correctness")
        pairs.append(row)
        print(json.dumps(row), flush=True)
    summary = {}
    for concurrency in pairs[0]["stock"]:
        ratios = [p["candidate"][concurrency] / p["stock"][concurrency] for p in pairs if concurrency in p.get("candidate", {})]
        summary[concurrency] = {
            "stock_tps": statistics.median(p["stock"][concurrency] for p in pairs),
            "candidate_tps": statistics.median(p["candidate"][concurrency] for p in pairs if concurrency in p.get("candidate", {})),
            "paired_speedup_median": statistics.median(ratios),
            "paired_speedup_min": min(ratios),
            "paired_speedup_max": max(ratios),
        }
    geo = math.exp(statistics.mean(math.log(v["paired_speedup_median"]) for v in summary.values()))
    result = {"tier": tier, "rounds": rounds, "per_concurrency": summary, "geomean_speedup": geo, "pairs": pairs}
    out.write_text(json.dumps(result, indent=1))
    print(json.dumps({k: v for k, v in result.items() if k != "pairs"}, indent=1))


if __name__ == "__main__":
    main()
