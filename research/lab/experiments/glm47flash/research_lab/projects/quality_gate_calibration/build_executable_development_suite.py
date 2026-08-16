#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "executable_development_v2"


def canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def digest(value): return hashlib.sha256(value).hexdigest()
def hashed(row):
    row["content_sha256"] = digest(canonical(row)); return row


def context(index, value):
    left = " ".join(f"L{index:02d}{n:04x}" for n in range(4096))
    right = " ".join(f"R{index:02d}{n:04x}" for n in range(4096))
    return f"{left}\nKEY-{index:02d}: {value}\n{right}"


def cases():
    rows=[]
    for i in range(1,7):
        path=f"src/calibration_{i}.py"
        rows.append(hashed({"case_id":f"cal_dev_tool_{i:02d}","split":"development_calibration","category":"tool_call","critical":True,"prompt":f'Return exactly this JSON object and no prose: {{"arguments":{{"path":"{path}"}},"name":"read_file"}}',"scorer":{"kind":"json_exact","expected":{"name":"read_file","arguments":{"path":path}}}}))
        fn=f"add_{i}"
        rows.append(hashed({"case_id":f"cal_dev_code_{i:02d}","split":"development_calibration","category":"coding","critical":True,"prompt":f"Return only Python, or one complete python fenced block, defining {fn}(a, b) that returns a + b + {i}.","scorer":{"kind":"python_tests","tests":[f"assert {fn}(2, 3) == {5+i}",f"assert {fn}(-1, 1) == {i}"]},"transport":{"accepted":["bare_python","single_python_fence"],"reject":["prose","multiple_blocks","wrong_fence"]}}))
        value=f"calibration-orbit-{i:02d}"
        rows.append(hashed({"case_id":f"cal_dev_retrieval_{i:02d}","split":"development_calibration","category":"long_context_retrieval","critical":True,"prompt":f"In the supplied context, return only the value paired with KEY-{i:02d}.","synthetic_context":context(i,value),"tokenizer_binding":{"status":"required_before_gpu_execution","model":"zai-org/GLM-4.7-Flash","checkpoint_revision":"33faccf4c2ba82142214d0d4e16232a4e9ccfe10","minimum_raw_context_characters":40000},"scorer":{"kind":"normalized_exact","expected":value}}))
        params=f"alpha{i}, beta{i}, gamma{i}"
        rows.append(hashed({"case_id":f"cal_dev_continuation_{i:02d}","split":"development_calibration","category":"multi_turn_continuation","critical":True,"history":[{"role":"user","content":f"Inspect blend_{i}."},{"role":"assistant","content":f"blend_{i}({params}) was found."}],"prompt":"Return only the ordered parameter names from the prior assistant message.","scorer":{"kind":"normalized_exact","expected":params}}))
        text=f"Quality calibration sentinel {i}: exact schemas and retrieval values remain stable."
        rows.append(hashed({"case_id":f"cal_dev_loss_{i:02d}","split":"development_calibration","category":"teacher_forced_loss","critical":True,"prompt":"Teacher-force the supplied frozen sequence through the runtime logprob endpoint.","teacher_forced_text":text,"token_sequence_sha256":digest(text.encode()),"scorer":{"kind":"teacher_forced_logprobs_calibration","minimum_scored_tokens":3,"ceiling_status":"unfrozen_requires_three_bf16_captures","ceiling_rule":"maximum_control_mean_nll_times_1.05"}}))
        expected={"status":"ready","truncated":False,"case":i}
        rows.append(hashed({"case_id":f"cal_dev_serving_{i:02d}","split":"development_calibration","category":"serving_correctness","critical":True,"deterministic_repetitions":2,"prompt":f"Return exactly this JSON object and no prose: {json.dumps(expected,separators=(',',':'))}","scorer":{"kind":"json_exact","expected":expected}}))
    return rows


def validate(rows):
    categories={"tool_call","coding","long_context_retrieval","multi_turn_continuation","teacher_forced_loss","serving_correctness"}
    if len(rows)!=36 or {r["category"] for r in rows} != categories: raise ValueError("category geometry")
    if any(digest(canonical({k:v for k,v in r.items() if k!="content_sha256"})) != r["content_sha256"] for r in rows): raise ValueError("fixture identity")
    if any(len(r.get("synthetic_context",""))<40000 for r in rows if r["category"]=="long_context_retrieval"): raise ValueError("context floor")
    if any("prompt" not in r or "scorer" not in r for r in rows): raise ValueError("capture fields")


def main():
    rows=cases(); validate(rows); OUT.mkdir(exist_ok=True)
    (OUT/"development.jsonl").write_bytes(b"".join(canonical(r)+b"\n" for r in rows))
    manifest={"schema_version":1,"split":"development_calibration","case_count":len(rows),"holdout_status":"not_generated_not_inspected","fixture_sha256":digest((OUT/"development.jsonl").read_bytes()),"builder_sha256":digest(Path(__file__).read_bytes()),"nll_status":"unfrozen_requires_three_bf16_captures"}
    (OUT/"MANIFEST.json").write_bytes(canonical(manifest)+b"\n")
    print(json.dumps(manifest,sort_keys=True))

if __name__=="__main__": main()
