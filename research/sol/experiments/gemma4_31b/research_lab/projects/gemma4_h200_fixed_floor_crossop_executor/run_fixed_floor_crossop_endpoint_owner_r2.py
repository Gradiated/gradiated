#!/usr/bin/env python3
"""R2 retained-dispatch owner for one director-bound c32 endpoint pair."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, subprocess, threading, time
P=pathlib.Path(__file__).resolve().parent; LAB=P.parents[1]; ENV={**os.environ,"PYTHONPATH":"/root/workspace/research/factory/src"}; TOOL="/root/workspace/research/factory/tools/repair-handshake"
def atomic(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n"); q.replace(p)
def sha(p):
 h=hashlib.sha256();
 with p.open("rb") as f:
  for b in iter(lambda:f.read(1<<20),b""): h.update(b)
 return h.hexdigest()
def run(a,t,env=ENV): return subprocess.run(a,text=True,capture_output=True,check=False,timeout=t,env=env)
def pool(*a,t=60): return run(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),*a],t)
def now(): return dt.datetime.now(dt.timezone.utc)
def left(deadline,reserve=0): return max(1,int((deadline-now()).total_seconds())-reserve)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--execution-binding",type=pathlib.Path,required=True); ap.add_argument("--owner-state",type=pathlib.Path,required=True); ap.add_argument("--artifact-root",type=pathlib.Path,required=True); a=ap.parse_args()
 bind=json.loads(a.execution_binding.read_text()); packet=json.loads((P/"ENDPOINT_INTEGRATION_PACKET_R2.json").read_text()); deadline=dt.datetime.fromisoformat(bind["absolute_release_deadline_utc"].replace("Z","+00:00")); bench=bind["bench_id"]
 if not bind.get("endpoint_execution_allowed") or bind.get("packet_sha256")!=sha(P/"ENDPOINT_INTEGRATION_PACKET_R2.json"): raise RuntimeError("execution_binding_or_packet_mismatch")
 for n,d in packet["files"].items():
  if sha(P/n)!=d: raise RuntimeError("packet_hash_mismatch:"+n)
 claim=pool("claim","--project",packet["project"],"--bench",bench,"--lease-seconds",str(min(2220,left(deadline))),t=60)
 if claim.returncode: raise RuntimeError("claim_failed:"+claim.stderr[-800:])
 a.artifact_root.mkdir(parents=True,exist_ok=False); atomic(a.artifact_root/"CLAIM.json",{"at_utc":now().isoformat(),"stdout":claim.stdout}); stop=threading.Event()
 def beat():
  while not stop.wait(40):
   r=pool("heartbeat","--project",packet["project"],t=30); atomic(a.artifact_root/"HEARTBEAT.json",{"at_utc":now().isoformat(),"returncode":r.returncode,"stderr":r.stderr[-800:]})
 threading.Thread(target=beat,daemon=True).start()
 terminal=None; terminal_reason=None
 try:
  inv=json.loads(pool("show","--bench",bench,t=30).stdout); r=inv["resource"]
  if r["gpu_uuid"]!=packet["identities"]["gpu_uuid"] or r["ssh_ed25519_fingerprint"]!=packet["identities"]["ssh_fingerprint"]: raise RuntimeError("bench_identity_mismatch")
  key=pathlib.Path(r["ssh_identity_path"]); known=pathlib.Path(r["known_hosts_namespace"])
  if not key.is_file() or not known.is_file(): raise RuntimeError("local_ssh_identity_missing")
  host=f"{r['ssh_user']}@{r['public_ipv4']}"; ssh=["ssh","-i",str(key),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",host]; remote=bind["remote_root"]
  manifest={n:sha(P/n) for n in packet["files"]}; atomic(a.artifact_root/"SOURCE_MANIFEST.json",manifest); archive=a.artifact_root/"packet.tar"; subprocess.run(["tar","-cf",str(archive),"-C",str(P),*manifest],check=True,timeout=120)
  staged=False; output=None; generation=0; scope="stage_and_pair"
  while now()<deadline:
   try:
    if scope=="stage_and_pair" and not staged:
     cp=run(["scp","-i",str(key),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",str(archive),host+":"+remote+"/packet.tar.part"],left(deadline,240))
     if cp.returncode: raise RuntimeError("packet_copy_failed:"+cp.stderr[-800:])
     un=run(ssh+[f"mkdir -p {remote}/project {remote}/artifacts && tar -xf {remote}/packet.tar.part -C {remote}/project && mv {remote}/packet.tar.part {remote}/packet.tar"],left(deadline,210))
     if un.returncode: raise RuntimeError("packet_unpack_failed:"+un.stderr[-800:])
     staged=True
    if scope in {"stage_and_pair","pair_runner_only"}:
     output=f"{remote}/artifacts/{a.artifact_root.name}-g{generation}"; atomic(a.artifact_root/"PROGRESS.json",{"phase":"scientific_pair","generation":generation,"output":output,"at_utc":now().isoformat()})
     w=run(ssh+[f"python3 {remote}/project/run_fixed_floor_crossop_endpoint_pair.py --project {remote}/project --checkpoint {bind['checkpoint_path']} --output {output}"],left(deadline,150)); (a.artifact_root/f"worker-g{generation}.stdout").write_text(w.stdout); (a.artifact_root/f"worker-g{generation}.stderr").write_text(w.stderr)
     if w.returncode: raise RuntimeError("pair_runner_failed")
     scope="retrieval_only"
    if scope=="retrieval_only":
     local=a.artifact_root/f"PAIR_TERMINAL-g{generation}.json"; cp=run(["scp","-i",str(key),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",host+":"+output+"/PAIR_TERMINAL.json",str(local)],left(deadline,100))
     if cp.returncode: raise RuntimeError("pair_terminal_retrieval_failed:"+cp.stderr[-800:])
     pair=json.loads(local.read_text()); required=pair.get("valid") and pair.get("control",{}).get("complete_requests")==32 and pair.get("candidate",{}).get("complete_requests")==32 and pair.get("request_token_ids_exact") and set(pair.get("candidate_local_global_proof",[]))=={"local","global"}
     if not required: terminal={"classification":"decision_bearing_endpoint_negative_or_invalid","pair":pair,"pair_sha256":sha(local),"science_consumed":True}; terminal_reason="pair"; break
     terminal={"classification":"decision_bearing_endpoint_pair","pair":pair,"pair_sha256":sha(local),"science_consumed":True}; terminal_reason="pair"; break
   except Exception as exc:
    diagnostic=a.artifact_root/f"RECOVERABLE_DIAGNOSTIC-g{generation}.json"; atomic(diagnostic,{"generation":generation,"scope":scope,"error":f"{type(exc).__name__}: {exc}","output":output,"candidate_or_endpoint_may_have_started":scope!="stage_and_pair"})
    rid=f"endpoint-r2-{generation}-{int(time.time())}"; ready=run([TOOL,"ready","--root",str(a.artifact_root),"--repair-id",rid,"--deadline",deadline.isoformat(),"--failure-kind","endpoint_recoverable", "--diagnostic",sha(diagnostic),"--retry-scope",scope],30)
    if ready.returncode: terminal={"classification":"unsafe_or_repair_protocol_boundary","diagnostic":str(diagnostic),"stderr":ready.stderr}; terminal_reason="unsafe"; break
    atomic(a.artifact_root/"PROGRESS.json",{"phase":"repair_wait","generation":generation,"repair_id":rid,"scope":scope,"at_utc":now().isoformat()})
    wait=run([TOOL,"wait","--root",str(a.artifact_root),"--repair-id",rid,"--deadline",deadline.isoformat()],left(deadline))
    if wait.returncode or json.loads(wait.stdout).get("state")!="requested": terminal={"classification":"repair_deadline_boundary","diagnostic":str(diagnostic),"wait":wait.stdout[-800:]}; terminal_reason="deadline"; break
    request=a.artifact_root/".repair-handshakes"/rid/"REPAIR_REQUEST.json"; consumed=request.with_name("REPAIR_REQUEST."+sha(request)+".consumed.json"); request.replace(consumed); req=json.loads(consumed.read_text()); scope=req.get("retry_scope")
    if scope not in {"stage_and_pair","pair_runner_only","retrieval_only"}: scope="stage_and_pair"
    generation+=1
  if terminal is None: terminal={"classification":"absolute_deadline_boundary","science_consumed":False}; terminal_reason="deadline"
 finally:
  atomic(a.artifact_root/"TERMINAL.json",terminal or {"classification":"unknown"}); condition="ready" if terminal_reason=="pair" else "maintenance"; contents=a.artifact_root/"RELEASE_CONTENTS.json"; atomic(contents,{"project":packet["project"],"result":(terminal or {}).get("classification"),"artifacts":str(a.artifact_root),"actual_spend_usd":packet["prior_actual_spend_usd"]}); rel=pool("release","--project",packet["project"],"--condition",condition,"--contents",str(contents),t=60); atomic(a.artifact_root/"RELEASE.json",{"condition":condition,"returncode":rel.returncode,"stdout":rel.stdout,"stderr":rel.stderr}); stop.set()
if __name__=="__main__": main()
