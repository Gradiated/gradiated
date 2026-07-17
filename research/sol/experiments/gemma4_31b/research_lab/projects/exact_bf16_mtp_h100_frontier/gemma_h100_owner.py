#!/usr/bin/env python3
"""Durable exact-Gemma H100 stock owner."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
NEBIUS = Path("/root/workspace/research/sol/experiments/glm47flash/campaign_100/nebius")
sys.path.insert(0, str(NEBIUS))
from placement_control import PlacementError, VerifiedRetainedOwner, build_create_command, extract_instance_id, extract_public_ipv4, get_instance, list_items, make_cloud_init, metadata_name, wait_ssh
from stock_control import run_ssh, scp_from
from vllm_smoke_control import start_independent_watchdog

MODEL = "google/gemma-4-31B-it"
REVISION = "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
IMAGE = "vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
SSH_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
SSH_PUBLIC_KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519.pub")

def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def emit(events: Path, event: str, **fields: object) -> None:
    with events.open("a") as handle:
        handle.write(json.dumps({"timestamp": utc_now(), "event": event, **fields}, sort_keys=True) + "\n")

def require_owner() -> None:
    if not os.environ.get("INVOCATION_ID") or os.environ.get("SYSTEMD_EXEC_PID") != str(os.getpid()):
        raise RuntimeError("provider mutation requires a systemd durable owner")

def remote_script(deadline: int) -> str:
    base = f"https://huggingface.co/{MODEL}/resolve/{REVISION}"
    return f"""set -Eeuo pipefail
workspace=/home/glmrunner/gemma-workspace
out=$workspace/gemma-frontier
model=$workspace/gemma-model
mkdir -p "$out" "$model"
for file in config.json generation_config.json tokenizer.json tokenizer_config.json chat_template.jinja processor_config.json model.safetensors.index.json model-00001-of-00002.safetensors model-00002-of-00002.safetensors; do
  test "$(date +%s)" -lt "{deadline}"
  curl --fail --location --retry 3 --retry-all-errors --silent --show-error --output "$model/$file" "{base}/$file"
done
(cd "$model" && sha256sum * | sort > "$out/model-files.sha256")
sudo docker pull {IMAGE}
sudo docker image inspect {IMAGE} --format '{{{{index .RepoDigests 0}}}}' > "$out/runtime-image.txt"
python3 - <<'PY' > "$out/stock-request.json"
import json
prompt = "Summarize this deterministic token stream: " + ("gemma frontier measurement token. " * 1400)
print(json.dumps({{"model": "{MODEL}", "prompt": prompt, "max_tokens": 358, "temperature": 0, "seed": 7}}))
PY
sudo docker rm -f gemma-frontier >/dev/null 2>&1 || true
sudo docker run -d --rm --name gemma-frontier --gpus all --ipc=host --shm-size=16g -p 8000:8000 -v "$workspace:$workspace" {IMAGE} vllm serve "$model" --dtype bfloat16 --max-model-len 12000 --max-num-seqs 16 --max-num-batched-tokens 16384 --limit-mm-per-prompt '{{"image":0,"audio":0}}' > "$out/container-id.txt"
ready=0
while test "$(date +%s)" -lt "{deadline}"; do
  if curl --fail --silent http://127.0.0.1:8000/v1/models > "$out/models.json"; then ready=1; break; fi
  sleep 5
done
test "$ready" = 1
python3 - <<'PY'
import json, time, urllib.request
root='/workspace/gemma-frontier'; base=json.loads(open(root+'/stock-request.json').read()); rows=[]
for concurrency in (1, 8, 16):
    for index in range(concurrency):
        started=time.monotonic()
        req=urllib.request.Request('http://127.0.0.1:8000/v1/completions', data=json.dumps(base).encode(), headers={{'Content-Type':'application/json'}})
        with urllib.request.urlopen(req, timeout=300) as response: payload=json.loads(response.read())
        rows.append({{'concurrency':concurrency,'index':index,'wall_seconds':time.monotonic()-started,'text':payload['choices'][0]['text'],'usage':payload.get('usage')}})
open(root+'/stock-rows.json','w').write(json.dumps(rows,sort_keys=True))
PY
nvidia-smi --query-gpu=name,memory.total,utilization.gpu,memory.used,power.draw --format=csv,noheader,nounits > "$out/gpu-final.csv"
sudo docker logs gemma-frontier > "$out/vllm.log" 2>&1 || true
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -czf "$workspace/gemma-frontier.tar.gz" -C "$workspace" gemma-frontier
sha256sum "$workspace/gemma-frontier.tar.gz" > "$workspace/gemma-frontier.tar.gz.sha256"
"""

def run(output_dir: Path, name: str, deadline: float) -> int:
    require_owner()
    output_dir.mkdir(parents=True, exist_ok=False)
    events = output_dir / "events.jsonl"
    emit(events, "owner_started", name=name, deadline_epoch=deadline, model=MODEL, revision=REVISION, image=IMAGE)
    if not SSH_KEY.is_file() or not SSH_PUBLIC_KEY.is_file():
        raise RuntimeError("required Nebius SSH keypair unavailable")
    if list_items("instance") or any(metadata_name(x) == f"{name}-boot" for x in list_items("disk")):
        raise RuntimeError("pre-create gate: Nebius inventory is not empty")
    (output_dir / "request.json").write_text(json.dumps({"name":name,"platform":"gpu-h100-sxm","preset":"1gpu-16vcpu-200gb","disk_gib":200,"preemptible":True,"deadline_epoch":deadline,"model":MODEL,"revision":REVISION,"image":IMAGE,"remote_workspace":"/home/glmrunner/gemma-workspace","prior_attempt":{"run":"gemma-bf16-h100-20260716t2210z","allocation_seconds":125.189,"classification":"pre_gpu_remote_workspace_permission_failure_cleanup_verified"}}, indent=2, sort_keys=True) + "\n")
    instance_id = None
    watchdog = None
    try:
        with VerifiedRetainedOwner(name, output_dir / "cleanup.json") as owner:
            create = subprocess.run(build_create_command(name=name, disk_name=f"{name}-boot", cloud_init=make_cloud_init(SSH_PUBLIC_KEY.read_text()), disk_gib=200, platform="gpu-h100-sxm", preset="1gpu-16vcpu-200gb", preemptible=True), capture_output=True, text=True, timeout=180)
            (output_dir / "provider-create.json").write_text(json.dumps({"returncode":create.returncode,"stdout_sha256":hashlib.sha256(create.stdout.encode()).hexdigest(),"stderr_sha256":hashlib.sha256(create.stderr.encode()).hexdigest()}, indent=2, sort_keys=True) + "\n")
            if create.returncode: raise PlacementError(f"provider create returned {create.returncode}")
            instance_id = extract_instance_id(json.loads(create.stdout)); owner.bind_instance(instance_id)
            watchdog = start_independent_watchdog(instance_id, f"{name}-boot", deadline, f"{name}-watchdog")
            emit(events, "instance_created", instance_id=instance_id, watchdog=watchdog)
            ip = None
            ready_deadline = min(deadline, time.time()+600)
            while time.time() < ready_deadline:
                payload = get_instance(instance_id)
                if payload is None: raise RuntimeError("instance disappeared before SSH readiness")
                ip = extract_public_ipv4(payload)
                if ip: break
                time.sleep(5)
            if not ip: raise RuntimeError("public IP readiness exceeded 600 seconds")
            wait_ssh(ip, SSH_KEY, ready_deadline); emit(events, "ssh_ready", instance_id=instance_id)
            remote = run_ssh(ip, SSH_KEY, "bash -s", timeout=max(60, int(deadline-time.time())), input_text=remote_script(int(deadline)))
            (output_dir / "remote.stdout.log").write_text(remote.stdout); (output_dir / "remote.stderr.log").write_text(remote.stderr)
            if remote.returncode: raise RuntimeError(f"remote stock workload returned {remote.returncode}")
            scp_from(ip, SSH_KEY, "/home/glmrunner/gemma-workspace/gemma-frontier.tar.gz", output_dir / "gemma-frontier.tar.gz")
            scp_from(ip, SSH_KEY, "/home/glmrunner/gemma-workspace/gemma-frontier.tar.gz.sha256", output_dir / "gemma-frontier.tar.gz.sha256")
            actual = hashlib.sha256((output_dir/"gemma-frontier.tar.gz").read_bytes()).hexdigest()
            if actual != (output_dir/"gemma-frontier.tar.gz.sha256").read_text().split()[0]: raise RuntimeError("retrieved artifact hash mismatch")
            owner.complete("stock_control_completed"); emit(events, "stock_completed", artifact_sha256=actual)
    except Exception as error:
        emit(events, "owner_error", error_type=type(error).__name__, message=str(error)[:500])
        (output_dir / "failure.json").write_text(json.dumps({"error_type":type(error).__name__,"message":str(error)[:500],"instance_id":instance_id,"watchdog":watchdog}, indent=2, sort_keys=True) + "\n")
        return 1
    (output_dir / "summary.json").write_text(json.dumps({"classification":"stock_control_completed","instance_id":instance_id,"watchdog":watchdog,"completed_at_utc":utc_now()}, indent=2, sort_keys=True) + "\n")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True); parser.add_argument("--name", required=True); parser.add_argument("--deadline-epoch", type=float, required=True)
    args = parser.parse_args()
    return run(args.output_dir.resolve(), args.name, args.deadline_epoch)

if __name__ == "__main__":
    raise SystemExit(main())
