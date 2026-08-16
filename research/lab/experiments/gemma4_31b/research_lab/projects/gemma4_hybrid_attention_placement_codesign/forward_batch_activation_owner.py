#!/usr/bin/env python3
from __future__ import annotations
import json, os, pathlib, subprocess, sys, threading, time
ROOT=pathlib.Path(__file__).resolve().parent; LAB=ROOT.parents[1]; ART=ROOT/"artifacts/forward-batch-activation-20260726t0058z"; STATE=ROOT/"FORWARD_BATCH_ACTIVATION_OWNER_STATE.json"
KEY="/root/.config/nebius/glm-campaign/ssh_ed25519"; KNOWN="/root/.config/nebius/glm-campaign/known_hosts"; HOST="89.169.109.132"; REMOTE="/home/glmrunner/phase-selective-full-model-readmission-20260726"; DEADLINE="2026-07-26T01:15:00Z"
def atom(p,v):
 p.parent.mkdir(parents=True,exist_ok=True); q=p.with_suffix(p.suffix+".part"); q.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n"); os.replace(q,p)
def cmd(a): return subprocess.run(a,text=True,capture_output=True)
def ssh(s): return cmd(["ssh","-i",KEY,"-o",f"UserKnownHostsFile={KNOWN}","-o","StrictHostKeyChecking=yes","glmrunner@"+HOST,s])
def beat(stop):
 while not stop.wait(60): cmd([sys.executable,"-m","grad_research.gpu_pool","--lab",str(LAB),"heartbeat","--project","gemma4_hybrid_attention_placement_codesign","--bench","h200-dflash-adapter-e00vyqp7gxsr34wrtz"])
def main():
 ART.mkdir(parents=True,exist_ok=True); stop=threading.Event(); threading.Thread(target=beat,args=(stop,),daemon=True).start()
 atom(STATE,{"phase":"materialize_activation","artifact_root":str(ART),"deadline_utc":DEADLINE,"science_started":False})
 cp=cmd(["scp","-i",KEY,"-o",f"UserKnownHostsFile={KNOWN}","-o","StrictHostKeyChecking=yes",str(ROOT/"forward_batch_activation_component.py"),f"glmrunner@{HOST}:{REMOTE}/source/"])
 (ART/"copy.stdout").write_text(cp.stdout); (ART/"copy.stderr").write_text(cp.stderr)
 if cp.returncode: atom(STATE,{"phase":"repair_ready","failure":"activation_copy_failed","artifact_root":str(ART),"science_started":False}); return 2
 atom(STATE,{"phase":"submit_activation","artifact_root":str(ART),"deadline_utc":DEADLINE,"science_started":True})
 run=ssh(f"set +e; sudo -n docker exec phase-selective-readmission python3 /work/source/forward_batch_activation_component.py; rc=$?; cat {REMOTE}/artifact/forward_batch_dual_cache.json; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json; sudo -n docker logs phase-selective-readmission >{REMOTE}/artifact/forward-batch-activation-c32/server.log 2>&1; exit $rc")
 (ART/"activation.stdout").write_text(run.stdout); (ART/"activation.stderr").write_text(run.stderr)
 retrieved=ssh(f"cat {REMOTE}/artifact/forward_batch_dual_cache.json; cat {REMOTE}/artifact/forward-batch-activation-c32/TERMINAL.json; cat {REMOTE}/artifact/forward-batch-activation-c32/server.log")
 (ART/"retrieved.stdout").write_text(retrieved.stdout); (ART/"retrieved.stderr").write_text(retrieved.stderr)
 atom(STATE,{"phase":"activation_retrieved","artifact_root":str(ART),"deadline_utc":DEADLINE,"science_started":True,"activation_returncode":run.returncode,"retrieval_returncode":retrieved.returncode,"next":"interpret actual ForwardBatch hook and dual-bank component eligibility"})
 return run.returncode
if __name__=="__main__": raise SystemExit(main())
