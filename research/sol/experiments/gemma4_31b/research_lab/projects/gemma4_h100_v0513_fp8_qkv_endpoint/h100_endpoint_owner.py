#!/usr/bin/env python3
"""Claim one registered H100, stage bound bytes atomically, and consume one c32 arm."""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, shlex, subprocess, sys, tarfile, threading, time

PROJECT_NAME="gemma4_h100_v0513_fp8_qkv_endpoint"
PROJECT=pathlib.Path(__file__).resolve().parent
LAB=PROJECT.parent.parent
FACTORY=pathlib.Path("/root/workspace/research/factory/src")
TOOLS=pathlib.Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
KEY=pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN=pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
REMOTE="/home/glmrunner/gemma4-h100-fp8-qkv"

def run(x, **kw): return subprocess.run(x,text=True,**kw)
def pool(*x,check=True): return run([sys.executable,"-m","grad_research.gpu_pool","--lab",str(LAB),*x],env={**os.environ,"PYTHONPATH":str(FACTORY)},capture_output=True,check=check)
def digest(p):
 h=hashlib.sha256()
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1048576),b""): h.update(b)
 return h.hexdigest()
def atomic(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n"); q.replace(p)
def scp(ip,src,dst,timeout):
 r=run(["scp","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={KNOWN}",str(src),f"glmrunner@{ip}:{dst}"],capture_output=True,timeout=timeout)
 if r.returncode: raise RuntimeError(f"typed_transfer_boundary:scp_failed:{src.name}:{r.stderr[-1000:]}")
def retrieve(ip,src,dst,timeout):
 r=run(["scp","-i",str(KEY),"-o","BatchMode=yes","-o","StrictHostKeyChecking=accept-new","-o",f"UserKnownHostsFile={KNOWN}",f"glmrunner@{ip}:{src}",str(dst)],capture_output=True,timeout=timeout)
 if r.returncode: raise RuntimeError(f"typed_retrieval_boundary:scp_failed:{r.stderr[-1000:]}")

def main():
 a=argparse.ArgumentParser(); a.add_argument("--artifact-root",type=pathlib.Path,required=True); a.add_argument("--absolute-deadline-epoch",type=int,required=True); a.add_argument("--resume-preinvocation-repair",action="store_true"); ns=a.parse_args()
 if ns.absolute_deadline_epoch-time.time()<900: raise RuntimeError("typed_budget_boundary:deadline_too_short")
 b=json.loads((PROJECT/"BINDINGS.json").read_text())
 sources=[PROJECT/"inputs"/x for x in ("proven_v0513_endpoint_entrypoint.py","proven_v0513_paired_endpoint_runner.py","fp8_qkv_paired_runner.py","stack_sitecustomize.py","install_endpoint_patch.py","qkv_epilogue_discriminator.py")]
 if any(digest(p)!=b["source_bytes"][k]["sha256"] for p,k in zip(sources,("endpoint_entrypoint","paired_runner","qkv_runner","qkv_sitecustomize","qkv_installer","qkv_discriminator"))): raise RuntimeError("typed_binding_boundary:project_local_input_hash_mismatch")
 ns.artifact_root.mkdir(parents=True,exist_ok=ns.resume_preinvocation_repair); events=ns.artifact_root/"outer-events.jsonl"; started=time.time(); claimed=False; terminal=None; stop=threading.Event(); rate=0.0
 def emit(event,**v):
  with events.open("a") as f:f.write(json.dumps({"time":time.time(),"event":event,**v},sort_keys=True)+"\n")
 def beat():
  while not stop.wait(45):
   r=pool("heartbeat","--project",PROJECT_NAME,check=False); emit("heartbeat",returncode=r.returncode,stderr=r.stderr[-1000:])
 try:
  inventory=json.loads((LAB/"runtime/gpus.json").read_text())["benches"]
  rows=inventory.values() if isinstance(inventory,dict) else inventory
  retained=next((x for x in rows if (x.get("claim") or {}).get("project")==PROJECT_NAME),None)
  if ns.resume_preinvocation_repair and retained is not None:
   claimed=True; bench=retained; emit("resumed_retained_claim",bench_id=bench["id"])
  else:
   claim=pool("claim","--project",PROJECT_NAME,"--accelerator","nvidia-h100-sxm","--lease-seconds",str(max(600,int(ns.absolute_deadline_epoch-time.time()))))
   claimed=True; bench=json.loads(claim.stdout); emit("claimed",bench=bench)
   bench=inventory[bench["id"]] if isinstance(inventory,dict) else next(x for x in inventory if x["id"]==bench["id"])
  threading.Thread(target=beat,daemon=True).start()
  rate=float(bench["hourly_cost_usd"])
  sys.path.insert(0,str(TOOLS)); from placement_control import extract_public_ipv4,get_instance; from stock_control import run_ssh
  ip=extract_public_ipv4(get_instance(bench["resource"]["instance_id"]))
  if not ip: raise RuntimeError("typed_provider_boundary:no_public_ip")
  run(["ssh-keygen","-R",ip,"-f",str(KNOWN)],capture_output=True)
  r=run_ssh(ip,KEY,"hostname; nvidia-smi --query-gpu=name,uuid --format=csv,noheader; sudo docker --version",timeout=60); (ns.artifact_root/"remote-identity.stdout").write_text(r.stdout); (ns.artifact_root/"remote-identity.stderr").write_text(r.stderr)
  if r.returncode or "H100" not in r.stdout: raise RuntimeError("typed_hardware_boundary:h100_identity_failed")
  r=run_ssh(ip,KEY,f"mkdir -p {REMOTE}/input {REMOTE}/checkpoint {REMOTE}/artifacts",timeout=60)
  if r.returncode: raise RuntimeError("typed_remote_boundary:prepare_failed")
  for p in [*sources,PROJECT/"remote_h100_qkv_endpoint.sh",PROJECT/"checkpoint_transfer_controller.py",PROJECT/"CHECKPOINT_MANIFEST.json",PROJECT/"CHECKPOINT_SOURCE_BINDING.json",PROJECT/"BINDINGS.json"]:
   want=digest(p); final=f"{REMOTE}/input/{p.name}"; check=run_ssh(ip,KEY,f"test -f {shlex.quote(final)} && test \"$(sha256sum {shlex.quote(final)}|awk '{{print $1}}')\" = {want}",timeout=60)
   if check.returncode:
    part=f"{REMOTE}/input/.{p.name}.{want}.part"; scp(ip,p,part,300); r=run_ssh(ip,KEY,f"test \"$(sha256sum {shlex.quote(part)}|awk '{{print $1}}')\" = {want} && mv -f {shlex.quote(part)} {shlex.quote(final)}",timeout=120)
    if r.returncode: raise RuntimeError(f"typed_transfer_boundary:finalize_failed:{p.name}")
  stage=[sys.executable,str(PROJECT/"checkpoint_transfer_controller.py"),"--ip",ip,"--remote-root",REMOTE,"--artifact-root",str(ns.artifact_root/"checkpoint-transfer")]
  r=run(stage,capture_output=True,timeout=max(900,int(ns.absolute_deadline_epoch-time.time()-300))); (ns.artifact_root/"checkpoint-stage.stdout").write_text(r.stdout); (ns.artifact_root/"checkpoint-stage.stderr").write_text(r.stderr)
  if r.returncode: raise RuntimeError("typed_staging_boundary:checkpoint_transfer_failed")
  worker_timeout=max(60,int(ns.absolute_deadline_epoch-time.time()-300)); r=run_ssh(ip,KEY,f"timeout --signal=TERM {worker_timeout} bash {REMOTE}/input/remote_h100_qkv_endpoint.sh",timeout=worker_timeout+30); (ns.artifact_root/"remote-worker.stdout").write_text(r.stdout); (ns.artifact_root/"remote-worker.stderr").write_text(r.stderr)
  for remote,local in (("artifacts/INVOCATION_STATE.json","INVOCATION_STATE.json"),("artifacts/WORKER_TERMINAL.json","REMOTE_WORKER_TERMINAL.json"),("compact.tar.gz.sha256","compact.tar.gz.sha256")):
   q=run_ssh(ip,KEY,f"cat {REMOTE}/{remote}",timeout=60); (ns.artifact_root/local).write_text(q.stdout)
  retrieve(ip,f"{REMOTE}/compact.tar.gz",ns.artifact_root/"compact.tar.gz",600)
  if digest(ns.artifact_root/"compact.tar.gz") != (ns.artifact_root/"compact.tar.gz.sha256").read_text().split()[0]: raise RuntimeError("typed_retrieval_boundary:compact_hash_mismatch")
  term=json.loads((ns.artifact_root/"REMOTE_WORKER_TERMINAL.json").read_text()); state=json.loads((ns.artifact_root/"INVOCATION_STATE.json").read_text())
  if term.get("classification")=="integration_failure" and not state.get("candidate_science_started",False):
   repair_deadline=ns.absolute_deadline_epoch-300
   atomic(ns.artifact_root/"REPAIR_READY.json",{"worker_terminal":term,"invocation_state":state,"repair_deadline_epoch":repair_deadline})
   request=ns.artifact_root/"REPAIR_REQUEST.json"
   while time.time()<repair_deadline and not request.is_file(): time.sleep(5)
   if request.is_file() and json.loads(request.read_text()).get("retry") is True:
    retry_timeout=max(60,int(ns.absolute_deadline_epoch-time.time()-300))
    retry=run_ssh(ip,KEY,f"timeout --signal=TERM {retry_timeout} bash {REMOTE}/input/remote_h100_qkv_endpoint.sh",timeout=retry_timeout+30)
    (ns.artifact_root/"remote-worker-retry.stdout").write_text(retry.stdout); (ns.artifact_root/"remote-worker-retry.stderr").write_text(retry.stderr)
    for remote,local in (("artifacts/INVOCATION_STATE.json","INVOCATION_STATE.json"),("artifacts/WORKER_TERMINAL.json","REMOTE_WORKER_TERMINAL.json"),("compact.tar.gz.sha256","compact.tar.gz.sha256")):
     q=run_ssh(ip,KEY,f"cat {REMOTE}/{remote}",timeout=60); (ns.artifact_root/local).write_text(q.stdout)
    retrieve(ip,f"{REMOTE}/compact.tar.gz",ns.artifact_root/"compact.tar.gz",600)
    if digest(ns.artifact_root/"compact.tar.gz") != (ns.artifact_root/"compact.tar.gz.sha256").read_text().split()[0]: raise RuntimeError("typed_retrieval_boundary:compact_retry_hash_mismatch")
    term=json.loads((ns.artifact_root/"REMOTE_WORKER_TERMINAL.json").read_text()); state=json.loads((ns.artifact_root/"INVOCATION_STATE.json").read_text())
   else:
    raise RuntimeError("typed_repair_boundary:repair_deadline_or_request_absent")
  extracted=ns.artifact_root/"retrieved"; extracted.mkdir()
  with tarfile.open(ns.artifact_root/"compact.tar.gz","r:gz") as x: x.extractall(extracted,filter="data")
  exact=json.loads((extracted/"exact-c32/TERMINAL.json").read_text())
  service=exact.get("service_seconds_per_request")
  valid=term.get("classification")=="completed" and isinstance(service,(int,float)) and service<=b["economics"]["maximum_seconds_per_request"]
  terminal={"schema_version":1,"status":"terminal","classification":"endpoint_useful" if valid else "endpoint_negative","pass":valid,"service_seconds_per_request":service,"economic_ceiling_seconds_per_request":b["economics"]["maximum_seconds_per_request"],"invocation_state":state,"provider_exposure_seconds":time.time()-started,"provider_spend_usd":(time.time()-started)*rate/3600}
  atomic(ns.artifact_root/"TERMINAL.json",terminal); return 0 if terminal["pass"] else 1
 except Exception as e:
  state_path=ns.artifact_root/"INVOCATION_STATE.json"
  state=json.loads(state_path.read_text()) if state_path.is_file() else {}
  if claimed and not state.get("candidate_science_started",False):
   repair_deadline=ns.absolute_deadline_epoch-300
   atomic(ns.artifact_root/"REPAIR_READY.json",{"error":{"type":type(e).__name__,"message":str(e)},"invocation_state":state,"repair_deadline_epoch":repair_deadline})
   request=ns.artifact_root/"REPAIR_REQUEST.json"
   while time.time()<repair_deadline and not request.is_file(): time.sleep(5)
   if request.is_file() and json.loads(request.read_text()).get("retry") is True:
    os.execv(sys.executable,[sys.executable,str(pathlib.Path(__file__).resolve()),"--resume-preinvocation-repair","--artifact-root",str(ns.artifact_root),"--absolute-deadline-epoch",str(ns.absolute_deadline_epoch)])
  terminal={"schema_version":1,"status":"terminal","classification":"owner_failure","pass":False,"error":{"type":type(e).__name__,"message":str(e)},"provider_exposure_seconds":time.time()-started if claimed else 0}; terminal["provider_spend_usd"]=terminal["provider_exposure_seconds"]*rate/3600; atomic(ns.artifact_root/"TERMINAL.json",terminal); emit("outer_error",error=terminal["error"]); return 1
 finally:
  stop.set()
  if claimed:
   contents={"project":PROJECT_NAME,"model":"google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4","checkpoint":f"Exact checkpoint retained at {REMOTE}/checkpoint.","image":"Pinned SGLang v0.5.13 image retained if pulled.","runtime":f"H100 FP8+QKV terminal: {(terminal or {}).get('classification','owner_failure')}.","caches":"FP8/QKV/CUDA graph caches retained.","server_state":"Healthy final server retained if present.","artifacts":"Compact terminal and raw worker stdout/stderr retained project-locally."}; atomic(ns.artifact_root/"BENCH_CONTENTS.json",contents); pool("release","--project",PROJECT_NAME,"--condition","maintenance" if (terminal or {}).get("classification")=="owner_failure" else "ready","--contents",str(ns.artifact_root/"BENCH_CONTENTS.json"),check=False)
if __name__=="__main__": raise SystemExit(main())
