#!/usr/bin/env python3
"""Bounded L40S Nsight Compute permission probe for this project."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NEBIUS = ROOT / "campaign_100" / "nebius"
sys.path.insert(0, str(NEBIUS))

from placement_control import (  # noqa: E402
    build_create_command,
    delete_disk,
    delete_instance,
    extract_instance_id,
    extract_public_ipv4,
    list_items,
    make_cloud_init,
    metadata_id,
    metadata_name,
    wait_absent,
    wait_ssh,
)
from stock_control import run_ssh, scp_from, scp_to  # noqa: E402

OUTPUT = Path(__file__).resolve().parent / "artifacts" / "ncu_permission_probe_v2_20260715"
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
PUBLIC_KEY = KEY.with_suffix(".pub")
NAME = "glm47-l40s-ncu-probe-v2"
DISK = NAME + "-boot"
RATE = 0.7492 + 0.0097222
CAP_SECONDS = 1200
IMAGE = "nvidia/cuda:12.9.1-devel-ubuntu22.04"


def now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def remote_script() -> str:
    return r'''set -u
out=/workspace/ncu-probe
rm -rf "$out"; mkdir -p "$out"
record() { "$@" >"$out/$1.stdout.log" 2>"$out/$1.stderr.log"; echo $? >"$out/$1.exitcode"; }
nvidia-smi -q > "$out/nvidia-smi.txt" 2>&1
nvcc --version > "$out/nvcc-version.txt" 2>&1
which ncu > "$out/ncu-path.txt" 2>&1; echo $? > "$out/ncu-path.exitcode"
ncu --version > "$out/ncu-version.txt" 2>&1; echo $? > "$out/ncu-version.exitcode"
ncu --query-metrics > "$out/ncu-query-metrics.txt" 2>&1; echo $? > "$out/ncu-query-metrics.exitcode"
cat > "$out/probe.cu" <<'CU'
#include <cuda_runtime.h>
#include <cstdio>
__global__ void saxpy(float *x) { int i=blockIdx.x*blockDim.x+threadIdx.x; if(i<1048576) x[i]=x[i]*1.0001f+1.f; }
int main(){ float *x; cudaMalloc(&x,1048576*sizeof(float)); for(int i=0;i<20;i++) saxpy<<<4096,256>>>(x); auto e=cudaDeviceSynchronize(); printf("cudaDeviceSynchronize=%s\n",cudaGetErrorString(e)); cudaFree(x); return e!=cudaSuccess; }
CU
nvcc -O3 -arch=sm_89 "$out/probe.cu" -o "$out/probe" > "$out/compile.stdout.log" 2> "$out/compile.stderr.log"; echo $? > "$out/compile.exitcode"
"$out/probe" > "$out/control.stdout.log" 2> "$out/control.stderr.log"; echo $? > "$out/control.exitcode"
ncu --set full --target-processes all --force-overwrite --export "$out/probe" "$out/probe" > "$out/ncu.stdout.log" 2> "$out/ncu.stderr.log"; echo $? > "$out/ncu.exitcode"
find "$out" -maxdepth 1 -type f -printf '%f %s\n' | sort > "$out/files.txt"
python3 - <<'PY'
from pathlib import Path
import hashlib,json,os
p=Path('/workspace/ncu-probe')
files={x.name:{'bytes':x.stat().st_size,'sha256':hashlib.sha256(x.read_bytes()).hexdigest()} for x in p.iterdir() if x.is_file()}
def rc(name):
 try:return int((p/(name+'.exitcode')).read_text().strip())
 except Exception:return None
json.dump({'gpu':'L40S expected','tool_path_rc':rc('ncu-path'),'tool_version_rc':rc('ncu-version'),'query_metrics_rc':rc('ncu-query-metrics'),'compile_rc':rc('compile'),'control_rc':rc('control'),'ncu_rc':rc('ncu'),'ncu_rep_present':(p/'probe.ncu-rep').is_file(),'files':files},open(p/'result.json','w'),indent=2,sort_keys=True)
PY
tar --sort=name --mtime='UTC 1970-01-01' --owner=0 --group=0 --numeric-owner -C /workspace -czf /workspace/ncu-probe.tar.gz ncu-probe
sha256sum /workspace/ncu-probe.tar.gz > /workspace/ncu-probe.tar.gz.sha256
exit 0
'''


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if list_items("instance"):
        raise RuntimeError("provider inventory is nonempty; refusing to race another owner")
    started = time.time()
    deadline = started + CAP_SECONDS
    instance_id = None
    remote = None
    error = None
    (OUTPUT / "spec.json").write_text(json.dumps({
        "question": "Are Nsight Compute counters permitted on one Nebius L40S?",
        "image": IMAGE, "platform": "gpu-l40s-a", "preset": "1gpu-8vcpu-32gb",
        "cap_seconds": CAP_SECONDS, "rate_usd_per_hour": RATE, "max_cost_usd": RATE * CAP_SECONDS / 3600,
        "started_at": now(),
    }, indent=2, sort_keys=True) + "\n")
    try:
        created = subprocess.run(build_create_command(name=NAME, disk_name=DISK, cloud_init=make_cloud_init(PUBLIC_KEY.read_text()), disk_gib=100, platform="gpu-l40s-a", preset="1gpu-8vcpu-32gb", preemptible=True), capture_output=True, text=True, timeout=180)
        (OUTPUT / "create.stdout.log").write_text(created.stdout)
        (OUTPUT / "create.stderr.log").write_text(created.stderr)
        if created.returncode:
            raise RuntimeError(f"instance create exit {created.returncode}")
        instance_id = extract_instance_id(json.loads(created.stdout))
        ip = None
        while time.time() < min(deadline, started + 480):
            from placement_control import get_instance
            payload = get_instance(instance_id)
            ip = extract_public_ipv4(payload) if payload else None
            if ip:
                break
            time.sleep(5)
        if not ip:
            raise RuntimeError("public IP readiness timeout")
        wait_ssh(ip, KEY, min(deadline, started + 600))
        setup = run_ssh(ip, KEY, "bash -s", timeout=min(540, int(deadline-time.time())), input_text="set -Eeuo pipefail\nif ! command -v docker >/dev/null; then sudo apt-get update; sudo apt-get install -y docker.io curl ca-certificates gnupg; fi\nsudo systemctl enable --now docker\ncurl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor --yes -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg\ncurl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#' | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list >/dev/null\nsudo apt-get update\nsudo apt-get install -y nvidia-container-toolkit\nsudo nvidia-ctk runtime configure --runtime=docker\nsudo systemctl restart docker\nsudo docker pull " + IMAGE + "\nsudo mkdir -p /workspace\n")
        (OUTPUT / "setup.stdout.log").write_text(setup.stdout)
        (OUTPUT / "setup.stderr.log").write_text(setup.stderr)
        if setup.returncode:
            raise RuntimeError(f"host setup exit {setup.returncode}")
        mkdir = run_ssh(ip, KEY, "mkdir -p /home/glmrunner/input", timeout=30)
        if mkdir.returncode:
            raise RuntimeError(f"remote input directory creation exit {mkdir.returncode}")
        scp_to(ip, KEY, [Path(__file__)], "/home/glmrunner/input/")
        remote = run_ssh(ip, KEY, ["sudo", "docker", "run", "--rm", "--gpus", "all", "--cap-add", "SYS_ADMIN", "--cap-add", "SYS_PTRACE", "--cap-add", "PERFMON", "--security-opt", "seccomp=unconfined", "-v", "/workspace:/workspace", "--entrypoint", "bash", IMAGE, "-lc", remote_script()], timeout=max(60, int(deadline-time.time())))
        (OUTPUT / "remote.stdout.log").write_text(remote.stdout)
        (OUTPUT / "remote.stderr.log").write_text(remote.stderr)
        scp_from(ip, KEY, "/workspace/ncu-probe.tar.gz", OUTPUT / "ncu-probe.tar.gz")
        scp_from(ip, KEY, "/workspace/ncu-probe.tar.gz.sha256", OUTPUT / "ncu-probe.tar.gz.sha256")
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"
        (OUTPUT / "controller-error.txt").write_text(error + "\n")
    finally:
        if instance_id:
            delete_instance(instance_id)
            absent = wait_absent(instance_id, time.time() + 240)
        else:
            absent = True
        for disk in list_items("disk"):
            if metadata_name(disk) == DISK and metadata_id(disk):
                delete_disk(metadata_id(disk))
        inventory = list_items("instance")
        disks = list_items("disk")
        elapsed = time.time() - started
        (OUTPUT / "summary.json").write_text(json.dumps({
            "error": error, "remote_returncode": None if remote is None else remote.returncode,
            "allocation_seconds": round(elapsed, 3), "derived_cost_usd": round(elapsed * RATE / 3600, 6),
            "instance_absent": absent, "named_instance_remaining": any(metadata_name(x) == NAME for x in inventory),
            "named_disk_remaining": any(metadata_name(x) == DISK for x in disks), "ended_at": now(),
        }, indent=2, sort_keys=True) + "\n")
    return 0 if error is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
