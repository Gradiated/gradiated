"""Measurement-fidelity experiment (paper Figure 13a): experts hit, real vs random.

Run on the GPU host against a running tier. Builds fresh (uncached) real
prompts from the workload corpus and random-token prompts, prefills chunks of
128/256/512 query tokens, and reports distinct experts per layer-chunk.
"""

from __future__ import annotations

import json
import statistics
import sys
import urllib.request
from pathlib import Path

from tkcc import workload

PORTS = {"fast": 18110, "slow": 18120}


def main() -> None:
    tier = sys.argv[1] if len(sys.argv) > 1 else "fast"
    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file("/home/tkcc/models/dsv41/tokenizer.json")
    encode = lambda text: tokenizer.encode(text, add_special_tokens=False).ids
    bundle = Path("/var/lib/gradiated-kubelet/bundles/58f40e17158432f39d828f40a0f001233ea97db75cecf22f67aa0e70f6642867/python/lib/python3.12/site-packages")
    corpus = workload.Corpus.from_paths(sorted((bundle / "torch").rglob("*.py"))[:3000], [Path("/home/tkcc/data/wikitext103_test.txt")], seed=99)
    sets = {}
    for length in (128, 256, 512):
        sets[f"real-{length}"] = workload.build_prompt_token_ids(corpus, encode, 8, length, seed=1000 + length)
        sets[f"random-{length}"] = workload.random_token_ids(8, length, 128000, seed=2000 + length, reserved=range(0, 16))
    source = Path(__file__).with_name("routing_probe.py").read_text()
    body = json.dumps({"source": source, "prompt_sets": sets, "max_tokens": 1}).encode()
    request = urllib.request.Request(f"http://127.0.0.1:{PORTS[tier]}/experiment", data=body, headers={"Content-Type": "application/json"})
    result = json.loads(urllib.request.urlopen(request, timeout=1800).read())
    summary = {}
    for name, data in result.items():
        if not isinstance(data, dict) or "hits" not in data:
            summary[name] = data
            continue
        length = int(name.split("-")[1])
        hits = [h for h, t in zip(data["hits"], data["tokens"]) if t == length]
        summary[name] = {"chunks": len(hits), "mean_experts_hit": statistics.mean(hits) if hits else None}
    for length in (128, 256, 512):
        real = summary.get(f"real-{length}", {}).get("mean_experts_hit")
        rand = summary.get(f"random-{length}", {}).get("mean_experts_hit")
        if real and rand:
            summary[f"excess-{length}"] = rand / real - 1
    print(json.dumps(summary, indent=1))
    Path(f"/home/tkcc/run/fidelity-{tier}.json").write_text(json.dumps({"summary": summary, "raw": result}))


if __name__ == "__main__":
    main()
