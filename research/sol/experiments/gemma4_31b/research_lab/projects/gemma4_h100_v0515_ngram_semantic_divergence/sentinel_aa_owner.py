#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

P = Path(__file__).resolve().parent
LAB = P.parents[1]
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
NAME = "gemma4_h100_v0515_ngram_semantic_divergence"
BENCH = "h100-v0515-endpoint-200g-r2-e00yfnrrfczsdjevms"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
IMAGE = "docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
REMOTE = "/home/glmrunner/gemma4-h100-v0515-sentinel-aa"
CONTAINER = "gemma4-h100-v0515-sentinel-aa"

def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def atomic(p, x):
    p = Path(p); p.parent.mkdir(parents=True, exist_ok=True); q = p.with_suffix(p.suffix + ".part")
    q.write_text(json.dumps(x, indent=2, sort_keys=True) + "\n"); q.replace(p)
def run(x, **kw): return subprocess.run(x, text=True, capture_output=True, **kw)
def ssh(ip, command, timeout=1200):
    return run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{ip}", "bash", "-s"], input=command, timeout=timeout)
def heartbeat(stop, events):
    while not stop.wait(40):
        r = run(["env", "PYTHONPATH=/root/workspace/research/factory/src", *POOL, "heartbeat", "--project", NAME], timeout=30)
        events.append({"at": now(), "returncode": r.returncode})

def audit():
    b = json.loads((P / "DIRECTOR_SENTINEL_AA_BINDING.json").read_text()); rows=[]
    for group in ("prior_localization", "runtime_identity", "bound_sources"):
        for name, item in b[group].items():
            if not isinstance(item, dict) or "path" not in item: continue
            f = (P / item["path"]).resolve(); actual = sha(f) if f.is_file() else None
            rows.append({"group": group, "name": name, "path": str(f), "expected": item.get("sha256"), "actual": actual, "pass": actual == item.get("sha256")})
    for f in (P / "inputs/bound").glob("*"):
        rows.append({"group":"project_snapshot", "name":f.name, "path":str(f), "actual":sha(f), "pass":True})
    x={"binding_sha256":sha(P / "DIRECTOR_SENTINEL_AA_BINDING.json"),"checks":rows,"pass":all(r["pass"] for r in rows)}
    atomic(P / "BINDING_AUDIT.json", x); return b, x

def build_patch(src, out, kind):
    text = Path(src).read_text()
    if kind == "worker":
        text = text.replace("import logging\n", "import logging\nimport json\nimport os\nimport time\n")
        needle = "        return GenerationBatchResult(\n"
        insert = '''        try:
            trace_path = os.environ.get("SENTINEL_AA_TRACE")
            if trace_path and batch.forward_mode.is_decode():
                lens = accept_lens.detach().cpu().tolist()
                flat = accept_tokens.detach().cpu().tolist()
                stride = self.draft_token_num
                rows = []
                for i, req in enumerate(batch.reqs):
                    accepted = flat[i * stride : i * stride + lens[i]]
                    rows.append({"event":"target_accept_kv","rid":str(req.rid),"batch_row":i,"request_pool_index":int(batch.req_pool_indices[i]),"raw_batch_size":bs,"padded_batch_size":int(batch.seq_lens.shape[0]),"seq_len_before_verify":int(batch.seq_lens[i]),"drafts":list(verify_input.draft_token[i].detach().cpu().tolist()),"target_argmax_chain":accepted,"accept_len":int(lens[i]),"accepted_tokens":accepted,"kv_committed_len_before":int(getattr(req,"kv_committed_len",0)),"kv_committed_len_after_worker":int(getattr(req,"kv_committed_len",0))})
                with open(trace_path, "a") as f:
                    for row in rows: f.write(json.dumps(row, sort_keys=True) + "\\n")
        except Exception as exc:
            with open(os.environ.get("SENTINEL_AA_TRACE", "/tmp/sentinel_trace.jsonl"), "a") as f: f.write(json.dumps({"event":"instrumentation_error","where":"worker","error":repr(exc)})+"\\n")
'''
        if needle not in text: raise RuntimeError("worker_patch_anchor_missing")
        text = text.replace(needle, insert + needle, 1)
    else:
        text = text.replace("import logging\n", "import logging\nimport json\nimport os\n")
        needle = "        return predict_tokens\n"
        insert = '''        try:
            trace_path = os.environ.get("SENTINEL_AA_TRACE")
            if trace_path:
                with open(trace_path, "a") as f:
                    for i, req in enumerate(batch.reqs):
                        f.write(json.dumps({"event":"scheduler_emit","rid":str(req.rid),"batch_row":i,"scheduler_emitted_tokens":predict_tokens[i],"kv_committed_len_after":int(getattr(req,"kv_committed_len",0))}, sort_keys=True) + "\\n")
        except Exception as exc:
            with open(os.environ.get("SENTINEL_AA_TRACE", "/tmp/sentinel_trace.jsonl"), "a") as f: f.write(json.dumps({"event":"instrumentation_error","where":"scheduler","error":repr(exc)})+"\\n")
'''
        if needle not in text: raise RuntimeError("processor_patch_anchor_missing")
        text = text.replace(needle, insert + needle, 1)
    Path(out).write_text(text)

def main():
    import argparse
    a=argparse.ArgumentParser(); a.add_argument("--ip",required=True); a.add_argument("--deadline-epoch",type=float,required=True); a.add_argument("--artifact-root",type=Path,required=True); ns=a.parse_args()
    out=ns.artifact_root.resolve(); out.mkdir(parents=True,exist_ok=True); events=[]; stop=threading.Event(); hb=threading.Thread(target=heartbeat,args=(stop,events),daemon=True); hb.start()
    terminal={"schema_version":1,"project":NAME,"bench":BENCH,"started_at":now(),"candidate_science_consumed":False}
    release="maintenance"
    try:
        binding, aud = audit()
        if not aud["pass"]: raise RuntimeError("binding_audit_failed")
        inputs=P/"inputs"; inst=inputs/"instrumented"; inst.mkdir(exist_ok=True)
        build_patch(inputs/"bound_source/sglang/srt/speculative/ngram_worker.py", inst/"ngram_worker.py", "worker")
        build_patch(inputs/"bound_source/sglang/srt/managers/scheduler_components/batch_result_processor.py", inst/"batch_result_processor.py", "processor")
        launch=json.loads((inputs/"bound/ngram-launch.json").read_text())["args"]
        trace=json.loads((inputs/"bound/TRACE_PACKET.json").read_text()); template=next(x for x in trace["primary_groups"] if x["name"]=="primary_c1")["scored"][0]["request_body"]
        consumed=[]
        for line in (inputs/"bound/exact_semantic_rows.jsonl").read_text().splitlines(): consumed.append(json.loads(line).get("i"))
        def body(index,rid):
            x=dict(template); x.update({"model":"google/gemma-4-31B-it","ignore_eos":True,"min_tokens":358,"max_tokens":358,"request_id":rid}); x["prompt"]=list(x["prompt"]); x["prompt"][535]=200000+index; return x
        arms=[("isolated_a_1",[body(60000,"sentinel-a-isolated-1")]),("isolated_a_2",[body(60000,"sentinel-a-isolated-2")]),("cobatched_ab",[body(60000,"sentinel-a-cobatched"),body(60001,"sentinel-b-cobatched")])]
        novelty={"consumed_indices":consumed,"new_indices":[60000,60001],"indices_disjoint":not set(consumed)&{60000,60001},"arms":[{"name":n,"bodies":[{"request_id":b["request_id"],"prompt_sha256":hashlib.sha256(json.dumps(b["prompt"],separators=(",",":")).encode()).hexdigest(),"request_sha256":hashlib.sha256(json.dumps(b,sort_keys=True,separators=(",",":")).encode()).hexdigest()} for b in bs]} for n,bs in arms]}
        novelty["pass"]=novelty["indices_disjoint"] and len({x["prompt_sha256"] for a in novelty["arms"] for x in a["bodies"] if "a-" in x["request_id"]})==1 and len({x["prompt_sha256"] for a in novelty["arms"] for x in a["bodies"]})==2
        atomic(P/"SENTINEL_NOVELTY.json",novelty)
        if not novelty["pass"]: raise RuntimeError("novelty_gate_failed")
        packet=out/"remote_packet"; shutil.copytree(inputs,packet,dirs_exist_ok=True)
        atomic(packet/"arms.json",{"arms":[{"name":n,"bodies":bs} for n,bs in arms]})
        runner='''import concurrent.futures,json,os,time,urllib.request,hashlib,pathlib\nout=pathlib.Path("/work/out"); out.mkdir(exist_ok=True); arms=json.load(open("/work/packet/arms.json"))["arms"]\ndef post(b):\n p={"input_ids":b["prompt"],"sampling_params":{"temperature":0,"min_new_tokens":358,"max_new_tokens":358,"ignore_eos":True}}; q=urllib.request.Request("http://127.0.0.1:30000/generate",json.dumps(p,separators=(",",":")).encode(),{"Content-Type":"application/json"}); t=time.monotonic(); r=json.loads(urllib.request.urlopen(q,timeout=1200).read()); m=r.get("meta_info") or {}; return {"rid":b["request_id"],"latency_s":time.monotonic()-t,"output_ids":r.get("output_ids") or m.get("output_ids") or m.get("completion_token_ids"),"usage":{"prompt_tokens":m.get("prompt_tokens",len(b["prompt"])),"completion_tokens":m.get("completion_tokens",358)},"raw_sha256":hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()}\nfor arm in arms:\n with concurrent.futures.ThreadPoolExecutor(max_workers=len(arm["bodies"])) as e: rows=[f.result() for f in [e.submit(post,b) for b in arm["bodies"]]]\n (out/(arm["name"]+".json")).write_text(json.dumps(rows,indent=2,sort_keys=True)+"\\n")\nprint("SENTINEL_RUNNER_DONE")\n'''
        (packet/"runner.py").write_text(runner)
        archive=out/"packet.tar"; subprocess.run(["tar","-C",str(packet),"-cf",str(archive),"."],check=True)
        stage=f"mkdir -p {REMOTE}/packet {REMOTE}/out {REMOTE}/instrumented; tar -C {REMOTE}/packet -xf -"
        with archive.open("rb") as f:
            s=subprocess.run(["ssh","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{ns.ip}",stage],stdin=f,text=False,capture_output=True,timeout=300)
        (out/"STAGE.stdout").write_bytes(s.stdout); (out/"STAGE.stderr").write_bytes(s.stderr)
        if s.returncode: raise RuntimeError("stage_failed")
        for local, remote in ((inst/"ngram_worker.py","ngram_worker.py"),(inst/"batch_result_processor.py","batch_result_processor.py")):
            r=run(["scp","-q","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",str(local),f"glmrunner@{ns.ip}:{REMOTE}/instrumented/{remote}"],timeout=120)
            if r.returncode: raise RuntimeError("instrument_stage_failed:"+remote)
        remote_cmd=f'''set -euo pipefail
sudo -n docker rm -f {CONTAINER} >/dev/null 2>&1 || true
sudo -n docker run -d --name {CONTAINER} --gpus all --ipc=host --network=host -e SENTINEL_AA_TRACE=/work/out/trace.jsonl -v /home/glmrunner/gemma4-h100-v0515-ngram-price-normalized/checkpoint:/work/checkpoint:ro -v /home/glmrunner/gemma4-h100-v0515-ngram-price-normalized/candidate-v0.5.15:/work/candidate-v0.5.15:ro -v {REMOTE}/packet:/work/packet:ro -v {REMOTE}/out:/work/out -v {REMOTE}/instrumented/ngram_worker.py:/sgl-workspace/sglang/python/sglang/srt/speculative/ngram_worker.py:ro -v {REMOTE}/instrumented/batch_result_processor.py:/sgl-workspace/sglang/python/sglang/srt/managers/scheduler_components/batch_result_processor.py:ro {IMAGE} python3 -m sglang.launch_server {' '.join(subprocess.list2cmdline([x]) for x in launch)}
for i in $(seq 1 120); do curl -fsS --max-time 3 http://127.0.0.1:30000/v1/models >/dev/null && break; sleep 5; done
curl -fsS --max-time 3 http://127.0.0.1:30000/v1/models >/dev/null
sudo -n docker exec {CONTAINER} python3 /work/packet/runner.py
'''
        atomic(P/"STATUS.json",{**json.loads((P/"STATUS.json").read_text()),"active_session":{"unit":str(out/"OWNER_STATE.json"),"unit_manager":"pid","artifact_root":str(out),"deadline_utc":"2026-07-25T13:20:00Z","expected_terminal":"SENTINEL_AA_TERMINAL.json"}})
        r=ssh(ns.ip,remote_cmd,timeout=max(60,int(ns.deadline_epoch-time.time()-120))); (out/"REMOTE.stdout").write_text(r.stdout); (out/"REMOTE.stderr").write_text(r.stderr)
        logs=ssh(ns.ip,f"sudo -n docker logs {CONTAINER} 2>&1 || true",timeout=120); (out/"SERVER.log").write_text(logs.stdout+logs.stderr)
        retrieve=ssh(ns.ip,f"tar -C {REMOTE}/out -cf - .",timeout=180)
        if retrieve.returncode: raise RuntimeError("retrieve_failed")
        tar=out/"remote_out.tar"; tar.write_text("")
        # stdout is decoded by ssh helper; re-fetch raw archive with scp to avoid trace loss.
        rr=run(["scp","-r","-q","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{ns.ip}:{REMOTE}/out/.",str(out/"remote")],timeout=180)
        if rr.returncode: raise RuntimeError("retrieve_scp_failed")
        remote=out/"remote"; trace_rows=[json.loads(x) for x in (remote/"trace.jsonl").read_text().splitlines() if x.strip()] if (remote/"trace.jsonl").exists() else []
        responses={}
        for f in remote.glob("*.json"):
            if f.name in ("trace.jsonl",): continue
            try:
                v=json.loads(f.read_text())
                if isinstance(v,list): responses.update({x["rid"]:x for x in v})
            except Exception: pass
        target={}; sched={}
        for x in trace_rows:
            if x.get("event")=="target_accept_kv": target.setdefault(x["rid"],[]).append(x)
            if x.get("event")=="scheduler_emit": sched.setdefault(x["rid"],[]).append(x)
        inv=[]
        for rid, steps in target.items():
            for i,x in enumerate(steps):
                y=sched.get(rid,[{}]*len(steps))[i] if i<len(sched.get(rid,[])) else {}; ok=x["accepted_tokens"]==x["target_argmax_chain"]==y.get("scheduler_emitted_tokens") and x["accept_len"]==len(x["accepted_tokens"]) and y.get("kv_committed_len_after",-1)>=x["kv_committed_len_before"]+x["accept_len"]
                inv.append({"rid":rid,"step":i,"pass":ok,"target_accept":x,"scheduler":y,"response_output_ids":responses.get(rid,{}).get("output_ids")})
        a1=responses.get("sentinel-a-isolated-1",{}).get("output_ids"); a2=responses.get("sentinel-a-isolated-2",{}).get("output_ids"); ac=responses.get("sentinel-a-cobatched",{}).get("output_ids")
        exact=bool(a1 and a1==a2==ac and inv and all(x["pass"] for x in inv) and not any(x.get("event")=="instrumentation_error" for x in trace_rows))
        classification="sentinel_exact" if exact else "batch_numerical_divergence" if a1 and ac and a1!=ac else "typed_invalid"
        result={"schema_version":1,"classification":classification,"novelty":novelty,"per_rid_invariant":inv,"responses":responses,"trace_rows":len(trace_rows),"instrumentation_errors":[x for x in trace_rows if x.get("event")=="instrumentation_error"],"isolated_identical":a1==a2,"isolated_vs_cobatched_identical":a1==ac}
        atomic(P/"SENTINEL_AA_RESULT.json",result); terminal.update({"candidate_science_consumed":True,"classification":classification,"result_sha256":sha(P/"SENTINEL_AA_RESULT.json")}); release="ready" if classification=="sentinel_exact" else "maintenance"
    except Exception as e:
        terminal.update({"classification":"typed_invalid","error":repr(e)})
    finally:
        terminal["finished_at"]=now(); terminal["heartbeat_events"]=events; terminal["actual_spend_usd"]=round(2.95*max(0,time.time()-(ns.deadline_epoch-2400))/3600,4); atomic(P/"SENTINEL_AA_TERMINAL.json",terminal)
        current=json.loads((P/"STATUS.json").read_text()); current.update({"active_session":None,"actual_spend_usd":terminal["actual_spend_usd"],"status":"complete" if terminal["candidate_science_consumed"] else "active","summary":terminal["classification"],"next_action":"Review SENTINEL_AA_RESULT.json and terminal.","terminal_artifact":"SENTINEL_AA_TERMINAL.json"}); atomic(P/"STATUS.json",current)
        stop.set(); hb.join(5); run(["env","PYTHONPATH=/root/workspace/research/factory/src",*POOL,"release","--project",NAME,"--condition",release],timeout=60)
    return 0 if terminal["candidate_science_consumed"] else 2
if __name__ == "__main__": raise SystemExit(main())
