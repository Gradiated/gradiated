#!/usr/bin/env python3
"""Materialize the frozen 905-request OpenAI-compatible replay workload."""
from __future__ import annotations
import hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "inputs"
OUT = ROOT / "paid_workload.jsonl"
MODEL = "google/gemma-4-31B-it"

def tool_defs(actions):
    return [{"type":"function","function":{"name":a["name"],"description":f"Perform {a['name']}.","parameters":{"additionalProperties":True,"type":"object"}}} for a in actions]

def result(case, idx, action):
    return json.dumps({"action_index":idx,"case_id":case,"ok":True,"result":"synthetic_safe_replay","tool":action["name"]}, separators=(",",":"), sort_keys=True)

def main():
    cases = [json.loads(x) for x in (INPUT/"taubench_requests.jsonl").read_text().splitlines() if x.strip()]
    rows=[]
    for case in cases:
        actions=case["expected_actions"]; tools=tool_defs(actions)
        messages=[{"role":"user","content":case["messages"][0]["content"]}]
        for idx in range(len(actions)+1):
            rows.append({"request_id":f"{case['case_id']}-turn-{idx:02d}","session_id":case["case_id"],"tenant_id":case["domain"],"turn_index":idx,
                         "body":{"model":MODEL,"messages":messages.copy(),"tools":tools,"temperature":0,"seed":20260724,"max_tokens":64,"return_token_ids":True,"stream":False}})
            if idx < len(actions):
                action=actions[idx]; call_id=f"call_{case['case_id']}_{idx}"
                messages.extend([{"role":"assistant","content":None,"tool_calls":[{"id":call_id,"type":"function","function":{"name":action["name"],"arguments":action["arguments"]}}]},
                                 {"role":"tool","tool_call_id":call_id,"name":action["name"],"content":result(case["case_id"],idx,action)}])
    rows.sort(key=lambda x:(x["turn_index"],x["session_id"]))
    OUT.write_text("\n".join(json.dumps(x,sort_keys=True,separators=(",",":")) for x in rows)+"\n")
    print(json.dumps({"rows":len(rows),"sessions":len(cases),"sha256":hashlib.sha256(OUT.read_bytes()).hexdigest(),"synthetic_tool_results":True},indent=2))
if __name__ == "__main__": main()
