#!/usr/bin/env python3
"""Durable owner for one admitted exact-c32 graph-gap matched pair."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import tarfile
import threading
import time

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_c32_graph_gap_elision"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
IP = "89.169.109.132"
REMOTE = "/home/glmrunner/gemma4-persistent-grouped-lm-head"
RATE, AUTH = 2.45, 3.00
RELEASE_BY = dt.datetime(2026, 7, 26, 5, 10, tzinfo=dt.timezone.utc)
WEIGHT_SHA = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
WEIGHT_BYTES = 49784788364
SOURCE = [
    "grouped_lm_head.py", "endpoint_pair.py", "sitecustomize.py", "token_trace_hook.py",
    "ngram_worker.py",
    "inputs/bound/endpoint_entrypoint.py", "inputs/bound/exact_runner.py",
    "inputs/bound/forward_batch_info.py", "inputs/bound/logits_processor.py",
    "inputs/bound/decode_equivalent_lm_head.py", "inputs/bound/config.json",
    "inputs/bound/model.safetensors.index.json", "inputs/bound/CHECKPOINT_MANIFEST.json",
]

def now(): return dt.datetime.now(dt.timezone.utc)
def atomic(p, v):
    p.parent.mkdir(parents=True, exist_ok=True); q=p.with_suffix(p.suffix+".part")
    q.write_text(json.dumps(v, indent=2, sort_keys=True)+"\n"); os.replace(q,p)
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for b in iter(lambda:f.read(16<<20), b""): h.update(b)
    return h.hexdigest()
def run(a, timeout=None, env=None): return subprocess.run(a,text=True,capture_output=True,check=False,timeout=timeout,env=env)
def pool(*a): return run(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),*a],env={**os.environ,"PYTHONPATH":str(FACTORY)})
def ssh(cmd, timeout): return run(["ssh","-i",str(KEY),"-o","BatchMode=yes","-o","ServerAliveInterval=20","-o","ServerAliveCountMax=3","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{IP}",cmd],timeout=timeout)
def scp(src,dst,timeout): return run(["scp","-p","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",src,dst],timeout=timeout)
def update(**changes):
    value=json.loads((PROJECT/"STATUS.json").read_text()); value.update(changes); atomic(PROJECT/"STATUS.json",value)
def heartbeat(stop, artifact):
    while not stop.wait(45):
        r=pool("heartbeat","--project",NAME)
        atomic(artifact/"OWNER_HEARTBEAT.json",{"at_utc":now().isoformat(),"returncode":r.returncode,"stdout":r.stdout[-800:],"stderr":r.stderr[-800:]})
def contents(artifact, spend, result, materialization):
    return {"schema_version":1,"project":NAME,"result":result,"artifact":str(artifact.relative_to(PROJECT)),"actual_spend_usd":spend,"checkpoint":{"weight":{"sha256":WEIGHT_SHA,"bytes":WEIGHT_BYTES,"materialization":materialization}},"image":"docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6","server_state":"No experiment server or worker remains; project immutable weight, pinned image, compiler, and CUDA caches retained.","processes_stopped":True,"next":"Available for a compatible director-selected H200 project."}
def release(artifact, condition, value):
    p=artifact/"BENCH_CONTENTS.json"; atomic(p,value); r=pool("release","--project",NAME,"--condition",condition,"--contents",str(p));
    (artifact/"release.stdout").write_text(r.stdout); (artifact/"release.stderr").write_text(r.stderr); return {"condition":condition,"returncode":r.returncode,"released":r.returncode==0,"at_utc":now().isoformat()}

def main():
    status=json.loads((PROJECT/"STATUS.json").read_text())
    prior=float(status.get("actual_spend_usd",0))+float(status.get("historical_actual_spend_usd",0))
    if float(status["authorized_spend_usd"]) != AUTH or prior >= AUTH: raise RuntimeError("typed_budget_boundary:cumulative_reservation_exhausted")
    if not KEY.is_file() or not KNOWN.is_file(): raise RuntimeError("typed_identity_boundary:local_ssh_identity_missing")
    binding=json.loads((PROJECT/"SOURCE_READY.json").read_text())
    if sha(PROJECT/"ngram_worker.py") != binding["source"]["candidate"]["sha256"]: raise RuntimeError("typed_binding_boundary:candidate_source")
    if sha(PROJECT/"endpoint_pair.py") != binding["launchers"]["endpoint_pair"]["sha256"]: raise RuntimeError("typed_binding_boundary:endpoint_outer")
    artifact=PROJECT/"artifacts"/f"c32-graph-gap-{now().strftime('%Y%m%dt%H%M%SZ').lower()}"
    lease_seconds=max(1, min(1700, int((AUTH-prior)*3600/RATE)))
    claim=pool("claim","--project",NAME,"--bench",BENCH,"--lease-seconds",str(lease_seconds))
    if claim.returncode: raise RuntimeError(f"typed_pool_boundary:claim_failed:{claim.stderr[-800:]}")
    artifact.mkdir(parents=True,exist_ok=False); (artifact/"claim.stdout").write_text(claim.stdout); (artifact/"claim.stderr").write_text(claim.stderr)
    owner=json.loads((PROJECT/"PAIR_OWNER_CONTROLLER.json").read_text())
    update(active_session={"artifact_root":str(artifact.relative_to(PROJECT)),"bench_id":BENCH,"deadline_utc":RELEASE_BY.isoformat(),"expected_terminal":"C32_GRAPH_GAP_ELISION_TERMINAL.json","forward_progress":"claim complete; immutable source staging and exact stock/candidate pair underway","unit":str(PROJECT/"PAIR_OWNER_CONTROLLER.json"),"pid":owner["pid"],"start_ticks":owner["start_ticks"],"unit_manager":"pid"})
    claimed=now(); stop=threading.Event(); threading.Thread(target=heartbeat,args=(stop,artifact),daemon=True).start(); materialization={}; terminal=None
    try:
        manifest={"files":[{"path":n,"bytes":(PROJECT/n).stat().st_size,"sha256":sha(PROJECT/n)} for n in SOURCE]}; identity=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":" )).encode()).hexdigest(); packet=artifact/"source-packets"/identity; packet.mkdir(parents=True); atomic(packet/"SOURCE_MANIFEST.json",manifest)
        archive=packet/"source.tar.gz"
        with tarfile.open(archive,"w:gz") as t:
            for n in SOURCE: t.add(PROJECT/n,arcname=n,recursive=False)
        remote_archive=f"{REMOTE}/source-{identity}.tar.gz.part"; snapshot=f"{REMOTE}/snapshots/{identity}"
        if ssh(f"test -d {shlex.quote(snapshot)}",30).returncode:
            r=ssh(f"install -d {shlex.quote(REMOTE+'/snapshots')} && rm -f {shlex.quote(remote_archive)}",120)
            if r.returncode: raise RuntimeError(f"source_prepare_failed:{r.stderr[-800:]}")
            r=scp(str(archive),f"glmrunner@{IP}:{remote_archive}",600)
            if r.returncode: raise RuntimeError(f"source_copy_failed:{r.stderr[-800:]}")
            r=ssh(f"rm -rf {shlex.quote(snapshot+'.part')} && mkdir {shlex.quote(snapshot+'.part')} && tar -xzf {shlex.quote(remote_archive)} -C {shlex.quote(snapshot+'.part')} && chmod -R a-w {shlex.quote(snapshot+'.part')} && mv {shlex.quote(snapshot+'.part')} {shlex.quote(snapshot)} && rm -f {shlex.quote(remote_archive)}",600)
            if r.returncode: raise RuntimeError(f"source_finalize_failed:{r.stderr[-800:]}")
        r=ssh(f"ln -sfn {shlex.quote(snapshot)} {shlex.quote(REMOTE+'/project')}",120)
        if r.returncode: raise RuntimeError(f"source_activation_failed:{r.stderr[-800:]}")
        source_weight="/home/glmrunner/gemma4-fixed-m384-executor/checkpoint/model-00001-of-00002.safetensors"; project_weight=f"{REMOTE}/immutable/{WEIGHT_SHA}/model-00001-of-00002.safetensors"
        r=ssh(f"sudo install -d -o glmrunner -g glmrunner {shlex.quote(REMOTE+'/immutable/'+WEIGHT_SHA)} && if test ! -f {shlex.quote(project_weight)}; then sudo ln {shlex.quote(source_weight)} {shlex.quote(project_weight+'.part')} && sudo chmod 0444 {shlex.quote(project_weight+'.part')} && sudo mv {shlex.quote(project_weight+'.part')} {shlex.quote(project_weight)}; fi; stat -c '%d:%i:%s' {shlex.quote(source_weight)} {shlex.quote(project_weight)}; sha256sum {shlex.quote(project_weight)}",1800)
        if r.returncode or WEIGHT_SHA not in r.stdout: raise RuntimeError(f"weight_materialization_failed:{r.stderr[-800:]}")
        materialization={"method":"verified_hardlink","source":source_weight,"project":project_weight,"stat":r.stdout.splitlines()[:-1],"sha256":WEIGHT_SHA}; atomic(artifact/"WEIGHT_MATERIALIZATION.json",materialization)
        remote_art=f"{REMOTE}/artifacts/{artifact.name}"; remaining=max(1,int((RELEASE_BY-now()).total_seconds()-180))
        command=f"install -d {shlex.quote(remote_art)} && GROUPED_LM_HEAD_REMOTE_ROOT={shlex.quote(REMOTE)} GROUPED_LM_HEAD_PAIR_ROOT={shlex.quote(remote_art+'/pair')} python3 {shlex.quote(REMOTE+'/project/endpoint_pair.py')}"
        atomic(artifact/"INVOCATION_STATE.json",{"pre_science":False,"scientific_invocation_started":True,"arm_submission":"control_then_candidate_exact_c32"})
        worker=ssh(command,remaining); (artifact/"worker.stdout").write_text(worker.stdout); (artifact/"worker.stderr").write_text(worker.stderr); atomic(artifact/"WORKER.json",{"returncode":worker.returncode,"scientific_invocation_started":True})
        for n in ("PAIR_TERMINAL.json","PAIR_RESULT.json","INVOCATION_STATE.json","CONTROL_PRODUCER_STAGE.json","CANDIDATE_PRODUCER_STAGE.json"):
            d=artifact/"retrieved"/n; d.parent.mkdir(exist_ok=True); g=scp(f"glmrunner@{IP}:{remote_art}/pair/{n}",str(d),300); atomic(artifact/(n+".retrieval.json"),{"returncode":g.returncode,"stderr":g.stderr[-800:]})
        p=artifact/"retrieved/PAIR_TERMINAL.json"
        if not p.exists(): raise RuntimeError("typed_retrieval_boundary:pair_terminal_missing")
        pair=json.loads(p.read_text()); elapsed=(now()-claimed).total_seconds(); spend=min(AUTH,prior+max(0,elapsed)*RATE/3600); result="correct_faster" if pair.get("valid") and pair.get("service_time_delta_fraction",0)<0 else ("correct_nonpositive" if pair.get("valid") else "quality_or_observer_reject")
        terminal={"schema_version":1,"classification":"scientific_terminal","result":result,"pair":pair,"science_consumed":True,"artifact_root":str(artifact.relative_to(PROJECT)),"provider":{"bench_id":BENCH,"claimed_at_utc":claimed.isoformat(),"completed_at_utc":now().isoformat(),"hourly_rate_usd":RATE,"actual_spend_usd":spend},"weight_materialization":materialization}; atomic(PROJECT/"C32_GRAPH_GAP_ELISION_TERMINAL.json",terminal)
        update(actual_spend_usd=spend,status="complete",decision=result,summary=f"One matched exact-c32 graph-gap pair completed: {result}.",terminal_artifact="C32_GRAPH_GAP_ELISION_TERMINAL.json",active_session=None)
        terminal["provider"]["release"]=release(artifact,"ready",contents(artifact,spend,result,materialization)); atomic(PROJECT/"C32_GRAPH_GAP_ELISION_TERMINAL.json",terminal)
    except Exception as e:
        elapsed=(now()-claimed).total_seconds(); spend=min(AUTH,prior+max(0,elapsed)*RATE/3600); boundary={"schema_version":1,"classification":"typed_controller_or_retrieval_boundary","error":f"{type(e).__name__}: {e}","science_consumed":True,"actual_spend_usd":spend,"artifact_root":str(artifact.relative_to(PROJECT))}; atomic(PROJECT/"C32_GRAPH_GAP_ELISION_TERMINAL.json",boundary); update(actual_spend_usd=spend,status="complete",decision="typed_controller_or_retrieval_boundary",terminal_artifact="C32_GRAPH_GAP_ELISION_TERMINAL.json",active_session=None); boundary["release"]=release(artifact,"maintenance",contents(artifact,spend,"typed_controller_or_retrieval_boundary",materialization)); atomic(PROJECT/"C32_GRAPH_GAP_ELISION_TERMINAL.json",boundary)
    finally: stop.set()

if __name__ == "__main__": main()
