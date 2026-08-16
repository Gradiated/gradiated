#!/usr/bin/env python3
"""One bounded claim/heartbeat/release owner for the already-produced KV8 overlay."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, subprocess, sys, tarfile, threading, time

PROJECT="gemma4_h200_local_kv_head8_discriminator"; BENCH="h200-local-kv8-e00tnyt66qqx2n7qqg"; INSTANCE="computeinstance-e00tnyt66qqx2n7qqg"
LAB=pathlib.Path("/root/workspace/research/lab/experiments/gemma4_31b/research_lab"); ROOT=LAB/"projects"/PROJECT; P=ROOT/"phase2"; FACTORY=pathlib.Path("/root/workspace/research/factory/src"); TOOLS=pathlib.Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius"); KEY=pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
REMOTE="/home/glmrunner/gemma-local-kv8"; RUN="local-kv8-consumer-resume-20260719t1500"; OVERLAY="e29faa6768d22aa6cae56bb15253d02f6af0aca2abdd6d4f0092a436cea05780"
FILES=("remote_consumer_resume.sh","patch/model_config.py","patch/gemma4_causal.py","patch/gemma4_mm.py","bound_sources/coherence_runner.py","bound_sources/retrieval_10k_runner.py","bound_sources/exact_mix_runner.py")
def run(c,**k): return subprocess.run(c,capture_output=True,text=True,**k)
def pool(*a): return run([sys.executable,"-m","grad_research.gpu_pool","--lab",str(LAB),*a],env={**os.environ,"PYTHONPATH":str(FACTORY)})
def digest(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(8<<20),b""): h.update(b)
 return h.hexdigest()
def atomic(p,x):
 q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n");q.replace(p)
def ssh(ip,cmd,t): return run(["ssh","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new",f"glmrunner@{ip}",cmd],timeout=t)
def scp(ip,src,dst,t): return run(["scp","-i",str(KEY),"-o","BatchMode=yes",*map(str,src),f"glmrunner@{ip}:{dst}"],timeout=t)
def get(ip,src,dst,t): return run(["scp","-i",str(KEY),"-o","BatchMode=yes",f"glmrunner@{ip}:{src}",str(dst)],timeout=t)
def main():
 ap=argparse.ArgumentParser();ap.add_argument("--artifact-root",type=pathlib.Path,required=True);ap.add_argument("--deadline-epoch",type=int,required=True);a=ap.parse_args();a.artifact_root.mkdir(parents=True,exist_ok=False);events=a.artifact_root/"outer-events.jsonl"
 def emit(e,**x):
  with events.open("a") as f:f.write(json.dumps({"time":time.time(),"event":e,**x},sort_keys=True)+"\n")
 claimed=False; stop=threading.Event(); terminal=None; condition="ready"; start=time.time()
 def beat():
  while not stop.wait(45):
   r=pool("heartbeat","--project",PROJECT);emit("heartbeat",returncode=r.returncode,stderr=r.stderr[-600:])
 try:
  c=pool("claim","--project",PROJECT,"--bench",BENCH,"--lease-seconds","600");
  if c.returncode: raise RuntimeError("claim_failed:"+c.stderr)
  claimed=True;emit("claimed",stdout=c.stdout);threading.Thread(target=beat,daemon=True).start()
  sys.path.insert(0,str(TOOLS));from placement_control import extract_public_ipv4,get_instance
  ip=extract_public_ipv4(get_instance(INSTANCE));
  if not ip: condition="maintenance";raise RuntimeError("typed_provider_boundary:no_public_ip")
  check=ssh(ip,f"set -eu; test \"$(sha256sum {REMOTE}/local-kv8-conversion-20260719t-phase2/distillation/overlay.safetensors | awk '{{print $1}}')\" = {OVERLAY}; test -f {REMOTE}/checkpoint/config.json; sudo docker image inspect docker.io/lmsysorg/sglang@sha256:015f39a45844be5a7b35270c56dc4d9ebcfe9b0c21a3b4f877a4ee22e795bd7a >/dev/null; mkdir -p {REMOTE}/phase2-consumer-bound",120);(a.artifact_root/"resident-check.stdout").write_text(check.stdout);(a.artifact_root/"resident-check.stderr").write_text(check.stderr)
  if check.returncode: condition="maintenance";raise RuntimeError("typed_resident_boundary:overlay_checkpoint_or_image")
  sources=[P/x for x in FILES];r=scp(ip,sources,f"{REMOTE}/phase2-consumer-bound/",300);(a.artifact_root/"consumer-patch-transfer.stderr").write_text(r.stderr)
  if r.returncode:raise RuntimeError("typed_staging_boundary:consumer_patch_transfer")
  r=ssh(ip,f"DEADLINE_EPOCH={a.deadline_epoch} bash {REMOTE}/phase2-consumer-bound/remote_consumer_resume.sh",max(60,a.deadline_epoch-int(time.time())+60));(a.artifact_root/"remote-worker.stdout").write_text(r.stdout);(a.artifact_root/"remote-worker.stderr").write_text(r.stderr);emit("worker_finished",returncode=r.returncode)
  if r.returncode not in (0,):raise RuntimeError("typed_remote_boundary:consumer_exit_"+str(r.returncode))
  arc=a.artifact_root/f"{RUN}.tar.gz";side=a.artifact_root/f"{RUN}.tar.gz.sha256";r=get(ip,f"{REMOTE}/{RUN}.tar.gz",arc,900)
  if r.returncode:raise RuntimeError("typed_retrieval_boundary:archive")
  r=get(ip,f"{REMOTE}/{RUN}.tar.gz.sha256",side,120)
  if r.returncode or digest(arc)!=side.read_text().split()[0]:raise RuntimeError("typed_retrieval_boundary:archive_hash")
  with tarfile.open(arc,"r:gz") as t:t.extractall(a.artifact_root,filter="data")
  terminal=json.loads((a.artifact_root/RUN/"OWNER_TERMINAL.json").read_text());emit("terminal_retrieved",terminal=terminal)
 except Exception as e:
  emit("outer_error",message=str(e));atomic(a.artifact_root/"FAILURE.json",{"type":str(e),"timestamp":time.time()})
 finally:
  stop.set()
  if claimed:
   contents={"project":PROJECT,"model":"google/gemma-4-31B-it local-KV8 with global-KV4","checkpoint":"Exact immutable eight-file checkpoint retained remotely.","image":"Pinned SGLang v0.5.12 image retained.","runtime":"Consumer-only resume after the one completed 24-update producer: "+str((terminal or {}).get("classification","typed_boundary")),"caches":"Conversion/server compilation caches retained.","server_state":"Converted server retained if healthy.","export":"Remote overlay e29faa6768d22aa6cae56bb15253d02f6af0aca2abdd6d4f0092a436cea05780 retained remotely; bulk local copy deferred."};cp=a.artifact_root/"BENCH_CONTENTS.json";atomic(cp,contents);rel=pool("release","--project",PROJECT,"--condition",condition,"--contents",str(cp));emit("released",returncode=rel.returncode,condition=condition)
  atomic(a.artifact_root/"SPEND.json",{"prior_project_cost_usd":3.22,"claim_seconds":max(0,time.time()-start) if claimed else 0,"claim_cost_usd_at_2_46_per_hour":max(0,time.time()-start)*2.46/3600 if claimed else 0,"authorized_cumulative_usd":18.0})
if __name__=="__main__":main()
