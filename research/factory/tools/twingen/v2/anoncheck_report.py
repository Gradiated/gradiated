"""Impact of anonymizer-corrupted SQL on traces and Phase A training rows. Aggregates only (stays on fbf8).

Usage: python3 -I anoncheck_report.py [--no-known] [--sample [--top]] [--only=test_v2,dev,...]
"""
import json, sys, random, collections as C
sys.path.insert(0, "/opt/posthog-sft/env-research/twingen/v2")
import anoncheck as A
V2 = "/opt/posthog-sft/env-research/twingen/v2"
A.load_vocab(f"{V2}/anoncheck_vocab.json")
USE_KNOWN = "--no-known" not in sys.argv
SAMPLE = "--sample" in sys.argv
TRACES = {"test_v2": "/opt/posthog-sft/eval/data/test_v2.jsonl", "dev": "/opt/posthog-sft/root_agent/data_all/dev.jsonl",
          "train": "/opt/posthog-sft/root_agent/data_all/train.jsonl"}
PHASE_A = {"dev.jsonl": "/opt/posthog-sft/root_agent/data_all/dev.jsonl",
           "train.jsonl": "/opt/posthog-sft/root_agent/data_all/train.jsonl",
           "train_ds600.jsonl": "/opt/posthog-sft/root_agent/data_all/train_ds600.jsonl"}
SPECS = "/opt/posthog-sft/env-research/twins/specs"
_cache = {}

def known(cid):
    if not USE_KNOWN: return None
    try: return A.known_from_spec(json.load(open(f"{SPECS}/{cid}.json")))
    except (FileNotFoundError, ValueError): return None

def sql_res(sql, kn, kid):
    key = (kid, sql)
    if key not in _cache: _cache[key] = A.analyze_sql(sql, kn)
    return _cache[key]

def pct(a, b): return round(100.0 * a / b, 2) if b else None
tok_samples = C.defaultdict(C.Counter)

def analyze_row(r):
    cid = r["id"]; kn = known(cid); msgs = r["messages"]
    calls = A.analyze_conversation(msgs, kn)
    for c in calls:
        for b in c["bad"]:
            if c["corrupted"]: tok_samples[b["reason"]][b["token"][:40]] += 1
    # prompt side: SQL in non-assistant content (user text, tool results); target side: assistant tool calls + text
    prompt_bad = prompt_n = text_bad = text_n = 0
    ph_prompt = 0
    for m in msgs:
        blocks = m["content"] if isinstance(m["content"], list) else [{"type": "text", "text": m["content"]}]
        for b in blocks:
            if m["role"] == "assistant":
                if b.get("type") == "text":
                    for s in A.extract_sql_snippets(b.get("text", "")):
                        res = sql_res(s, kn, cid); text_n += 1; text_bad += res["corrupted"]
                continue
            t = b.get("text", "") if b.get("type") == "text" else A._result_text(b) if b.get("type") == "tool_result" else ""
            for s in A.extract_sql_snippets(t):
                res = sql_res(s, kn, cid); prompt_n += 1; prompt_bad += res["corrupted"]; ph_prompt += res["placeholders"] > 0
    last_ai = max(i for i, m in enumerate(msgs) if m["role"] == "assistant")
    return {
        "calls": len(calls), "bad_calls": sum(c["corrupted"] for c in calls),
        "repaired_calls": sum(c["repair_status"] == "repaired" for c in calls),
        "partial_calls": sum(c["repair_status"] == "partial" for c in calls),
        "bad_calls_err": sum(1 for c in calls if c["corrupted"] and c["result_error"]),
        "good_calls_err": sum(1 for c in calls if not c["corrupted"] and c["result_error"]),
        "ph_calls": sum(c["placeholders"] > 0 for c in calls),
        "exec_calls": sum(c["tool"] == "execute_sql" for c in calls),
        "exec_bad": sum(c["tool"] == "execute_sql" and c["corrupted"] for c in calls),
        "prompt_n": prompt_n, "prompt_bad": prompt_bad, "ph_prompt": ph_prompt,
        "target_text_n": text_n, "target_text_bad": text_bad,
        "bad_before_last": any(c["corrupted"] and c["message_index"] < last_ai for c in calls),
        "reasons": C.Counter(rs for c in calls if c["corrupted"] for rs in c["reasons"]),
    }

def trace_stats(path):
    convs = sqlconvs = badconvs = fixconvs = 0
    agg = C.Counter(); reasons = C.Counter()
    for l in open(path):
        r = json.loads(l); s = analyze_row(r); convs += 1
        for k in ("calls", "bad_calls", "repaired_calls", "partial_calls", "bad_calls_err", "good_calls_err", "ph_calls",
                  "exec_calls", "exec_bad"):
            agg[k] += s[k]
        reasons.update(s["reasons"])
        if s["calls"]: sqlconvs += 1
        if s["bad_calls"]:
            badconvs += 1
            if s["repaired_calls"] == s["bad_calls"]: fixconvs += 1
    return {
        "conversations": convs, "conversations_with_sql": sqlconvs, "sql_calls": agg["calls"],
        "corrupted_calls": agg["bad_calls"], "corrupted_call_pct": pct(agg["bad_calls"], agg["calls"]),
        "execute_sql_calls": agg["exec_calls"], "execute_sql_corrupted_pct": pct(agg["exec_bad"], agg["exec_calls"]),
        "conversations_with_corrupted": badconvs, "conv_corrupted_pct_of_all": pct(badconvs, convs),
        "conv_corrupted_pct_of_sql_convs": pct(badconvs, sqlconvs),
        "corrupted_calls_repaired": agg["repaired_calls"], "call_repair_pct": pct(agg["repaired_calls"], agg["bad_calls"]),
        "corrupted_calls_partial_repair": agg["partial_calls"],
        "conversations_fully_repaired": fixconvs, "conv_repair_pct": pct(fixconvs, badconvs),
        "prod_result_error_pct_corrupted": pct(agg["bad_calls_err"], agg["bad_calls"]),
        "prod_result_error_pct_clean": pct(agg["good_calls_err"], agg["calls"] - agg["bad_calls"]),
        "calls_with_value_placeholders": agg["ph_calls"], "placeholder_call_pct": pct(agg["ph_calls"], agg["calls"]),
        "reasons_in_corrupted_calls": dict(reasons.most_common()),
    }

def phase_a_stats(path):
    rows = 0; c = C.Counter()
    for l in open(path):
        r = json.loads(l); s = analyze_row(r); rows += 1
        p = s["prompt_bad"] > 0
        t_tool = s["bad_calls"] > 0
        t = t_tool or s["target_text_bad"] > 0
        c["prompt"] += p; c["target"] += t; c["either"] += p or t; c["both"] += p and t
        c["target_toolcall"] += t_tool; c["target_text_only"] += t and not t_tool
        c["ctx_prior_turn"] += p or s["bad_before_last"]
        if t_tool and s["repaired_calls"] == s["bad_calls"] and not s["target_text_bad"]: c["target_repairable"] += 1
        c["rows_sql_target"] += (s["calls"] + s["target_text_n"]) > 0
        c["rows_sql_prompt"] += s["prompt_n"] > 0
        c["prompt_snippets"] += s["prompt_n"]; c["prompt_snippets_bad"] += s["prompt_bad"]
        c["prompt_placeholder_snippets"] += s["ph_prompt"]
        c["target_calls"] += s["calls"]; c["target_calls_bad"] += s["bad_calls"]
    return {
        "rows": rows, "rows_with_sql_in_prompt": c["rows_sql_prompt"], "rows_with_sql_in_target": c["rows_sql_target"],
        "prompt_corrupted_rows": c["prompt"], "prompt_corrupted_pct": pct(c["prompt"], rows),
        "target_corrupted_rows": c["target"], "target_corrupted_pct": pct(c["target"], rows),
        "target_corrupted_toolcall_rows": c["target_toolcall"], "target_corrupted_text_only_rows": c["target_text_only"],
        "either_rows": c["either"], "either_pct": pct(c["either"], rows), "both_rows": c["both"],
        "corrupted_in_context_of_some_trained_turn_rows": c["ctx_prior_turn"],
        "corrupted_in_context_pct": pct(c["ctx_prior_turn"], rows),
        "target_corrupted_rows_repairable": c["target_repairable"],
        "target_repairable_pct_of_target_corrupted": pct(c["target_repairable"], c["target"]),
        "prompt_sql_snippets": c["prompt_snippets"], "prompt_sql_snippets_corrupted": c["prompt_snippets_bad"],
        "prompt_snippets_with_placeholders": c["prompt_placeholder_snippets"],
        "target_sql_calls": c["target_calls"], "target_sql_calls_corrupted": c["target_calls_bad"],
    }

ONLY = next((a.split("=", 1)[1].split(",") for a in sys.argv if a.startswith("--only=")), None)
if ONLY:
    TRACES = {k: v for k, v in TRACES.items() if k in ONLY}
    PHASE_A = {k: v for k, v in PHASE_A.items() if k in ONLY}
out = {"known_from_spec": USE_KNOWN, "traces": {}, "phase_a": {}}
for name, path in TRACES.items():
    out["traces"][name] = trace_stats(path); print(name, json.dumps(out["traces"][name]))
for name, path in PHASE_A.items():
    out["phase_a"][name] = phase_a_stats(path); print(name, json.dumps(out["phase_a"][name]))
if USE_KNOWN and not ONLY:
    json.dump(out, open(f"{V2}/anoncheck_report.json", "w"), indent=1)
if SAMPLE:
    rnd = random.Random(0)
    for reason, cnt in sorted(tok_samples.items()):
        toks = [t for t, _ in cnt.most_common()] if "--top" in sys.argv else list(cnt)
        if "--top" not in sys.argv: rnd.shuffle(toks)
        print("SAMPLE", reason, sum(cnt.values()), toks[:12])
