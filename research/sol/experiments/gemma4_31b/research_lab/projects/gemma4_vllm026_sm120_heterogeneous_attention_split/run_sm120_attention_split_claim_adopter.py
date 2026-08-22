#!/usr/bin/env python3
"""One director-authorized adopter for the already-claimed attention bench."""
from __future__ import annotations
import argparse, datetime as dt, json, os, subprocess, sys, tempfile, threading, time
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent; LAB=HERE.parents[1]; REPO=HERE.parents[6]
sys.path.insert(0,str(REPO/"research/factory/src"))
from grad_research.gpu_pool import GpuPool
from run_sm120_attention_split_component_owner import deadline_epoch, oracle_terminal, remote, remote_checked, retrieve_generation, sha256, stage_oracle_after_claim

PROJECT="gemma4_vllm026_sm120_heterogeneous_attention_split"; BENCH="rtxpro6000-gemma4-fp8-f4nbtoufbwf66f"
CLAIMED="2026-07-29T08:29:54.858364Z"; OLD_PID=4018491; OLD_TICKS=142981221
EXEC_SHA="b6ebe2a4f4b3dd6c2e5ac7edab83fc40046e354275a3fa0e1bb35fe8253f0fd3"; ORACLE_SHA="b41ef19d7d8b0b6f0522634ea9c5c0753fff48d6b02ac33dea7b002575601842"
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")
def atom(p:Path,v:dict[str,Any]):
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile("w",dir=p.parent,delete=False) as f: json.dump(v,f,indent=2,sort_keys=True);f.write("\n");q=Path(f.name)
    json.loads(q.read_text());os.replace(q,p)
def ticks(pid:int):
    try:return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")",1)[1].split()[19])
    except (FileNotFoundError,IndexError,ValueError):return None
def live(pid:int,start:int):return ticks(pid)==start
class Beat:
    def __init__(self,p):self.p=p;self.stop=threading.Event();self.err=None
    def start(self):self.t=threading.Thread(target=self.run,daemon=True);self.t.start()
    def run(self):
        while not self.stop.wait(40):
            try:
                self.p.heartbeat(PROJECT,bench_id=BENCH);c=self.p.show(BENCH).get("claim") or {}
                if c.get("project")!=PROJECT or c.get("claimed_at")!=CLAIMED:raise RuntimeError("claim generation changed")
            except Exception as e:self.err=e;self.stop.set()
    def check(self):
        if self.err:raise self.err
    def close(self):self.stop.set();self.t.join(5)
def stop_old():
    if not live(OLD_PID,OLD_TICKS):raise RuntimeError("original waiter identity changed")
    os.kill(OLD_PID,15)
    for _ in range(80):
        if not live(OLD_PID,OLD_TICKS):return
        time.sleep(.25)
    raise RuntimeError("original waiter did not exit")
def fence(bind:dict[str,Any],out:Path):
    p=bind["predecessor"];pid=p["server_pid"];start=p["start_ticks"]
    cmd=f"pid={pid}; e={start}; t() {{ awk '{{print $22}}' /proc/$1/stat 2>/dev/null || true; }}; if test -e /proc/$pid; then test \"$(t $pid)\" = \"$e\"; kill -TERM $pid; for n in $(seq 1 30); do test -e /proc/$pid || break; sleep 1; done; fi; test ! -e /proc/$pid; nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader || true"
    r=remote(bind,cmd,timeout=90);(out/"predecessor_fence.stdout").write_bytes(r.stdout);(out/"predecessor_fence.stderr").write_bytes(r.stderr)
    if r.returncode or r.stdout.decode(errors="replace").strip():raise RuntimeError("predecessor/accelerator not quiescent")
def main():
    ap=argparse.ArgumentParser();ap.add_argument("--repair-binding",type=Path,required=True);ap.add_argument("--execution-binding",type=Path,required=True);ap.add_argument("--artifact-root",type=Path,required=True);a=ap.parse_args()
    repair=json.loads(a.repair_binding.read_text());bind=json.loads(a.execution_binding.read_text());root=a.artifact_root.resolve();pool=GpuPool(LAB)
    if repair.get("classification")!="director_same_claim_attention_owner_adopter_repair" or sha256(a.execution_binding)!=EXEC_SHA or repair["scientific_contract"].get("oracle_sha256")!=ORACLE_SHA:raise RuntimeError("immutable repair binding mismatch")
    c=(pool.show(BENCH).get("claim") or {})
    adopted=(root/"CLAIM_ADOPTED.json").is_file()
    if c.get("project")!=PROJECT or c.get("claimed_at")!=CLAIMED or (not adopted and not live(OLD_PID,OLD_TICKS)):raise RuntimeError("exact live claim/waiter unavailable")
    if any(root.glob("**/SM120_ATTENTION_SPLIT_ORACLE.json")):raise RuntimeError("complete oracle artifact already exists")
    pool.heartbeat(PROJECT,bench_id=BENCH);root.mkdir(parents=True,exist_ok=True)
    atom(root/"CLAIM_ADOPTED.json",{"schema_version":1,"phase":"claim_adopted_retry" if adopted else "claim_adopted","claimed_at":CLAIMED,"bench_id":BENCH,"adopter_pid":os.getpid(),"adopter_start_ticks":ticks(os.getpid()),"original_pid":OLD_PID,"original_start_ticks":OLD_TICKS,"at_utc":now()})
    beat=Beat(pool);beat.start();atom(root/"PROGRESS.json",{"phase":"adopted_heartbeat_live","claimed_at":CLAIMED,"at_utc":now()})
    gen=CLAIMED.replace(":","").replace("+","_");local=root/"generations"/gen/f"adopter-{os.getpid()}";local.mkdir(parents=True,exist_ok=True)
    try:
        beat.check();drivers=remote_checked(bind,"pgrep -af '[f]uture_sm120_oracle|[s]m120-attention.*adopter' || true",timeout=30);(local/"REMOTE_DRIVER_CENSUS.txt").write_bytes(drivers)
        if drivers.strip():raise RuntimeError("remote attention-oracle driver already present")
        if not adopted:stop_old()
        atom(root/"PROGRESS.json",{"phase":"original_waiter_stopped","claimed_at":CLAIMED,"at_utc":now()})
        remote_base=f"{bind['remote_root'].rstrip('/')}/generations/{gen}-adopter-{os.getpid()}";staged=stage_oracle_after_claim(bind,remote_base);fence(bind,local);beat.check()
        remote_run=remote_base+"/run"
        cmd=f"{bind['runtime_python']!r} {staged!r} --wheel {bind['runtime_wheel']!r} --model {bind['checkpoint_path']!r} --output {remote_run!r}"
        atom(local/"SUBMISSION.json",{"submission_definition":"one parent all-TRITON then 50-TRITON/10-FLEX","submitted_at_utc":now(),"command":cmd});atom(root/"PROGRESS.json",{"phase":"parent_oracle_submitted","claimed_at":CLAIMED,"at_utc":now()})
        r=remote(bind,cmd,timeout=max(60,int(deadline_epoch(repair['lifecycle']['absolute_release_deadline_utc'])-time.time()-180)));(local/"oracle_parent.stdout").write_bytes(r.stdout);(local/"oracle_parent.stderr").write_bytes(r.stderr)
        got=retrieve_generation(bind,remote_run,local);term=oracle_terminal(local)
        if term is None:raise RuntimeError("incomplete parent oracle terminal; arm evidence preserved")
        final={"schema_version":1,"classification":term["classification"],"claimed_at":CLAIMED,"oracle_returncode":r.returncode,"oracle_terminal":term,"retrieved":got,"component_only":True,"endpoint_c32_executed":False,"completed_at_utc":now()};atom(root/"TERMINAL.json",final);beat.check();pool.release(PROJECT,bench_id=BENCH,expected_claimed_at=CLAIMED,condition="maintenance",contents={"project":PROJECT,"attention_split_terminal":final["classification"],"artifacts":str(root),"server_state":"Runtime/checkpoint/caches retained; predecessor stopped."});return 0 if term["classification"]=="oracle_pass" else 3
    except Exception as e:
        (root/"ADOPTER_EXCEPTION.txt").write_text(repr(e)+"\n");atom(root/"PROGRESS.json",{"phase":"retained_repair","claimed_at":CLAIMED,"error":repr(e),"at_utc":now()});raise
    finally:beat.close()
if __name__=="__main__":raise SystemExit(main())
