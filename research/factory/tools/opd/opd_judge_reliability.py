#!/usr/bin/env python3
"""How repeatable is the judge? Re-judges saved eval generations and compares with their stored verdicts.

    opd_judge_reliability.py --results eval/results/vllm_qwen27b-base_n300_s0.jsonl --points 100
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, "/opt/posthog-sft/eval")

from providers import ProxyJudge  # noqa: E402
from run_eval import JudgeOptions, judge_record  # noqa: E402
from sampling import enumerate_points, load_conversations  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--results", required=True)
    p.add_argument("--data", default="/opt/posthog-sft/eval/data/test_v2.jsonl")
    p.add_argument("--points", type=int, default=100)
    args = p.parse_args()
    points = {pt.point_id: pt for pt in enumerate_points(load_conversations([args.data]))}
    records = sorted((r for r in map(json.loads, open(args.results)) if "judge" in r and "error" not in r
                      and not r["judge"].get("skipped")), key=lambda r: r["point_id"])[: args.points]
    judge = ProxyJudge("gpt-6.1-sol", 120, None)
    options = JudgeOptions("gpt-6.1-sol", reference_faithfulness=False)

    def again(r):
        try:
            return r["judge"]["verdict"], judge_record({k: v for k, v in r.items() if k not in ("judge", "faithfulness")},
                                                       points[r["point_id"]], judge, options)["judge"]["verdict"]
        except Exception:  # noqa: BLE001
            return None

    with ThreadPoolExecutor(12) as pool:
        pairs = [x for x in pool.map(again, records) if x]
    ge = lambda v: v in ("better", "equivalent")  # noqa: E731
    print(json.dumps({"rejudged": len(pairs), "same_verdict": round(sum(a == b for a, b in pairs) / len(pairs), 3),
                      "same_at_least_as_good": round(sum(ge(a) == ge(b) for a, b in pairs) / len(pairs), 3),
                      "transitions": {f"{a}->{b}": n for (a, b), n in Counter(pairs).most_common()}}, indent=1))


if __name__ == "__main__":
    main()
