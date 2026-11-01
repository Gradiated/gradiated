#!/usr/bin/env python3
"""Reverse KL per field type (content, tool name, argument key/value, gap) for scored OPD samples. Aggregates only."""
import json, sys
from collections import defaultdict
sys.path.insert(0, "/opt/posthog-sft/opd")
from opd_sample_score import Qwen, char_offsets
from xtok_distill import parse_qwen_output

qwen = Qwen()
for path in sys.argv[1:]:
    tot, cnt, first_name = defaultdict(float), defaultdict(int), []
    for line in open(path):
        r = json.loads(line)
        if r.get("status") != "ok":
            continue
        text, offsets = char_offsets(qwen.pieces(r["token_ids"]))
        try:
            turn, fields = parse_qwen_output(text)
        except Exception:
            continue
        kind_of = {}
        for f in fields:
            kind = f.field.split(".")[-1] if "." in f.field else f.field
            for i, (a, b) in enumerate(offsets):
                if f.start <= a < b <= f.end:
                    kind_of[i] = kind
        for i, adv in enumerate(r["advantages"]):
            if adv is None:
                continue
            k = kind_of.get(i, "gap")
            tot[k] -= adv
            cnt[k] += 1
        # KL on the first call name (the action choice), per sample that calls a tool
        name_idx = [i for i, (a, b) in enumerate(offsets) for f in fields if f.field == "call0.name" and f.start <= a < b <= f.end]
        if name_idx:
            first_name.append(-sum(r["advantages"][i] or 0 for i in name_idx))
    print(path.split("/")[-1])
    for k in ("content", "name", "key", "value", "gap"):
        if cnt[k]:
            print(f"   {k:8s} tokens {cnt[k]:6d}  share {cnt[k] / sum(cnt.values()):.1%}  KL/token {tot[k] / cnt[k]:.4f}  KL total share {tot[k] / sum(tot.values()):.1%}")
    if first_name:
        print(f"   first tool name: samples {len(first_name)}  mean KL {sum(first_name) / len(first_name):.3f}")
