"""Build the corpus vocabulary (identifier parts seen in >= 2-3 conversations) used by anoncheck. Stays on fbf8."""
import json, sys
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import anoncheck as A
FILES = ["/opt/posthog-sft/eval/data/test_v2.jsonl", "/opt/posthog-sft/root_agent/data_all/dev.jsonl",
         "/opt/posthog-sft/root_agent/data_all/train.jsonl"]
OUT = "/opt/posthog-sft/env-research/twingen/v2/anoncheck_vocab.json"
seen = set()
def strings(o):
    if isinstance(o, dict):
        for v in o.values(): yield from strings(v)
    elif isinstance(o, list):
        for v in o: yield from strings(v)
    elif isinstance(o, str): yield o
def docs():
    for f in FILES:
        for l in open(f):
            r = json.loads(l)
            if r["id"] in seen: continue
            seen.add(r["id"])
            yield "\n".join(strings(r["messages"]))
v = A.build_vocab(docs())
json.dump(sorted(v), open(OUT, "w"))
print("docs", len(seen), "vocab", len(v))
