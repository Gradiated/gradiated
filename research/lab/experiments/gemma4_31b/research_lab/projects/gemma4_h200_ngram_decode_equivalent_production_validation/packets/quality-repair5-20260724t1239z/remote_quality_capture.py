#!/usr/bin/env python3
"""Bound sequential AR/NGRAM GPQA-Diamond and TauBench quality consumer."""
from __future__ import annotations

import hashlib
import json
import pathlib
import random
import re
import subprocess
import time
import urllib.request

ROOT = pathlib.Path("/home/glmrunner/gemma4-ngram-production-quality")
PACKET = ROOT / "packet"
OUT = ROOT / "out"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MODEL = "google/gemma-4-31B-it"
BASE = ["--model-path", "/work/checkpoint", "--tokenizer-path", "/work/checkpoint", "--served-model-name", MODEL, "--dtype", "bfloat16", "--quantization", "fp8", "--tp-size", "1", "--kv-cache-dtype", "fp8_e5m2", "--host", "0.0.0.0", "--port", "30000", "--context-length", "5000", "--max-running-requests", "32", "--mem-fraction-static", "0.85", "--enable-metrics", "--skip-server-warmup", "--enable-dynamic-chunking", "--chunked-prefill-size", "2048", "--enable-fused-qk-norm-rope", "--cuda-graph-max-bs", "32", "--prefill-attention-backend", "triton", "--decode-attention-backend", "triton", "--page-size", "1", "--num-continuous-decode-steps", "1", "--triton-attention-num-kv-splits", "8", "--tool-call-parser", "gemma4"]

def canon(x): return json.dumps(x, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def sha(x): return hashlib.sha256(x).hexdigest()
def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"); tmp.replace(path)
def run(args): return subprocess.run(args, text=True, capture_output=True, check=False)
def post(body):
    raw = canon(body); req = urllib.request.Request("http://127.0.0.1:30000/v1/chat/completions", raw, {"Content-Type":"application/json"})
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=300) as response: data = response.read()
    return json.loads(data), data, time.monotonic() - started
def wait_ready(name):
    for _ in range(240):
        try:
            with urllib.request.urlopen("http://127.0.0.1:30000/v1/models", timeout=5) as r:
                if MODEL in r.read().decode(errors="replace"): return
        except Exception: pass
        time.sleep(2)
    run(["sudo","docker","logs",name]); raise RuntimeError("server_not_ready")
def launch(arm):
    name = "gemma4-ngram-quality-" + arm; run(["sudo","docker","rm","-f",name])
    args = BASE + (["--speculative-algorithm","NGRAM"] if arm == "ngram" else [])
    env = ["-e", "PYTHONPATH=/work/packet:/sgl-workspace/sglang/python", "-e", f"FP8_MODULE_AUDIT=/work/out/{arm}-fp8-modules.jsonl", "-e", f"FP8_CONSUMER_AUDIT=/work/out/{arm}-fp8-consumers.jsonl", "-e", f"FP8_RUNTIME_AUDIT=/work/out/{arm}-fp8-runtime.json"]
    cmd = ["sudo","docker","run","-d","--name",name,"--gpus","all","--ipc=host","--network","host","-v",f"{ROOT}:/work","-v",f"{ROOT}/checkpoint:/work/checkpoint:ro",*env,IMAGE,"python3","/work/packet/endpoint_entrypoint.py",*args]
    result = run(cmd); atomic(OUT / f"{arm}-launch.json", {"args":args,"returncode":result.returncode,"stdout":result.stdout,"stderr":result.stderr})
    if result.returncode: raise RuntimeError("launch_failed:" + result.stderr[-1000:])
    wait_ready(name); return name
def stop(name): run(["sudo","docker","rm","-f",name])
def empty():
    p = run(["nvidia-smi","--query-compute-apps=pid,used_memory","--format=csv,noheader"]); m = run(["nvidia-smi","--query-gpu=memory.used,utilization.gpu","--format=csv,noheader"])
    return {"processes":p.stdout.strip(),"gpu":m.stdout.strip(),"zero":not p.stdout.strip() and m.stdout.strip().startswith("0 MiB")}
def tool_schema(actions):
    return [{"type":"function","function":{"name":a["name"],"description":"Perform "+a["name"],"parameters":{"type":"object","properties":{},"additionalProperties":True}}} for a in actions]
def records(path):
    text=path.read_text(); decoder=json.JSONDecoder(); offset=0; result=[]
    while offset < len(text):
        while offset < len(text) and text[offset].isspace(): offset += 1
        if offset >= len(text): break
        row, offset = decoder.raw_decode(text, offset); result.append(row)
    return result
def gpqa_body(row):
    choices = list(row["choices"]); random.Random(20260720 + int(row["case_id"].split("-")[2])).shuffle(choices); letters="ABCD"
    prompt = row["messages"][0]["content"].strip()+"\n\nChoices:\n"+"\n".join(f"{letters[i]}. {x.strip()}" for i,x in enumerate(choices))+"\nAnswer with only the letter."
    expected=row["expected_answer"].strip(); expected_index=next(i for i,x in enumerate(choices) if x.strip()==expected)
    return {"model":MODEL,"messages":[{"role":"user","content":prompt}],"temperature":0,"seed":20260718,"max_tokens":8}, letters[expected_index]
def calls(response):
    msg=((response.get("choices") or [{}])[0].get("message") or {}); result=[]
    for x in msg.get("tool_calls") or []:
        f=x.get("function") or {}
        try: args=json.loads(f.get("arguments","{}"))
        except Exception: args=None
        result.append({"name":f.get("name"),"arguments":args})
    return result
def capture_arm(arm, gpqa, tau):
    name=launch(arm); atomic(OUT/"INVOCATION_STATE.json", {"control_science_started":True,"candidate_science_started":arm=="ngram"})
    try:
        gpqa_path=OUT/f"{arm}-gpqa.jsonl"; tau_path=OUT/f"{arm}-tau.jsonl"
        gp=[json.loads(x) for x in gpqa_path.read_text().splitlines() if x.strip()] if gpqa_path.exists() else []
        tp=[json.loads(x) for x in tau_path.read_text().splitlines() if x.strip()] if tau_path.exists() else []
        gp_done={x["case_id"] for x in gp}; tau_done={x["case_id"] for x in tp}
        for row in gpqa:
            if row["case_id"] in gp_done: continue
            body,expected=gpqa_body(row); response,raw,elapsed=post(body); text=(((response.get("choices")or[{}])[0].get("message")or{}).get("content")or"").strip().upper(); match=re.search(r"\b([ABCD])\b",text)
            gp.append({"case_id":row["case_id"],"request":body,"response":response,"raw_response_sha256":sha(raw),"elapsed_seconds":elapsed,"expected":expected,"answer":match.group(1) if match else None,"pass":bool(match and match.group(1)==expected),"usage":response.get("usage")})
            gpqa_path.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in gp))
        for row in tau:
            if row["case_id"] in tau_done: continue
            expected=row["expected_actions"]; body={"model":MODEL,"messages":row["messages"],"temperature":0,"seed":20260718,"max_tokens":256}
            if expected: body.update({"tools":tool_schema(expected),"tool_choice":"required"})
            response,raw,elapsed=post(body); observed=calls(response)
            tp.append({"case_id":row["case_id"],"request":body,"response":response,"raw_response_sha256":sha(raw),"elapsed_seconds":elapsed,"expected_actions":expected,"observed_actions":observed,"pass":observed[:len(expected)]==expected,"usage":response.get("usage"),"finish_reason":((response.get("choices")or[{}])[0].get("finish_reason"))})
            (OUT/f"{arm}-tau.jsonl").write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in tp))
        for label, rows in (("gpqa",gp),("tau",tp)):
            p=OUT/f"{arm}-{label}.jsonl"; p.write_text("".join(json.dumps(x,sort_keys=True,ensure_ascii=False)+"\n" for x in rows))
        usage=[x.get("usage") or {} for x in gp+tp]; result={"arm":arm,"gpqa":{"count":len(gp),"accuracy":sum(x["pass"] for x in gp)/len(gp)},"taubench":{"count":len(tp),"task_success":sum(x["pass"] for x in tp)/len(tp)},"economics":{"completion_tokens":sum(int(x.get("completion_tokens") or 0) for x in usage),"total_tokens":sum(int(x.get("total_tokens") or 0) for x in usage),"latency_seconds":sum(x["elapsed_seconds"] for x in gp+tp)},"raw_hashes":{"gpqa":sha((OUT/f"{arm}-gpqa.jsonl").read_bytes()),"tau":sha((OUT/f"{arm}-tau.jsonl").read_bytes())}}
        atomic(OUT/f"{arm}-RESULT.json",result); return result
    finally: stop(name)
def bootstrap(control,candidate,key,n=10000):
    d=[int(b["pass"])-int(a["pass"]) for a,b in zip(control,candidate)]; rng=random.Random(20260724); values=sorted(sum(d[rng.randrange(len(d))] for _ in d)/len(d) for _ in range(n)); return {"replicates":n,"candidate_minus_control":sum(d)/len(d),"ci_95":[values[250],values[9750]],"noninferior_3pp":values[250]>=-0.03}
def main():
    OUT.mkdir(parents=True,exist_ok=True); gpqa=records(PACKET/"gpqa_diamond_requests.jsonl"); tau=records(PACKET/"taubench_requests.jsonl")
    atomic(OUT/"INVOCATION_STATE.json", {"control_science_started":False,"candidate_science_started":False}); control=capture_arm("control",gpqa,tau); zero=empty(); atomic(OUT/"ZERO_HBM_AFTER_CONTROL.json",zero)
    if not zero["zero"]: raise RuntimeError("control_cleanup_not_zero")
    candidate=capture_arm("ngram",gpqa,tau)
    cg=[json.loads(x) for x in (OUT/"control-gpqa.jsonl").read_text().splitlines()]; ng=[json.loads(x) for x in (OUT/"ngram-gpqa.jsonl").read_text().splitlines()]; ct=[json.loads(x) for x in (OUT/"control-tau.jsonl").read_text().splitlines()]; nt=[json.loads(x) for x in (OUT/"ngram-tau.jsonl").read_text().splitlines()]
    gboot=bootstrap(cg,ng,"gpqa"); tboot=bootstrap(ct,nt,"tau"); inflation=candidate["economics"]["completion_tokens"]-control["economics"]["completion_tokens"]
    terminal={"schema_version":1,"classification":"sequential_ngram_production_quality_complete","control":control,"candidate":candidate,"paired_bootstrap":{"gpqa":gboot,"taubench":tboot},"completion_token_inflation":inflation,"scientific_invocation":{"control":True,"candidate":True},"pass":gboot["noninferior_3pp"] and tboot["noninferior_3pp"]}
    atomic(OUT/"TERMINAL.json",terminal)
if __name__=="__main__": main()
