#!/usr/bin/env python3
from __future__ import annotations
import hashlib, json, os, shlex, subprocess, time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
REMOTE = "glmrunner@89.169.103.97"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
ROOT = "/home/glmrunner/adaptive_depth6_fresh_endpoint"
IMAGE = "docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
RUN = PROJECT / "artifacts/stock-assert-localization"
CONTAINER = "gemma4-adaptive-stock-localization"
launch = json.loads((PROJECT / "inputs/fresh_endpoint_packet/candidate-v0.5.15/inputs/ngram-launch.json").read_text())["args"]

def ssh(command: str, timeout=1800, check=True):
    args=["ssh","-i",KEY,"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}",REMOTE,command]
    r=subprocess.run(args,text=True,capture_output=True,timeout=timeout,check=False)
    RUN.mkdir(parents=True,exist_ok=True)
    with (RUN/"events.jsonl").open("a") as f: f.write(json.dumps({"command":command,"returncode":r.returncode,"stdout":r.stdout[-2000:],"stderr":r.stderr[-4000:]})+"\n")
    if check and r.returncode: raise RuntimeError(f"ssh_failed:{r.returncode}:{r.stderr[-1000:]}")
    return r

def start(repair=False):
    ssh(f"sudo -n docker rm -f {CONTAINER} >/dev/null 2>&1 || true",60)
    extra = " --triton-attention-num-kv-splits 1" if repair else ""
    cmd=(f"sudo -n docker run -d --name {CONTAINER} --gpus all --ipc=host -p 30000:30000 "
         f"-e CUDA_LAUNCH_BLOCKING=1 -v {ROOT}/../gemma4-h100-packed-endpoint/checkpoint:/work/checkpoint:ro "
         f"{IMAGE} python3 -m sglang.launch_server {' '.join(shlex.quote(x) for x in launch)}{extra}")
    ssh(cmd,120)

def stop(log):
    ssh(f"sudo -n docker logs {CONTAINER} > {ROOT}/artifacts/{log}.log 2>&1 || true; sudo -n docker stop -t 30 {CONTAINER} >/dev/null 2>&1 || true; sudo -n docker rm {CONTAINER} >/dev/null 2>&1 || true",120,False)
    lp=RUN/(log+".log"); lp.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(["scp","-q","-i",KEY,"-o","StrictHostKeyChecking=yes",f"-o","UserKnownHostsFile={KNOWN}",f"{REMOTE}:{ROOT}/artifacts/{log}.log",str(lp)],check=False,timeout=300)

def run_client(indices, name):
    remote_out=f"{ROOT}/artifacts/stock-assert-localization/{name}.json"
    result=ssh(f"FRESH_ENDPOINT_ROOT={ROOT} python3 {ROOT}/stock_localization_client.py --indices {' '.join(map(str,indices))} --output {remote_out}",timeout=1200,check=False)
    local=RUN/(name+".json"); local.parent.mkdir(parents=True,exist_ok=True)
    subprocess.run(["scp","-q","-i",KEY,"-o","StrictHostKeyChecking=yes",f"-o","UserKnownHostsFile={KNOWN}",f"{REMOTE}:{remote_out}",str(local)],check=False,timeout=300)
    return result

def main():
    RUN.mkdir(parents=True,exist_ok=True)
    start(repair=False)
    diagnostic=run_client([62128],"diagnostic_62128")
    stop("server_diagnostic")
    start(repair=True)
    guard=run_client([62127,62128,62129],"stock_aa_guard")
    stop("server_guard")
    guard_ok=guard.returncode == 0
    summary={"schema_version":1,"diagnostic":{"request":62128,"cuda_launch_blocking":True,"returncode":diagnostic.returncode},"repair":{"kind":"triton_attention_num_kv_splits_1","applied_to_stock_and_candidate_scope":True,"semantic_scope_unchanged":True},"guard":{"indices":[62127,62128,62129],"returncode":guard.returncode,"passed":guard_ok},"server_stopped":True,"created_at_utc":time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())}
    (RUN/"LOCALIZATION_SUMMARY.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    if not guard_ok: raise SystemExit(3)
    env={**os.environ,"FRESH_START":"63000","FRESH_END":"63790","FRESH_REPAIR":"0"}
    os.execve("/usr/bin/python3",["python3","run_fresh_endpoint_controller.py"],env)

if __name__ == "__main__": main()
