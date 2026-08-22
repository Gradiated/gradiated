#!/usr/bin/env python3
"""Bound durable owner for the single quality-unsafe H200 endpoint pair."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
TERMINAL = "HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json"

def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise RuntimeError("json_object_required")
    return value
def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as out:
        json.dump(value, out, indent=2, sort_keys=True); out.write("\n"); temporary=Path(out.name)
    json.loads(temporary.read_text()); temporary.replace(path)
def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable,"-m","grad_research.gpu_pool","--lab",str(LAB),*args],text=True,capture_output=True,env={**os.environ,"PYTHONPATH":str(ROOT.parents[5]/"factory"/"src")})
def run(command: list[str], timeout: float) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command,text=True,capture_output=True,timeout=max(1,timeout),check=False)
def parse_time(value: str) -> dt.datetime: return dt.datetime.fromisoformat(value.replace("Z","+00:00"))
def claim_at(value: str) -> str:
    match=re.search(r'"claimed_at"\s*:\s*"([^"]+)',value)
    if not match: raise RuntimeError("claim_timestamp_missing")
    return match.group(1)
def status_update(**changes: Any) -> None:
    value=load(ROOT/"STATUS.json"); value.update(changes); atomic(ROOT/"STATUS.json",value)

def validate(binding: dict[str,Any], manifest: dict[str,Any], preclaim: dict[str,Any]) -> dict[str,Any]:
    packet=ROOT/binding["packet_manifest_path"]; repair=ROOT/binding["live_binding_repair_manifest_path"]
    if not (binding.get("project")==PROJECT and binding.get("claim_allowed") is True and binding.get("quality_preservation_claimed") is False): raise RuntimeError("binding_authority_invalid")
    if sha(packet)!=binding["packet_manifest_sha256"] or sha(repair)!=binding["live_binding_repair_manifest_sha256"]: raise RuntimeError("binding_digest_mismatch")
    p=load(packet)
    if binding.get("immutable_scientific_files")!=p.get("immutable_files") or binding.get("pair_contract")!=p.get("pair_contract"): raise RuntimeError("scientific_packet_mismatch")
    if sha(ROOT/binding["candidate_source"]["path"])!=binding["candidate_source"]["sha256"]: raise RuntimeError("candidate_digest_mismatch")
    if sha(ROOT/manifest["owner_path"])!=manifest["owner_sha256"] or sha(ROOT/"run_h200_55l5g_endpoint_pair.py")!=manifest["pair_sha256"]: raise RuntimeError("runtime_manifest_mismatch")
    if not (binding["budget"]["cumulative_authorized_usd"]==22.0 and binding["budget"]["prior_actual_usd"]==9.960954252113234 and binding["budget"]["maximum_cumulative_usd"]<=22.0): raise RuntimeError("budget_invalid")
    if preclaim.get("classification")!="preclaim_endpoint_ready" or preclaim.get("science_consumed") is not False: raise RuntimeError("preclaim_invalid")
    return p

def heartbeat(stop: threading.Event, artifact: Path, bench: str) -> None:
    while not stop.wait(35):
        result=pool("heartbeat","--project",PROJECT,"--bench",bench)
        atomic(artifact/"HEARTBEAT.json",{"at_utc":dt.datetime.now(dt.timezone.utc).isoformat(),"returncode":result.returncode,"stderr":result.stderr[-2000:]})

def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--execution-binding",type=Path,required=True); parser.add_argument("--runtime-manifest",type=Path,required=True); parser.add_argument("--preclaim-packet",type=Path,required=True); parser.add_argument("--artifact-root",type=Path,required=True); args=parser.parse_args()
    binding, manifest, preclaim = load(args.execution_binding), load(args.runtime_manifest), load(args.preclaim_packet)
    packet=validate(binding,manifest,preclaim)
    if dt.datetime.now(dt.timezone.utc)>parse_time(binding["lifecycle"]["claim_start_by_utc"]): raise RuntimeError("claim_start_fence_expired")
    shown=pool("show","--bench",binding["live_bench"]["id"])
    if shown.returncode: raise RuntimeError("live_bench_unreadable")
    bench=json.loads(shown.stdout); resource=binding["live_bench"]["resource"]
    existing=bench.get("claim") or {}
    admissible=(bench.get("status")=="available" and not existing) or (bench.get("status")=="claimed" and existing.get("project")==PROJECT and existing.get("claimed_at"))
    if not (admissible and bench.get("resource",{}).get("instance_id")==resource["instance_id"] and bench.get("resource",{}).get("ssh_ed25519_fingerprint")==resource["ssh_ed25519_fingerprint"]): raise RuntimeError("live_bench_gate_invalid")
    artifact=args.artifact_root.resolve(); artifact.mkdir(parents=True,exist_ok=False)
    claimed=pool("claim","--project",PROJECT,"--bench",bench["id"]); (artifact/"claim.stdout.log").write_text(claimed.stdout); (artifact/"claim.stderr.log").write_text(claimed.stderr)
    if claimed.returncode: atomic(artifact/"OWNER_FAILURE.json",{"classification":"atomic_claim_failed","science_consumed":False}); return 2
    expected=existing.get("claimed_at") or claim_at(claimed.stdout); stop=threading.Event(); threading.Thread(target=heartbeat,args=(stop,artifact,bench["id"]),daemon=True).start()
    owner_state=os.environ.get("DETACHED_OWNER_STATE",str(artifact.parent/(artifact.name+"-controller")/"OWNER_STATE.json"))
    status_update(active_session={"artifact_root":str(artifact),"bench_id":bench["id"],"expected_claimed_at_utc":expected,"deadline_utc":binding["lifecycle"]["owner_deadline_utc"],"expected_terminal":TERMINAL,"forward_progress":"claim complete; resumable checkpoint/image stage then matched endpoint pair","unit":owner_state,"pid":os.getpid(),"unit_manager":"pid"})
    try:
        key=bench["resource"]["identity_file"]; host=f"{bench['resource']['ssh_user']}@{bench['resource']['public_ipv4']}"; known=bench["resource"]["known_hosts_namespace"]
        ssh=["/usr/bin/ssh","-i",key,"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}",host]
        scp=["/usr/bin/scp","-i",key,"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={known}"]
        d=binding["runtime_destinations"]; remote=d["remote_root"]; checkpoint=d["checkpoint"]
        stage=f"set -euo pipefail; mkdir -p {remote}/packet {remote}/out; sudo -n docker pull {d['image']}; if [ ! -f {checkpoint}/.hybrid-55l5g-manifest.json ]; then rm -rf {checkpoint}.part; mkdir -p {checkpoint}.part; sudo -n docker run --rm -v {checkpoint}.part:/out {d['image']} huggingface-cli download google/gemma-4-31B-it --revision b9ea41a2887d8607f594846523f94c6cc75ac8a4 --local-dir /out; test $(du -sb {checkpoint}.part | awk '{{print $1}}') -ge {d['checkpoint_bytes']}; printf '{{\\\"revision\\\":\\\"b9ea41a2887d8607f594846523f94c6cc75ac8a4\\\",\\\"bytes\\\":{d['checkpoint_bytes']}}}\\n' > {checkpoint}.part/.hybrid-55l5g-manifest.json; mv {checkpoint}.part {checkpoint}; fi"
        result=run([*ssh,stage],max(60,(parse_time(binding["lifecycle"]["release_by_utc"])-dt.datetime.now(dt.timezone.utc)).total_seconds()-1200)); (artifact/"stage.stdout.log").write_text(result.stdout); (artifact/"stage.stderr.log").write_text(result.stderr)
        if result.returncode: atomic(artifact/"PRE_SCIENCE_FAILURE.json",{"classification":"recoverable_staging_or_image_failure","science_consumed":False,"stderr":result.stderr[-12000:]}); return 72
        for source in (ROOT/binding["candidate_source"]["path"],ROOT/packet["pair_contract"]["workload_path"]):
            result=run([*scp,str(source),f"{host}:{remote}/packet/{source.name}"],600)
            if result.returncode: raise RuntimeError("packet_transfer_failed")
        # Sequential model residency fits the 143-GiB H200; each endpoint arm uses the immutable c32 driver.
        runner="import json,sys;from pathlib import Path;import run_h200_55l5g_endpoint_pair as p; w=json.loads(Path('/work/qualified_c32_workload.json').read_text()); print(json.dumps(p.run_arm(sys.argv[1],sys.argv[2],w,900)))"
        def arm(name: str, mount: str="") -> dict[str,Any]:
            launch=f"sudo -n docker rm -f hybrid-55l5g >/dev/null 2>&1 || true; sudo -n docker run -d --name hybrid-55l5g --gpus all -p 30000:30000 -v {checkpoint}:/models/target:ro -v {remote}/packet:/work {mount} {d['image']} python3 -m sglang.launch_server --model-path /models/target --tokenizer-path /models/target --dtype bfloat16 --tp-size 1 --host 0.0.0.0 --port 30000 --context-length 5000 --max-running-requests 32"
            launched=run([*ssh,launch],180)
            if launched.returncode: raise RuntimeError(f"{name}_launch_failed")
            until=time.time()+600
            while time.time()<until:
                health=run([*ssh,"curl -fsS http://127.0.0.1:30000/health"],20)
                if health.returncode==0: break
                state=run([*ssh,"sudo -n docker inspect --format '{{json .State}}' hybrid-55l5g"],20)
                if state.returncode==0 and 'false' in state.stdout.lower(): raise RuntimeError(f"{name}_server_exited")
                time.sleep(3)
            else: raise RuntimeError(f"{name}_readiness_timeout")
            if name=="candidate":
                proof=run([*ssh,"sudo -n docker exec hybrid-55l5g sha256sum /usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py"],60)
                if binding["candidate_source"]["sha256"] not in proof.stdout: raise RuntimeError("candidate_path_proof_invalid")
            call=run([*ssh,f"cd {remote}/packet && sudo -n docker exec hybrid-55l5g python3 -c {json.dumps(runner)} {name} http://127.0.0.1:30000"],1200)
            logs=run([*ssh,"sudo -n docker logs hybrid-55l5g 2>&1 | /usr/bin/tail -n 400"],60); run([*ssh,"sudo -n docker rm -f hybrid-55l5g >/dev/null 2>&1 || true"],60)
            if call.returncode: raise RuntimeError(f"{name}_request_driver_failed")
            out=json.loads(call.stdout.strip().splitlines()[-1]); out["server_log_tail"]=logs.stdout[-12000:]; return out
        stock=arm("stock"); candidate=arm("candidate",f"-v {remote}/packet/{Path(binding['candidate_source']['path']).name}:/usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py:ro")
        valid=stock["complete_requests"]==candidate["complete_requests"]==32 and stock["failures"]==candidate["failures"]==0
        terminal={"schema_version":1,"classification":"scientific_terminal" if valid else "invalid_endpoint_pair","science_consumed":valid,"candidate_cuda_invocation_started":valid,"quality_preservation_claimed":False,"workload":binding["pair_contract"],"control":stock,"candidate":candidate,"service_time_delta_seconds_per_request":candidate["service_seconds_per_request"]-stock["service_seconds_per_request"] if valid else None}
        atomic(artifact/TERMINAL,terminal); atomic(ROOT/TERMINAL,terminal)
        if not valid: return 72
        contents=artifact/"BENCH_CONTENTS.json"; atomic(contents,{"project":PROJECT,"checkpoint":checkpoint,"image":d["image"],"terminal":str(artifact/TERMINAL),"server_state":"No server remains; checkpoint and image retained."})
        release=pool("release","--project",PROJECT,"--bench",bench["id"],"--expected-claimed-at",expected,"--condition","ready","--contents",str(contents)); (artifact/"release.stdout.log").write_text(release.stdout); status_update(active_session=None,actual_spend_usd=binding["budget"]["maximum_cumulative_usd"]); return 0 if release.returncode==0 else 72
    except Exception as error:
        atomic(artifact/"OWNER_EXCEPTION.json",{"classification":"recoverable_pre_science_or_unknown","science_consumed":False,"exception":repr(error)})
        return 72
    finally: stop.set()
if __name__=="__main__": raise SystemExit(main())
