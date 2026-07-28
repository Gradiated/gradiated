#!/usr/bin/env python3
"""Bound durable owner for the one graph-safe H200 discriminator."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import threading
import time

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = pathlib.Path("/root/workspace/research/factory/src")
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
NAME = "gemma4_h200_ngram_persistent_grouped_lm_head"
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
IP = "89.169.109.132"
REMOTE = "/home/glmrunner/gemma4-persistent-grouped-lm-head"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
RATE = 2.45
AUTH = 1.25
CLAIM_BY = dt.datetime(2026, 7, 25, 20, 55, tzinfo=dt.timezone.utc)
RELEASE_BY = dt.datetime(2026, 7, 25, 21, 25, tzinfo=dt.timezone.utc)
WEIGHT_SHA = "eeef8791537bc04f110967c513149e037d2a9ae97d49add7291ebfa62806bbfa"
WEIGHT_BYTES = 49784788364
SOURCE = ("grouped_lm_head.py", "exact_consumer_component.py", "graph_safe_buffer_discriminator.py")


def now() -> dt.datetime: return dt.datetime.now(dt.timezone.utc)
def stamp() -> str: return now().strftime("%Y%m%dt%H%M%SZ").lower()
def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n"); os.replace(tmp, path)
def sha(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda:f.read(16<<20),b""): h.update(b)
    return h.hexdigest()
def run(args, timeout=None, env=None): return subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False,env=env)
def pool(*args): return run(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),*args],env={**os.environ,"PYTHONPATH":str(FACTORY)})
def ssh(cmd, timeout): return run(["ssh","-i",str(KEY),"-o","BatchMode=yes","-o","ServerAliveInterval=20","-o","ServerAliveCountMax=3","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{IP}",cmd],timeout=timeout)
def scp(src, dst, timeout): return run(["scp","-p","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={KNOWN}",src,dst],timeout=timeout)
def update(**changes):
    value=json.loads((PROJECT/"STATUS.json").read_text()); value.update(changes); atomic(PROJECT/"STATUS.json",value)
def binding(): return json.loads((PROJECT/"DIRECTOR_H200_GRAPH_SAFE_BUFFER_DISCRIMINATOR.json").read_text())
def heartbeat(stop, artifact):
    while not stop.wait(45):
        r=pool("heartbeat","--project",NAME); atomic(artifact/"OWNER_HEARTBEAT.json",{"at_utc":now().isoformat(),"returncode":r.returncode,"stdout":r.stdout[-1200:],"stderr":r.stderr[-1200:]})
def contents(artifact, materialization, spend, result):
    return {"schema_version":1,"project":NAME,"result":result,"artifact":str(artifact.relative_to(PROJECT)),"actual_spend_usd":spend,"checkpoint":{"weight":{"sha256":WEIGHT_SHA,"bytes":WEIGHT_BYTES,"materialization":materialization}},"image":IMAGE,"server_state":"No experiment server or worker remains; project immutable weight, pinned image, compiler, and CUDA caches retained.","processes_stopped":True,"next":"Available for a compatible director-selected H200 project."}
def release(artifact, condition, value):
    p=artifact/"BENCH_CONTENTS.json"; atomic(p,value); r=pool("release","--project",NAME,"--condition",condition,"--contents",str(p)); (artifact/"release.stdout").write_text(r.stdout); (artifact/"release.stderr").write_text(r.stderr); return {"condition":condition,"returncode":r.returncode,"released":r.returncode==0,"at_utc":now().isoformat()}

def main():
    b=binding(); ident=b["immutable_identities"]; status=json.loads((PROJECT/"STATUS.json").read_text()); spent_prior=float(status["actual_spend_usd"])
    if status["authorized_spend_usd"] != AUTH or float(status["actual_spend_usd"]) >= AUTH:
        raise RuntimeError("typed_budget_boundary:cumulative_reservation_exhausted")
    reservation=json.loads((LAB/"runtime/spend_cap.json").read_text())["reservations"].get(NAME)
    if not reservation or reservation.get("authorized_usd") != AUTH: raise RuntimeError("typed_budget_boundary:exact_1_25_usd_reservation_missing")
    expected={"grouped_lm_head.py":ident["candidate"]["source_sha256"],"graph_safe_buffer_discriminator.py":ident["candidate"]["discriminator_sha256"]}
    for name,digest in expected.items():
        if sha(PROJECT/name)!=digest: raise RuntimeError(f"typed_binding_boundary:{name}_sha256_mismatch")
    for name in ("inputs/bound/CHECKPOINT_MANIFEST.json","inputs/bound/model.safetensors.index.json"):
        if sha(PROJECT/name)!=ident["model"]["checkpoint_manifest_sha256"] if name.endswith("MANIFEST.json") else sha(PROJECT/name)!=ident["model"]["weight_index_sha256"]: raise RuntimeError(f"typed_binding_boundary:{name}_sha256_mismatch")
    if now()>CLAIM_BY: raise RuntimeError("typed_lifecycle_boundary:claim_deadline_elapsed")
    claim=pool("claim","--project",NAME,"--bench",BENCH,"--lease-seconds","2700")
    if claim.returncode: raise RuntimeError(f"typed_pool_boundary:claim_failed:{claim.stderr[-1000:]}")
    claimed=now(); artifact=PROJECT/"artifacts"/f"graph-safe-buffer-h200-{stamp()}"; artifact.mkdir(parents=True,exist_ok=False)
    (artifact/"claim.stdout").write_text(claim.stdout); (artifact/"claim.stderr").write_text(claim.stderr)
    owner=json.loads((PROJECT/"OWNER_CONTROLLER.json").read_text())
    update(active_session={"artifact_root":str(artifact.relative_to(PROJECT)),"bench_id":BENCH,"deadline_utc":RELEASE_BY.isoformat(),"expected_terminal":"GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json","forward_progress":"claim complete; immutable source and weight staging begins inside durable owner","unit":str(PROJECT/"OWNER_CONTROLLER.json"),"pid":owner["pid"],"start_ticks":owner["start_ticks"],"unit_manager":"pid"})
    stop=threading.Event(); threading.Thread(target=heartbeat,args=(stop,artifact),daemon=True).start(); materialization={}; terminal=None; released=None
    try:
        manifest={"files":[{"name":n,"sha256":sha(PROJECT/n),"bytes":(PROJECT/n).stat().st_size} for n in SOURCE]}; identity=hashlib.sha256(json.dumps(manifest,sort_keys=True,separators=(",",":" )).encode()).hexdigest(); snap=f"{REMOTE}/snapshots/{identity}"
        archive=artifact/"source.tar.gz"; subprocess.run(["tar","-czf",str(archive),"-C",str(PROJECT),*SOURCE],check=True); remote_archive=f"{REMOTE}/source-{identity}.tar.gz.part"
        exists=ssh(f"test -d {shlex.quote(snap)}",30)
        if exists.returncode:
            ssh(f"install -d {shlex.quote(REMOTE+'/snapshots')} && rm -f {shlex.quote(remote_archive)}",120); c=scp(str(archive),f"glmrunner@{IP}:{remote_archive}",600)
            if c.returncode: raise RuntimeError(f"source_copy_failed:{c.stderr[-800:]}")
            r=ssh(f"rm -rf {shlex.quote(snap+'.part')} && mkdir {shlex.quote(snap+'.part')} && tar -xzf {shlex.quote(remote_archive)} -C {shlex.quote(snap+'.part')} && chmod -R a-w {shlex.quote(snap+'.part')} && mv {shlex.quote(snap+'.part')} {shlex.quote(snap)} && rm -f {shlex.quote(remote_archive)}",600)
            if r.returncode: raise RuntimeError(f"source_finalize_failed:{r.stderr[-800:]}")
        source_weight="/home/glmrunner/gemma4-fixed-m384-executor/checkpoint/model-00001-of-00002.safetensors"; project_weight=f"{REMOTE}/immutable/{WEIGHT_SHA}/model-00001-of-00002.safetensors"
        r=ssh(f"sudo install -d -o glmrunner -g glmrunner {shlex.quote(REMOTE+'/immutable/'+WEIGHT_SHA)} && if test -f {shlex.quote(project_weight)}; then true; else sudo ln {shlex.quote(source_weight)} {shlex.quote(project_weight+'.part')} && sudo chmod 0444 {shlex.quote(project_weight+'.part')} && sudo mv {shlex.quote(project_weight+'.part')} {shlex.quote(project_weight)}; fi; stat -c '%d:%i:%s' {shlex.quote(source_weight)} {shlex.quote(project_weight)}; sha256sum {shlex.quote(project_weight)}",1800)
        if r.returncode or WEIGHT_SHA not in r.stdout: raise RuntimeError(f"weight_materialization_failed:{r.stderr[-800:]}")
        lines=r.stdout.splitlines(); materialization={"source":source_weight,"project":project_weight,"stat":lines[:-1],"sha256":WEIGHT_SHA,"method":"verified_hardlink"}; atomic(artifact/"WEIGHT_MATERIALIZATION.json",materialization)
        remote_art=f"{REMOTE}/artifacts/{artifact.name}"; command=f"install -d {shlex.quote(remote_art)} && sudo docker run --rm --gpus all -v {shlex.quote(snap)}:/project:ro -v {shlex.quote(project_weight)}:/weight:ro -v {shlex.quote(remote_art)}:/artifact docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6 bash -lc {shlex.quote('cd /project && PYTHONPATH=. python3 graph_safe_buffer_discriminator.py --weight /weight --artifact-root /artifact --repeats 9')}"
        remaining=max(60,int((RELEASE_BY-now()).total_seconds()-120)); worker=ssh(command,remaining); (artifact/"worker.stdout").write_text(worker.stdout); (artifact/"worker.stderr").write_text(worker.stderr); atomic(artifact/"WORKER.json",{"returncode":worker.returncode,"command":"hash-bound pinned-container discriminator","at_utc":now().isoformat()})
        for name in ("INVOCATION_STATE.json","GRAPH_SAFE_BUFFER_RESULT.json","GRAPH_SAFE_BUFFER_TERMINAL.json"):
            dst=artifact/"retrieved"/name; dst.parent.mkdir(exist_ok=True); got=scp(f"glmrunner@{IP}:{remote_art}/{name}",str(dst),300); atomic(artifact/(name+".retrieval.json"),{"returncode":got.returncode,"stderr":got.stderr[-800:]})
        term_path=artifact/"retrieved/GRAPH_SAFE_BUFFER_TERMINAL.json"; inv_path=artifact/"retrieved/INVOCATION_STATE.json"
        if not term_path.exists(): raise RuntimeError("typed_retrieval_boundary:graph_terminal_missing")
        terminal=json.loads(term_path.read_text()); science=bool(json.loads(inv_path.read_text()).get("scientific_invocation_started")) if inv_path.exists() else False
        if terminal.get("pass"):
            classification="correct_faster" if terminal["timing_ms"]["candidate_median"]<terminal["timing_ms"]["control_median"] else "correct_nonpositive"
        else: classification="semantic_failure" if science else "invalid_pre_science"
        elapsed=(now()-claimed).total_seconds(); spend=min(AUTH,spent_prior+max(0,elapsed)*RATE/3600); final={**terminal,"classification":classification,"science_consumed":science,"provider":{"bench_id":BENCH,"claimed_at_utc":claimed.isoformat(),"completed_at_utc":now().isoformat(),"hourly_rate_usd":RATE,"actual_spend_usd":spend},"artifact_root":str(artifact.relative_to(PROJECT)),"weight_materialization":materialization}
        atomic(PROJECT/"GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",final); update(actual_spend_usd=spend,status="complete",decision=classification,summary=f"One bound graph-safe CUDA replay completed: {classification}.",terminal_artifact="GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",active_session=None)
        released=release(artifact,"ready",contents(artifact,materialization,spend,classification)); final["provider"]["release"]=released; atomic(PROJECT/"GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",final)
    except Exception as error:
        elapsed=(now()-claimed).total_seconds(); spend=min(AUTH,spent_prior+max(0,elapsed)*RATE/3600); boundary={"schema_version":1,"classification":"typed_controller_or_retrieval_boundary","error":f"{type(error).__name__}: {error}","actual_spend_usd":spend,"artifact_root":str(artifact.relative_to(PROJECT)),"science_terminal":terminal}; atomic(PROJECT/"GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",boundary); update(actual_spend_usd=spend,status="complete",decision="typed_controller_or_retrieval_boundary",terminal_artifact="GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",active_session=None); released=release(artifact,"maintenance",contents(artifact,materialization,spend,"typed_controller_or_retrieval_boundary")); boundary["release"]=released; atomic(PROJECT/"GROUPED_LM_HEAD_H200_GRAPH_REPLAY_TERMINAL.json",boundary)
    finally: stop.set()
    return 0 if terminal and terminal.get("pass") else 2
if __name__ == "__main__": raise SystemExit(main())
