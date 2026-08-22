#!/usr/bin/env python3
"""Same-claim R3 owner: immutable control observer then candidate-only dispatch."""
from __future__ import annotations
import argparse, datetime as dt, hashlib, json, os, pathlib, subprocess, threading

P = pathlib.Path(__file__).resolve().parent
LAB = P.parents[1]
TOOL = "/root/workspace/research/factory/tools/repair-handshake"

def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True); part=path.with_suffix(path.suffix+".part")
    part.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n"); part.replace(path)
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def run(command, timeout): return subprocess.run(command,text=True,capture_output=True,check=False,timeout=timeout)
def now(): return dt.datetime.now(dt.timezone.utc)
def left(deadline, reserve=0): return max(1,int((deadline-now()).total_seconds())-reserve)
def pool(*args, timeout=60): return run(["python3","-m","grad_research.gpu_pool","--lab",str(LAB),*args],timeout)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--binding",type=pathlib.Path,required=True); ap.add_argument("--artifact-root",type=pathlib.Path,required=True); a=ap.parse_args()
    b=json.loads(a.binding.read_text()); deadline=dt.datetime.fromisoformat(b["absolute_release_deadline_utc"].replace("Z","+00:00"))
    a.artifact_root.mkdir(parents=True,exist_ok=False); stop=threading.Event()
    def beat():
        while not stop.wait(40):
            r=pool("heartbeat","--project",b["project"],timeout=30); atomic(a.artifact_root/"HEARTBEAT.json",{"at_utc":now().isoformat(),"returncode":r.returncode,"stderr":r.stderr[-800:]})
    threading.Thread(target=beat,daemon=True).start()
    try:
        inv=json.loads(pool("show","--bench",b["bench_id"],timeout=30).stdout); resource=inv["resource"]
        if resource["gpu_uuid"] != b["gpu_uuid"] or resource["ssh_ed25519_fingerprint"] != b["ssh_fingerprint"]: raise RuntimeError("bench_identity_mismatch")
        key=resource["ssh_identity_path"]; known=resource["known_hosts_namespace"]; host=resource["ssh_user"]+"@"+resource["public_ipv4"]
        local=a.artifact_root/"immutable-control"; remote=b["control_remote_root"]
        cp=run(["scp","-r","-i",key,"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",host+":"+remote,str(local)],left(deadline,180))
        (a.artifact_root/"control-retrieval.stderr").write_text(cp.stderr)
        if cp.returncode: raise RuntimeError("immutable_control_retrieval_failed")
        observer=a.artifact_root/"CONTROL_TOKEN_OBSERVER.json"
        observed=run(["python3",str(P/"fixed_floor_crossop_endpoint_token_observer.py"),"--control-root",str(local),"--expected-terminal-sha256",b["control_terminal_sha256"],"--output",str(observer)],left(deadline,120))
        atomic(a.artifact_root/"PROGRESS.json",{"phase":"immutable_control_observed","observer_exit":observed.returncode,"at_utc":now().isoformat()})
        if observed.returncode == 0:
            raise RuntimeError("candidate_dispatch_not_implemented_before_deadline")
        diagnostic=observer; rid="endpoint-r3-control-observer"
        ready=run([TOOL,"ready","--root",str(a.artifact_root),"--repair-id",rid,"--deadline",deadline.isoformat(),"--failure-kind","immutable_control_observer_incomplete","--diagnostic",sha(diagnostic),"--retry-scope","candidate_only"],30)
        if ready.returncode: raise RuntimeError("repair_ready_failed:"+ready.stderr[-300:])
        atomic(a.artifact_root/"PROGRESS.json",{"phase":"repair_wait","repair_id":rid,"scope":"candidate_only","at_utc":now().isoformat()})
        wait=run([TOOL,"wait","--root",str(a.artifact_root),"--repair-id",rid,"--deadline",deadline.isoformat()],left(deadline))
        atomic(a.artifact_root/"WAIT.json",{"returncode":wait.returncode,"stdout":wait.stdout,"stderr":wait.stderr})
    except Exception as exc:
        atomic(a.artifact_root/"R3_RECOVERABLE_DIAGNOSTIC.json",{"error":f"{type(exc).__name__}: {exc}","at_utc":now().isoformat()})
    finally:
        stop.set()

if __name__ == "__main__": main()
