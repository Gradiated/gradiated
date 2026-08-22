#!/usr/bin/env python3
"""Only future claim seam for the cold R5 owner."""
from __future__ import annotations
import argparse,json,pathlib,subprocess,sys
PROJECT=pathlib.Path(__file__).resolve().parent; LAB=PROJECT.parents[1]; POOL=["python3","-m","grad_research.gpu_pool","--lab",str(LAB)]; DETACHED="/root/workspace/research/factory/tools/detached-owner"
def put(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+".part");q.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n");q.replace(p)
def run(c,t=60):
 r=subprocess.run(c,text=True,capture_output=True,timeout=t)
 if r.returncode: raise RuntimeError(r.stderr[-600:] or r.stdout[-600:])
 return r.stdout
def main():
 p=argparse.ArgumentParser();p.add_argument("--execution-spec",type=pathlib.Path,required=True);p.add_argument("--artifact-root",type=pathlib.Path,required=True);p.add_argument("--detached-owner",default=DETACHED);a=p.parse_args()
 spec=json.loads(a.execution_spec.read_text())
 if not spec.get("claim_allowed"): raise RuntimeError("fresh_director_execution_binding_required")
 run([*POOL,"claim","--project",spec["project"],"--bench",spec["bench_id"]])
 row=json.loads(run([*POOL,"show","--bench",spec["bench_id"]]))
 claim=row.get("claim") or {}; res=row["resource"]; contents=row.get("contents",{}); accel=contents.get("accelerator_identity",{})
 if claim.get("claimed_at") is None: raise RuntimeError("claim_not_observed")
 binding={**spec,"claimed_at":claim["claimed_at"],"gpu_uuid":res.get("gpu_uuid") or accel.get("gpu_uuid"),"ssh_fingerprint":res.get("ssh_ed25519_fingerprint") or contents.get("ssh_ed25519_fingerprint"),"watchdog_main_pid":row["lifecycle"]["watchdog"]["main_pid"]}
 root=a.artifact_root.resolve(); derived=root/"COLD_R5_EXECUTION_BINDING.json";ready=root/"OWNER_READY.json";state=root/"OWNER_STATE.json";log=root/"OWNER.log";put(derived,binding)
 launched=json.loads(run([a.detached_owner,"start","--unit-manager","pid","--state",str(state),"--log",str(log),"--cwd",str(PROJECT),"--ready-file",str(ready),"--stabilize-seconds","30","--",sys.executable,str(PROJECT/"run_fixed_floor_crossop_endpoint_cold_owner_r5.py"),"--binding",str(derived),"--artifact-root",str(root),"--ready-file",str(ready)],45))
 if not launched.get("live") or not launched.get("ready"): raise RuntimeError("owner_not_ready")
 status=PROJECT/"STATUS.json";record=json.loads(status.read_text());record["active_session"]={"artifact_root":str(root),"deadline_utc":binding["absolute_release_deadline_utc"],"expected_terminal":"PAIR_TERMINAL.json","forward_progress":"cold owner reconciled immutable manifests and entered candidate-only dispatch","pid":launched["pid"],"start_ticks":launched["start_ticks"],"unit":str(state),"unit_manager":"pid"};put(status,record)
 print(json.dumps({"binding":str(derived),"pid":launched["pid"],"start_ticks":launched["start_ticks"]},sort_keys=True))
if __name__=="__main__": main()
