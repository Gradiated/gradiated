#!/usr/bin/env python3
import concurrent.futures, hashlib, json, math, os, statistics, subprocess, threading, time, urllib.request
from pathlib import Path

ROOT=Path(os.environ["CALIBRATION_FREEZE_ROOT"]); OUT=Path(os.environ["CALIBRATION_FREEZE_RESULT_OUT"]); CONTAINER_OUT=Path(os.environ["CALIBRATION_FREEZE_CONTAINER_OUT"]); INPUT=ROOT/"inputs"/"bound"; MODEL="google/gemma-4-31B-it"; N=791
def digest(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic(n,v):
    OUT.mkdir(parents=True,exist_ok=True); p=OUT/n; q=p.with_suffix(p.suffix+".part");q.write_text(json.dumps(v,sort_keys=True,indent=2)+"\n");q.replace(p)
def get(url,t=10): return urllib.request.urlopen(url,timeout=t).read()
def metrics():
    raw=get("http://127.0.0.1:30000/metrics").decode(); vals={}
    for line in raw.splitlines():
        if line and not line.startswith("#"):
            name=line.split("{",1)[0]
            if name in {"sglang:num_queue_reqs","sglang:num_running_reqs","sglang:spec_accept_length"}:
                try: vals[name]=float(line.rsplit(" ",1)[1])
                except ValueError: pass
    return vals,raw
def post(body):
    req=urllib.request.Request("http://127.0.0.1:30000/generate",json.dumps({"input_ids":body["prompt"],"sampling_params":{"temperature":0,"max_new_tokens":358,"min_new_tokens":358,"ignore_eos":True}},separators=(",",":")).encode(),{"Content-Type":"application/json"}); began=time.monotonic()
    with urllib.request.urlopen(req,timeout=1200) as r: value=json.loads(r.read())
    meta=value.get("meta_info") or {}; usage={"prompt_tokens":meta.get("prompt_tokens",len(body["prompt"])),"completion_tokens":meta.get("completion_tokens",358)};usage["total_tokens"]=usage["prompt_tokens"]+usage["completion_tokens"]
    return {"output_ids":value.get("output_ids") or meta.get("output_ids") or meta.get("completion_token_ids"),"finish_reason":meta.get("finish_reason") or value.get("finish_reason"),"usage":usage,"latency_seconds":time.monotonic()-began}
def invoke(i,arrival,released,body,expected,origin):
    try:
        a=post(body); semantic={k:a[k] for k in ("output_ids","finish_reason","usage")}; want={k:expected["semantic"][k] for k in semantic}
        return {"i":i,"arrival_s":arrival,"released_s":released,"completed_s":time.monotonic()-origin,"release_drift_seconds":released-arrival,"semantic":semantic,"semantic_matches_bound":semantic==want,"server_seconds":a["latency_seconds"]}
    except Exception as e: return {"i":i,"arrival_s":arrival,"released_s":released,"completed_s":time.monotonic()-origin,"error":repr(e)}
def body(template,i):
    b=dict(template["request_body"]); b["prompt"]=list(b["prompt"]);b["prompt"][535]=200000+i;return b
def wait():
    end=time.monotonic()+420
    while time.monotonic()<end:
        try:
            if MODEL in [x.get("id") for x in json.loads(get("http://127.0.0.1:30000/v1/models")).get("data",[])]:return
        except Exception:pass
        time.sleep(2)
    raise RuntimeError("server_not_ready")
def run_phase(indices, controls, template, origin, shifted):
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=44) as ex:
        futures=[]
        base=controls[32]["arrival_s"] if shifted else 0
        for i in indices:
            arrival=controls[i]["arrival_s"]-base;time.sleep(max(0,origin+arrival-time.monotonic())); released=time.monotonic()-origin; futures.append(ex.submit(invoke,i,arrival,released,body(template,i),controls[i],origin))
        for f in futures: rows.append(f.result())
    return rows
def main():
    hashes=json.loads((INPUT/"SHA256SUMS.json").read_text())
    for n,h in hashes.items():
        if digest(INPUT/n)!=h: raise RuntimeError("input_hash_mismatch:"+n)
    controls=[json.loads(x) for x in (INPUT/"exact_semantic_rows.jsonl").read_text().splitlines()][:N]
    if [x["i"] for x in controls]!=list(range(N)):raise RuntimeError("bound_rows_mismatch")
    trace_packet=json.loads((INPUT/"TRACE_PACKET.json").read_text()); template=next(x for x in trace_packet["primary_groups"] if x["name"]=="primary_c1")["scored"][0]
    wait(); atomic("INVOCATION_STATE.json",{"science_started":False,"phase":"calibration"})
    calibration_origin=time.monotonic(); cal=run_phase(range(32),controls,template,calibration_origin,False)
    if len(cal)!=32 or any("error" in x for x in cal):raise RuntimeError("calibration_failure")
    activation=CONTAINER_OUT/"ACTIVATION_STATE.json"; end=time.monotonic()+90
    while time.monotonic()<end and not activation.exists():time.sleep(.25)
    if not activation.exists():raise RuntimeError("activation_missing")
    state=json.loads(activation.read_text())
    if state.get("calibration_indices")!=list(range(32)) or not state.get("calibration_complete"):raise RuntimeError("activation_invalid:"+repr(state))
    atomic("CALIBRATION_RECORD.json",{"requests":cal,"activation":state,"calibration_semantics_exact":all(x["semantic_matches_bound"] for x in cal)})
    atomic("INVOCATION_STATE.json",{"science_started":True,"phase":"candidate_discriminator","requests":"32-790","freeze_proved_before_release":True})
    before,raw=metrics();(OUT/"metrics-before.prom").write_text(raw); origin=time.monotonic(); telemetry=[]; stop=threading.Event()
    def sample():
        while not stop.wait(2):
            try: telemetry.append({"elapsed_s":time.monotonic()-origin,"metrics":metrics()[0],"nvidia_smi":subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu,power.draw,memory.used","--format=csv,noheader,nounits"],text=True,capture_output=True,timeout=20).stdout.strip()})
            except Exception as e: telemetry.append({"elapsed_s":time.monotonic()-origin,"error":repr(e)})
    t=threading.Thread(target=sample,daemon=True);t.start()
    try: rows=run_phase(range(32,N),controls,template,origin,True)
    finally: stop.set();t.join(5)
    after,raw=metrics();(OUT/"metrics-after.prom").write_text(raw); rows.sort(key=lambda x:x["i"]);(OUT/"requests.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in rows));(OUT/"telemetry.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in telemetry))
    trace=[json.loads(x) for x in (CONTAINER_OUT/"calibration-freeze-ngram.jsonl").read_text().splitlines()]; activation=json.loads(activation.read_text()); valid=[x for x in rows if "error" not in x]; failures=[x for x in rows if "error" in x]; elapsed=max(x["completed_s"] for x in rows); total=sum(x["semantic"]["usage"]["total_tokens"] for x in valid); cost=2.46*(elapsed/3600)/(total/1e6) if total else None
    accepted=[r["accepted_drafts"] for e in trace if e.get("event")=="target_verify" and e.get("freeze_active") for r in e["rows"] if r.get("request_index") not in (None,32)]
    queue=max([0,*[x.get("metrics",{}).get("sglang:num_queue_reqs",0) for x in telemetry],before.get("sglang:num_queue_reqs",0),after.get("sglang:num_queue_reqs",0)]); drifts=[x["release_drift_seconds"] for x in rows]
    decision={"all_complete":len(valid)==759,"normalized_semantics_exact":len(valid)==759 and all(x["semantic_matches_bound"] for x in valid),"failures_zero":not failures,"positive_activation_identity":activation.get("calibration_complete") and activation.get("writes_after_freeze")==0,"post_calibration_writes_zero":activation.get("writes_after_freeze")==0,"unaffected_long_trunks":len(accepted)>=8 and statistics.median(accepted)>=10 and sorted(accepted)[max(0,math.ceil(.1*len(accepted))-1)]>=8,"max_server_queue_at_most_30":queue<=30,"final_server_queue_zero":(after.get("sglang:num_queue_reqs") or 0)==0,"stable_release_timing":bool(drifts) and max(abs(x) for x in drifts)<=.25,"planning_cost_at_or_below_target":cost is not None and cost<=.14}
    atomic("FINAL_TERMINAL.json",{"result":"measured_calibration_freeze_discriminator","candidate_science_consumed":True,"identity":{"overlay_sha256":digest(ROOT/"calibration_freeze_sitecustomize.py"),"requests_sha256":digest(INPUT/"requests.jsonl"),"semantic_rows_sha256":digest(INPUT/"exact_semantic_rows.jsonl"),"launch_sha256":digest(INPUT/"ngram-launch.json")},"primary":{"requests":759,"elapsed_seconds":elapsed,"total_tokens":total,"failures":failures,"planning_cost_usd_per_million_total_tokens":cost,"queue_peak":queue,"queue_final":after.get("sglang:num_queue_reqs"),"accepted_samples":len(accepted),"accepted_median":statistics.median(accepted) if accepted else None,"accepted_p10":sorted(accepted)[max(0,math.ceil(.1*len(accepted))-1)] if accepted else None},"activation":activation,"decision":decision,"conditional_endpoint_admitted":all(decision.values())})
if __name__=="__main__":
    try: main()
    except Exception as e: atomic("ATTEMPT_TERMINAL.json",{"classification":"recoverable_or_typed_remote_failure","error":repr(e),"candidate_science_consumed":False});raise
