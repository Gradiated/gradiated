#!/usr/bin/env python3
"""Durable cold-H200 R5 bootstrap owner; all mutable guest work stays under one claim."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, pathlib, subprocess, threading, time

PROJECT=pathlib.Path(__file__).resolve().parent
LAB=PROJECT.parents[1]
REPAIR="/root/workspace/research/factory/tools/repair-handshake"
ENV={**__import__("os").environ,"PYTHONPATH":"/root/workspace/research/factory/src"}

def now(): return dt.datetime.now(dt.UTC)
def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n"); q.replace(p)
def call(c,t): return subprocess.run(c,text=True,capture_output=True,check=False,timeout=max(1,t),env=ENV)
def left(deadline,reserve=0): return max(1,int((deadline-now()).total_seconds())-reserve)
def require(ok,label):
 if not ok: raise RuntimeError(label)

def reconcile(ssh, entries, deadline, root):
 """Copy only missing/mismatched immutable bytes to .part, verify, then rename."""
 rows=[]
 for entry in entries:
  source=pathlib.Path(entry["source"]); dest=entry["destination"]; digest=entry["sha256"]
  require(sha(source)==digest,"local_manifest_hash:"+source.name)
  probe=call([*ssh,"test -f "+dest+" && sha256sum "+dest+" | awk '{print $1}' || true"],left(deadline,300))
  if probe.returncode==0 and probe.stdout.strip()==digest:
   rows.append({"destination":dest,"sha256":digest,"action":"reused"}); continue
  parent=str(pathlib.PurePosixPath(dest).parent)
  require(call([*ssh,"mkdir -p "+parent],left(deadline,300)).returncode==0,"remote_mkdir")
  scp=["scp",*ssh[1:-1],str(source),ssh[-1]+":"+dest+".part"]
  require(call(scp,left(deadline,300)).returncode==0,"immutable_copy")
  verify=call([*ssh,"sha256sum "+dest+".part | awk '{print $1}'"],left(deadline,300))
  require(verify.returncode==0 and verify.stdout.strip()==digest,"remote_manifest_hash")
  require(call([*ssh,"mv "+dest+".part "+dest],left(deadline,300)).returncode==0,"atomic_finalize")
  rows.append({"destination":dest,"sha256":digest,"action":"copied"})
 put(root/"STAGING_MANIFEST.json",{"schema_version":1,"entries":rows,"at_utc":now().isoformat()})

def main():
 p=argparse.ArgumentParser(); p.add_argument("--binding",type=pathlib.Path,required=True);p.add_argument("--artifact-root",type=pathlib.Path,required=True);p.add_argument("--ready-file",type=pathlib.Path,required=True);a=p.parse_args()
 b=json.loads(a.binding.read_text()); root=a.artifact_root; root.mkdir(parents=True,exist_ok=True)
 require(b.get("claim_allowed"),"fresh_execution_binding_required")
 deadline=dt.datetime.fromisoformat(b["absolute_release_deadline_utc"].replace("Z","+00:00"))
 show=call(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),"show","--bench",b["bench_id"]],30); require(show.returncode==0,"pool_show")
 row=json.loads(show.stdout); resource=row["resource"]; contents=row.get("contents",{}); accel=contents.get("accelerator_identity",{})
 require(row.get("claim",{}).get("claimed_at")==b["claimed_at"],"claim_generation")
 require((resource.get("gpu_uuid") or accel.get("gpu_uuid"))==b["gpu_uuid"],"gpu_identity")
 require((resource.get("ssh_ed25519_fingerprint") or contents.get("ssh_ed25519_fingerprint"))==b["ssh_fingerprint"],"ssh_identity")
 require(row["lifecycle"]["watchdog"]["main_pid"]==b["watchdog_main_pid"],"watchdog_identity")
 host=resource["ssh_user"]+"@"+resource["public_ipv4"]; ssh=["ssh","-i",resource["ssh_identity_path"],"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o","UserKnownHostsFile="+resource["known_hosts_namespace"],host]
 stop=threading.Event()
 def heartbeat():
  while not stop.wait(30):
   r=call(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),"heartbeat","--project",b["project"]],30); put(root/"HEARTBEAT.json",{"at_utc":now().isoformat(),"rc":r.returncode,"stderr":r.stderr[-400:]})
 threading.Thread(target=heartbeat,daemon=True).start()
 terminal=None
 try:
  reconcile(ssh,b["immutable_manifests"]["files"],deadline,root)
  image=b["immutable_manifests"]["image"]
  probe=call([*ssh,"sudo -n docker image inspect "+image+" >/dev/null 2>&1 || sudo -n docker pull "+image],left(deadline,600))
  require(probe.returncode==0,"image_reconcile")
  put(a.ready_file,{"phase":"cold_inputs_reconciled","claimed_at":b["claimed_at"],"at_utc":now().isoformat()})
  generation=0
  while now()<deadline:
   output=b["remote_root"]+"/artifacts/candidate-r5-cold-g"+str(generation)
   worker=call([*ssh,"python3 "+b["remote_project"]+"/run_fixed_floor_crossop_endpoint_candidate_only_r5.py --project "+b["remote_project"]+" --checkpoint "+b["checkpoint_path"]+" --oracle "+b["oracle_path"]+" --output "+output],left(deadline,180))
   put(root/f"worker-g{generation}.json",{"returncode":worker.returncode,"stdout":worker.stdout[-4000:],"stderr":worker.stderr[-4000:],"output":output})
   local=root/f"PAIR_TERMINAL-candidate-g{generation}.json"
   get=call(["scp",*ssh[1:-1],host+":"+output+"/PAIR_TERMINAL.json",str(local)],left(deadline,90))
   if worker.returncode==0 and get.returncode==0:
    pair=json.loads(local.read_text()); rows=pair.get("candidate",{}).get("rows",[])
    if pair.get("candidate",{}).get("complete_requests")==32 and len(rows)==32:
     terminal={"classification":"decision_bearing_candidate_only_endpoint","science_consumed":True,"pair_sha256":sha(local)};break
   diagnostic=root/f"RECOVERABLE_DIAGNOSTIC-g{generation}.json"; put(diagnostic,{"classification":"recoverable_cold_consumer_failure","generation":generation,"worker_returncode":worker.returncode,"retrieval_returncode":get.returncode,"science_consumed":False})
   rid="cold-r5-"+str(generation)+"-"+str(int(time.time()))
   ready=call([REPAIR,"ready","--root",str(root),"--repair-id",rid,"--deadline",deadline.isoformat(),"--failure-kind","candidate_only_recoverable","--diagnostic",sha(diagnostic),"--retry-scope","candidate_only"],30)
   if ready.returncode: raise RuntimeError("repair_ready")
   waited=call([REPAIR,"wait","--root",str(root),"--repair-id",rid,"--deadline",deadline.isoformat()],left(deadline))
   if waited.returncode or json.loads(waited.stdout).get("state")!="requested": break
   req=root/".repair-handshakes"/rid/"REPAIR_REQUEST.json"; req.replace(req.with_name("REPAIR_REQUEST."+sha(req)+".consumed.json")); generation+=1
  if terminal is None: terminal={"classification":"cold_owner_deadline_boundary","science_consumed":False}
 finally:
  stop.set(); put(root/"TERMINAL.json",terminal or {"classification":"unknown","science_consumed":False})
  condition="ready" if terminal and terminal["classification"]=="decision_bearing_candidate_only_endpoint" else "maintenance"
  call(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),"release","--project",b["project"],"--bench",b["bench_id"],"--expected-claimed-at",b["claimed_at"],"--condition",condition],60)
if __name__=="__main__": main()
