#!/usr/bin/env python3
"""Bound remote workload producer and contemporaneous endpoint-arm consumer."""
import argparse
import concurrent.futures
import hashlib
import json
import os
import threading
import time
import urllib.request
from pathlib import Path

MODEL = "google/gemma-4-31B-it"
ROOT = Path(os.environ.get("PACKED_ENDPOINT_ROOT", "/home/glmrunner/gemma4-h100-packed-endpoint"))
RUN = ROOT / "workload-schema-repair-run"
INPUT = ROOT / "packet/candidate-v0.5.15/inputs"

def compact(x, sort=False):
    return json.dumps(x, separators=(",", ":"), sort_keys=sort, allow_nan=False).encode()

def sha(x): return hashlib.sha256(x).hexdigest()
def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    with part.open("wb") as f:
        f.write(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
        f.flush(); os.fsync(f.fileno())
    os.replace(part, path)

def request_body(template, index):
    value = json.loads(json.dumps(template))
    value.update({"model": MODEL, "ignore_eos": True, "min_tokens": 358,
                  "max_tokens": 358, "request_id": f"tail-overlap-{index}"})
    value["prompt"] = list(value["prompt"])
    value["prompt"][535] = 200000 + index
    return value

def construct():
    trace = json.loads((INPUT / "TRACE_PACKET.json").read_text())
    body = next(x for x in trace["primary_groups"] if x["name"] == "primary_c1")["scored"][0]["request_body"]
    if len(body.get("prompt", [])) != 4214: raise RuntimeError("template_prompt_length")
    source = [json.loads(x) for x in (INPUT / "exact_semantic_rows.jsonl").read_text().splitlines()[:791]]
    if [x.get("i") for x in source] != list(range(791)): raise RuntimeError("arrival_row_indices")
    if any(source[i]["arrival_s"] > source[i+1]["arrival_s"] for i in range(790)): raise RuntimeError("arrival_order")
    rows=[]
    for x in source:
        idx=61000+x["i"]; body_i=request_body(body,idx)
        rows.append({"source_i":x["i"],"fresh_index":idx,"arrival_s":x["arrival_s"],"request_body":body_i,
                     "prompt_sha256":sha(compact(body_i["prompt"])),"request_sha256":sha(compact(body_i,True))})
    if [x["fresh_index"] for x in rows] != list(range(61000,61791)): raise RuntimeError("fresh_index_interval")
    if len({x["prompt_sha256"] for x in rows}) != 791 or len({x["request_sha256"] for x in rows}) != 791: raise RuntimeError("fresh_hash_uniqueness")
    historical={sha(compact(request_body(body,i)["prompt"])) for i in list(range(1036))+list(range(60000,60004))}
    if historical & {x["prompt_sha256"] for x in rows}: raise RuntimeError("novelty_intersection")
    out=RUN / "fresh_workload.jsonl"; part=out.with_suffix(".jsonl.part"); RUN.mkdir(parents=True,exist_ok=True)
    with part.open("wb") as f:
        for x in rows: f.write(compact(x)+b"\n")
        f.flush(); os.fsync(f.fileno())
    parsed=[json.loads(x) for x in part.read_text().splitlines()]
    if len(parsed)!=791 or parsed!=rows: raise RuntimeError("atomic_workload_validation")
    os.replace(part,out); data=out.read_bytes()
    marker={"schema_version":1,"status":"complete","row_count":791,"index_interval":[61000,61790],
            "workload_byte_sha256":sha(data),"prompt_hash_set_sha256":sha(compact(sorted(x["prompt_sha256"] for x in rows))),
            "request_hash_set_sha256":sha(compact(sorted(x["request_sha256"] for x in rows))),
            "sources":{"trace_packet_sha256":sha((INPUT/"TRACE_PACKET.json").read_bytes()),"arrival_rows_sha256":sha((INPUT/"exact_semantic_rows.jsonl").read_bytes())},
            "construction_identity_sha256":sha(Path(__file__).read_bytes()),"completed_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    atomic(RUN / "FRESH_WORKLOAD.json",marker)

def get(url, timeout=10): return urllib.request.urlopen(url, timeout=timeout).read()
def metrics():
    vals={}
    for line in get("http://127.0.0.1:30000/metrics").decode().splitlines():
        if line and not line.startswith("#"):
            name=line.split("{",1)[0]
            if name in {"sglang:num_queue_reqs","sglang:num_running_reqs","sglang:spec_accept_rate","sglang:spec_accept_length"}:
                try: vals[name]=float(line.rsplit(" ",1)[1])
                except ValueError: pass
    return vals
def post(body):
    payload={"input_ids":body["prompt"],"sampling_params":{"temperature":0,"max_new_tokens":body["max_tokens"],"min_new_tokens":body["min_tokens"],"ignore_eos":body["ignore_eos"]}}
    req=urllib.request.Request("http://127.0.0.1:30000/generate",compact(payload),{"Content-Type":"application/json"})
    started=time.monotonic()
    with urllib.request.urlopen(req,timeout=1200) as r: answer=json.loads(r.read())
    meta=answer.get("meta_info") or {}; usage={"prompt_tokens":meta.get("prompt_tokens",len(body["prompt"])),"completion_tokens":meta.get("completion_tokens",body["max_tokens"])}; usage["total_tokens"]=usage["prompt_tokens"]+usage["completion_tokens"]
    return {"output_ids":answer.get("output_ids") or meta.get("output_ids") or meta.get("completion_token_ids"),"finish_reason":meta.get("finish_reason") or answer.get("finish_reason"),"usage":usage,"server_seconds":time.monotonic()-started}
def wait_server():
    end=time.monotonic()+720
    while time.monotonic()<end:
        try:
            if MODEL in [x.get("id") for x in json.loads(get("http://127.0.0.1:30000/v1/models",4)).get("data",[])]: return
        except Exception: pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")
def arm(name):
    marker=json.loads((RUN/"FRESH_WORKLOAD.json").read_text()); workload=(RUN/"fresh_workload.jsonl").read_bytes()
    if marker.get("status")!="complete" or marker.get("workload_byte_sha256")!=sha(workload): raise RuntimeError("workload_marker_invalid")
    rows=[json.loads(x) for x in workload.decode().splitlines()]
    if len(rows)!=791 or [x["fresh_index"] for x in rows]!=list(range(61000,61791)): raise RuntimeError("workload_interval_invalid")
    wait_server(); origin=time.monotonic(); telemetry=[]; stop=threading.Event()
    def sample():
        while not stop.wait(.5):
            try: telemetry.append({"elapsed_s":time.monotonic()-origin,"metrics":metrics()})
            except Exception as e: telemetry.append({"elapsed_s":time.monotonic()-origin,"metrics_error":repr(e)})
    t=threading.Thread(target=sample,daemon=True); t.start(); results=[]; submissions=[]
    def invoke(x,released):
        started=time.monotonic()-origin
        try:
            ans=post(x["request_body"]); return {"fresh_index":x["fresh_index"],"source_i":x["source_i"],"arrival_s":x["arrival_s"],"released_s":released,"client_started_s":started,"completed_s":time.monotonic()-origin,**ans}
        except Exception as e: return {"fresh_index":x["fresh_index"],"source_i":x["source_i"],"arrival_s":x["arrival_s"],"released_s":released,"error":repr(e)}
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=44) as ex:
            fs=[]
            for x in rows:
                time.sleep(max(0,origin+x["arrival_s"]-time.monotonic())); released=time.monotonic()-origin
                fs.append(ex.submit(invoke,x,released)); submissions.append({"fresh_index":x["fresh_index"],"planned_release_s":x["arrival_s"],"actual_release_s":released,"release_drift_seconds":released-x["arrival_s"]})
            results=[f.result() for f in fs]
    finally: stop.set(); t.join(5)
    results.sort(key=lambda x:x["fresh_index"]); out=RUN/f"arm_{name}"; out.mkdir(parents=True,exist_ok=True)
    (out/"requests.jsonl").write_bytes(b"".join(compact(x,True)+b"\n" for x in results)); (out/"telemetry.jsonl").write_bytes(b"".join(compact(x,True)+b"\n" for x in telemetry))
    failures=[x for x in results if "error" in x]; elapsed=max((x.get("completed_s",0) for x in results),default=0); tokens=sum(x.get("usage",{}).get("total_tokens",0) for x in results)
    atomic(out/"ARM_RESULT.json",{"arm":name,"rows":len(results),"failures":failures,"elapsed_seconds":elapsed,"service_seconds_per_request":elapsed/791 if elapsed else None,"total_tokens":tokens,"release_drift_bounded":all(abs(x["release_drift_seconds"])<=.25 for x in submissions),"telemetry_samples":len(telemetry),"request_rows_sha256":sha((out/"requests.jsonl").read_bytes()),"telemetry_sha256":sha((out/"telemetry.jsonl").read_bytes())})
    if failures: raise RuntimeError("endpoint_failures:"+repr(failures[:1]))
if __name__=="__main__":
    p=argparse.ArgumentParser(); p.add_argument("mode",choices=["construct","arm"]); p.add_argument("--arm"); a=p.parse_args(); construct() if a.mode=="construct" else arm(a.arm)
