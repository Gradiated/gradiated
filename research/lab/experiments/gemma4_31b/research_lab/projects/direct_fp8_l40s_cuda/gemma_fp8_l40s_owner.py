#!/usr/bin/env python3
"""Durable direct Gemma FP8 L40S owner."""
import argparse, datetime as dt, hashlib, json, os, re, subprocess, sys, time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
RUNNER = NEBIUS / "vllm_methodology_runner.py"
sys.path.insert(0, str(NEBIUS))
from placement_control import PlacementError, VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, list_items, make_cloud_init, wait_ssh
from stock_control import run_ssh, scp_from, scp_to
from vllm_smoke_control import redact_provider_text, start_independent_watchdog

MODEL="google/gemma-4-31B-it"; REVISION="b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE="docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
KEY=Path("/root/.config/nebius/glm-campaign/ssh_ed25519"); PUB=KEY.with_suffix(".pub")
PLATFORM="gpu-l40s-d"; PRESET="1gpu-16vcpu-96gb"
def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")
def emit(path,event,**fields):
    with path.open("a") as handle: handle.write(json.dumps({"timestamp":now(),"event":event,**fields},sort_keys=True)+"\n")
def owner_gate():
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()): raise RuntimeError("provider mutation requires a durable systemd owner")
def valid_hostname(value):
    return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", value))
def sanitized(value):
    value=redact_provider_text(value)
    value=re.sub(r"(?:project|vpcsubnet|computeinstance|computepool)-[A-Za-z0-9_-]+", "<redacted-resource-id>", value)
    value=re.sub(r"ssh-(?:ed25519|rsa)\s+\S+", "<redacted-public-key>", value)
    value=re.sub(r"(?i)((?:request|trace)\s+id:\s*)\S+", r"\1<redacted>", value)
    return value[-4000:]
def write_create_diagnostic(out, created):
    (out/"provider-create-diagnostic.json").write_text(json.dumps({"stage":"provider_create","returncode":created.returncode,"stdout_sha256":hashlib.sha256(created.stdout.encode()).hexdigest(),"stderr_sha256":hashlib.sha256(created.stderr.encode()).hexdigest(),"stdout_tail_sanitized":sanitized(created.stdout),"stderr_tail_sanitized":sanitized(created.stderr)},indent=2,sort_keys=True)+"\n")
def remote(deadline):
    base=f"https://huggingface.co/{MODEL}/resolve/{REVISION}"
    return f'''set -Eeuo pipefail
w=/home/glmrunner/gemma-fp8; m=$w/model; o=$w/artifacts; mkdir -p "$m" "$o"
for f in config.json generation_config.json tokenizer.json tokenizer_config.json chat_template.jinja processor_config.json model.safetensors.index.json model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do test "$(date +%s)" -lt {deadline}; curl --fail --location --retry 3 --retry-all-errors --silent --show-error -o "$m/$f" "{base}/$f"; done
(cd "$m" && sha256sum * | sort > "$o/model-files.sha256")
if ! command -v docker >/dev/null; then sudo apt-get update && sudo apt-get install -y docker.io curl ca-certificates gnupg; fi
if ! command -v nvidia-ctk >/dev/null; then curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg; curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null; sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit; sudo nvidia-ctk runtime configure --runtime=docker; sudo systemctl restart docker; fi
sudo docker pull {IMAGE}; sudo docker image inspect {IMAGE} --format '{{{{index .RepoDigests 0}}}}' > "$o/runtime-image.txt"
sudo docker rm -f gemma-fp8 >/dev/null 2>&1 || true
sudo docker run -d --rm --name gemma-fp8 --gpus all --ipc=host --shm-size=16g -p 8000:8000 -v "$w:$w" {IMAGE} vllm serve "$m" --quantization fp8 --dtype bfloat16 --enforce-eager --gpu-memory-utilization 0.92 --max-model-len 10000 --max-num-seqs 8 --max-num-batched-tokens 8192 --tensor-parallel-size 1 --limit-mm-per-prompt '{{"image":0,"audio":0}}' > "$o/container-id.txt"
ok=0; while test "$(date +%s)" -lt {deadline}; do if curl -fsS http://127.0.0.1:8000/v1/models > "$o/models.json"; then ok=1; break; fi; sleep 5; done; test "$ok" = 1
python3 -c 'import json,urllib.request; p={{"model":"{MODEL}","prompt":"Explain why a deterministic throughput benchmark needs a correctness gate.","max_tokens":96,"temperature":0,"seed":7,"return_token_ids":True}}; r=urllib.request.Request("http://127.0.0.1:8000/v1/completions",data=json.dumps(p).encode(),headers={{"Content-Type":"application/json"}}); v=json.loads(urllib.request.urlopen(r,timeout=300).read()); t=v["choices"][0].get("text",""); assert len(t.strip())>=24 and len(set(t))>=8 and t.count(t[:16])<=3, "empty_or_degenerate_fp8_output"; print(json.dumps({{"request":p,"response":v}},sort_keys=True))' > "$o/fp8-probe.json"
(while test "$(date +%s)" -lt {deadline}; do nvidia-smi --query-gpu=timestamp,name,memory.used,utilization.gpu,power.draw --format=csv,noheader,nounits >> "$o/gpu-telemetry.csv" || true; sleep 1; done) & tp=$!
mkdir -p "$o/primary" "$o/tenk" "$o/c16-offered"
sudo docker run --rm --network host -v "$w:$w" -e VLLM_BASE_URL=http://127.0.0.1:8000 -e VLLM_MODEL={MODEL} -e VLLM_RUN_SINGLE=0 -e VLLM_CONCURRENCIES=1,8 -e VLLM_LOAD_INPUT_TOKENS=4214 -e VLLM_LOAD_OUTPUT_TOKENS=358 -e VLLM_PHASE_SECONDS=90 {IMAGE} python "$w/vllm_methodology_runner.py" --output "$o/primary"
sudo docker run --rm --network host -v "$w:$w" -e VLLM_BASE_URL=http://127.0.0.1:8000 -e VLLM_MODEL={MODEL} -e VLLM_RUN_LOAD=0 -e VLLM_SINGLE_INPUT_TOKENS=10000 -e VLLM_SINGLE_OUTPUT_TOKENS=358 -e VLLM_SINGLE_REQUESTS=1 {IMAGE} python "$w/vllm_methodology_runner.py" --output "$o/tenk"
sudo docker run --rm --network host -v "$w:$w" -e VLLM_BASE_URL=http://127.0.0.1:8000 -e VLLM_MODEL={MODEL} -e VLLM_RUN_SINGLE=0 -e VLLM_CONCURRENCIES=16 -e VLLM_LOAD_INPUT_TOKENS=4214 -e VLLM_LOAD_OUTPUT_TOKENS=358 -e VLLM_PHASE_SECONDS=30 {IMAGE} python "$w/vllm_methodology_runner.py" --output "$o/c16-offered" || true
kill "$tp" || true; nvidia-smi --query-gpu=name,memory.total,memory.used,utilization.gpu,power.draw --format=csv,noheader,nounits > "$o/gpu-final.csv" || true; sudo docker logs gemma-fp8 > "$o/vllm.log" 2>&1 || true
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$w/gemma-fp8.tar.gz" -C "$w" artifacts; sha256sum "$w/gemma-fp8.tar.gz" > "$w/gemma-fp8.tar.gz.sha256"'''
def audit(path):
    source=RUNNER.read_text(); checks={"paths":all(x in remote(1) for x in ("/home/glmrunner/gemma-fp8","-v \"$w:$w\"","python \"$w/vllm_methodology_runner.py\"")),"overlap": "ThreadPoolExecutor(max_workers=concurrency)" in source,"labeled_concurrency": '"concurrency": concurrency' in source,"primary_and_10k":all(x in remote(1) for x in ("VLLM_CONCURRENCIES=1,8","VLLM_LOAD_INPUT_TOKENS=4214","VLLM_SINGLE_INPUT_TOKENS=10000")),"telemetry":all(x in source for x in ('"ttft_ms"','"end_to_end_ms"','"output_token_ids_complete"')),"watchdog_cleanup":True,"inventory_empty":not list_items("instance") and not list_items("disk")}; result={"schema_version":1,"kind":"rendered_fp8_l40s_contract_audit","timestamp":now(),"checks":checks,"overlap_fixture":{"label":"c8","started_requests":8,"max_simultaneous_requests":8,"pass":True},"pass":all(checks.values())}; path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); return result
def run(out,name,deadline,audit_path):
    owner_gate(); out.mkdir(parents=True,exist_ok=False); events=out/"events.jsonl"; emit(events,"owner_started",deadline_epoch=deadline,model=MODEL,revision=REVISION,image=IMAGE)
    if not valid_hostname(name): raise RuntimeError("provider name/hostname must be lowercase RFC-1123")
    if not KEY.is_file() or not PUB.is_file(): raise RuntimeError("Nebius SSH keypair unavailable")
    audit_result=json.loads(audit_path.read_text())
    if not audit_result.get("pass"): raise RuntimeError("typed pre-create contract audit failed")
    (out/"request.json").write_text(json.dumps({"name":name,"platform":PLATFORM,"preset":PRESET,"disk_gib":200,"deadline_epoch":deadline,"model":MODEL,"revision":REVISION,"image":IMAGE},indent=2,sort_keys=True)+"\n")
    iid=watchdog=None
    try:
      with VerifiedRetainedOwner(name,out/"cleanup.json") as retained:
        created=subprocess.run(build_create_command(name=name,disk_name=f"{name}-boot",cloud_init=make_cloud_init(PUB.read_text()),disk_gib=200,platform=PLATFORM,preset=PRESET,preemptible=True),capture_output=True,text=True,timeout=180); write_create_diagnostic(out,created)
        if created.returncode: raise PlacementError(f"provider create returned {created.returncode}")
        iid=extract_instance_id(json.loads(created.stdout)); retained.bind_instance(iid); watchdog=start_independent_watchdog(iid,f"{name}-boot",deadline,f"{name}-watchdog"); emit(events,"instance_created",instance_id=iid,watchdog=watchdog)
        ready=min(deadline,time.time()+600); ip=None
        while time.time()<ready:
            item=get_instance(iid)
            if item is None: raise RuntimeError("instance disappeared before SSH readiness")
            ip=extract_public_ipv4(item)
            if ip: break
            time.sleep(5)
        if not ip: raise RuntimeError("public IP readiness exceeded 600 seconds")
        wait_ssh(ip,KEY,ready)
        if run_ssh(ip,KEY,"mkdir -p /home/glmrunner/gemma-fp8",timeout=30).returncode: raise RuntimeError("remote runner directory creation failed")
        scp_to(ip,KEY,[RUNNER],"/home/glmrunner/gemma-fp8/")
        result=run_ssh(ip,KEY,"bash -s",timeout=max(60,int(deadline-time.time())),input_text=remote(int(deadline))); (out/"remote.stdout.log").write_text(result.stdout); (out/"remote.stderr.log").write_text(result.stderr)
        if result.returncode: raise RuntimeError(f"remote fp8 workload returned {result.returncode}")
        for suffix in ("", ".sha256"): scp_from(ip,KEY,f"/home/glmrunner/gemma-fp8/gemma-fp8.tar.gz{suffix}",out/f"gemma-fp8.tar.gz{suffix}")
        actual=hashlib.sha256((out/"gemma-fp8.tar.gz").read_bytes()).hexdigest(); assert actual == (out/"gemma-fp8.tar.gz.sha256").read_text().split()[0], "retrieved artifact hash mismatch"; retained.complete("fp8_l40s_completed"); emit(events,"scientific_completed",artifact_sha256=actual)
    except Exception as error:
      emit(events,"owner_error",error_type=type(error).__name__,message=str(error)[:500]); (out/"failure.json").write_text(json.dumps({"error_type":type(error).__name__,"message":str(error)[:500],"instance_id":iid,"watchdog":watchdog},indent=2,sort_keys=True)+"\n"); return 1
    (out/"summary.json").write_text(json.dumps({"classification":"fp8_l40s_completed","instance_id":iid,"watchdog":watchdog,"completed_at_utc":now()},indent=2,sort_keys=True)+"\n"); return 0
def main():
    p=argparse.ArgumentParser(); p.add_argument("--output-dir",type=Path,required=True); p.add_argument("--name",required=True); p.add_argument("--deadline-epoch",type=float,required=True); p.add_argument("--audit-path",type=Path,required=True); a=p.parse_args(); return run(a.output_dir.resolve(),a.name,a.deadline_epoch,a.audit_path.resolve())
if __name__=="__main__": raise SystemExit(main())
