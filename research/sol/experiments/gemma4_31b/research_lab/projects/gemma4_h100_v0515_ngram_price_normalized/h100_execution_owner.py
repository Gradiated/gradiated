#!/usr/bin/env python3
"""Durable in-place owner for the bound H100 NGRAM execution."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from manifest_size import ManifestError, compressed_bytes

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY = Path("/root/workspace/research/factory/src")
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
BENCH = "h100-v0515-ngram-e00mfea030cdngg54z"
PROJECT_NAME = "gemma4_h100_v0515_ngram_price_normalized"
REMOTE = "/home/glmrunner/gemma4-h100-v0515-ngram-price-normalized"
IMAGE = "docker.io/lmsysorg/sglang@sha256:ae55a60885cba1acad22c224b971aa29309b676f5a079f7713a690a8b0dbc9cd"
COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
MODEL = "google/gemma-4-31B-it"
CONTAINER = "gemma4-h100-v0515"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(32 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def atomic(path: Path, value: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def ssh_base(ip: str, key: Path) -> list[str]:
    return ["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", "-o", "ConnectTimeout=15", f"glmrunner@{ip}"]


def ssh(ip: str, key: Path, command: str, *, timeout: int = 1200, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ssh_base(ip, key), "bash", "-s"], input=command if input_text is None else input_text, text=True, capture_output=True, timeout=timeout)


def stream_tar(ip: str, key: Path, source: Path, remote_dir: str, timeout: int) -> None:
    # Use a single shell pipeline so tar's stdout is the remote shell stdin payload.
    command = f"tar -C {source} -cf - . | ssh -i {key} -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts -o ConnectTimeout=15 glmrunner@{ip} 'mkdir -p {remote_dir} && tar -C {remote_dir} -xf -'"
    result = subprocess.run(["bash", "-lc", command], text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"stage_failed:{source}:{result.returncode}:{result.stderr[-2000:]}")


def heartbeat(stop: threading.Event, events: list[dict]) -> None:
    while not stop.wait(45):
        r = subprocess.run(["env", f"PYTHONPATH={FACTORY}", *POOL, "heartbeat", "--project", PROJECT_NAME], text=True, capture_output=True, timeout=30)
        events.append({"at": now(), "kind": "heartbeat", "returncode": r.returncode})


def verify_local() -> dict:
    packet = json.loads((PROJECT / "PACKET_MANIFEST.json").read_text())
    bad = []
    for name, expected in packet.items():
        path = PROJECT / name
        if path.stat().st_size != expected["bytes"] or sha256(path) != expected["sha256"]:
            bad.append(name)
    checkpoint = json.loads((PROJECT / "packet/CHECKPOINT_MANIFEST.json").read_text())
    for item in checkpoint["files"]:
        path = PROJECT / "inputs/checkpoint" / item["name"]
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            bad.append("checkpoint/" + item["name"])
    return {"packet_entries": len(packet), "checkpoint_files": len(checkpoint["files"]), "bad": bad, "pass": not bad}


def remote_hash_script(manifest: dict, root: str) -> str:
    rows = json.dumps(manifest, sort_keys=True)
    return f'''python3 - <<'PY'
import hashlib, json, pathlib, sys
root=pathlib.Path({root!r})
expected=json.loads({rows!r})
bad=[]
for name,item in expected.items():
 p=root/name; h=hashlib.sha256(); n=0
 with p.open('rb') as f:
  for b in iter(lambda:f.read(32*1024*1024),b''): h.update(b); n+=len(b)
 actual=h.hexdigest()
 print(name,n,actual,flush=True)
 if n!=item['bytes'] or actual!=item['sha256']: bad.append(name)
print('REMOTE_HASH_RESULT='+('PASS' if not bad else 'FAIL'))
raise SystemExit(bool(bad))
PY'''


def packet_finalize_transport(remote_root: str, reconcile: str) -> str:
    return (
        f"set -e; sudo -n env PYTHONPATH= {reconcile}\n"
        f"rm -rf {remote_root}/.packet.staging; "
        f"find {remote_root}/packet -type f -printf '%P %s\\n' | sort"
    )


def launch_command() -> str:
    args = json.loads((PROJECT / "packet/candidate-v0.5.15/inputs/ngram-launch.json").read_text())["args"]
    quoted = " ".join(subprocess.list2cmdline([x]) for x in args)
    return f"docker run -d --name {CONTAINER} --gpus all --ipc=host --network=host -v {REMOTE}/checkpoint:/work/checkpoint:ro -v {REMOTE}/candidate-v0.5.15:/work/candidate-v0.5.15:ro {IMAGE} " + "python3 -m sglang.launch_server " + quoted


def disk_repair_command() -> str:
    """Reclaim expendable state and return the raw manifest for local parsing."""
    return f'''set -euo pipefail
IMAGE={IMAGE!r}
echo DISK_REPAIR_BEGIN
df -Pk /var/lib/docker {REMOTE}
sudo -n docker rm -f {CONTAINER} >/dev/null 2>&1 || true
sudo -n docker container prune -f
sudo -n docker image prune -af
sudo -n docker builder prune -af
sudo -n find /var/lib/docker/tmp -mindepth 1 -maxdepth 1 -exec rm -rf -- {{}} + 2>/dev/null || true
echo DISK_REPAIR_AFTER_CLEANUP
sudo -n docker system df
echo MANIFEST_BEGIN
sudo -n docker manifest inspect --verbose {IMAGE}
echo MANIFEST_END
df -Pk /var/lib/docker {REMOTE}
echo DISK_REPAIR_PASS'''


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--artifact-root", type=Path, required=True)
    ap.add_argument("--deadline-epoch", type=float, required=True)
    ap.add_argument("--reuse-staged", action="store_true")
    ap.add_argument("--stage-packet", action="store_true")
    ap.add_argument("--reuse-server", action="store_true")
    ap.add_argument("--endpoint-only", action="store_true")
    ap.add_argument("--bench-id", default=BENCH)
    args = ap.parse_args()
    out = args.artifact_root.resolve(); out.mkdir(parents=True, exist_ok=True)
    events: list[dict] = []
    stop = threading.Event(); hb = threading.Thread(target=heartbeat, args=(stop, events), daemon=True); hb.start()
    terminal: dict = {"schema_version": 1, "project": PROJECT_NAME, "bench": args.bench_id, "started_at": now(), "candidate_sample_consumed": False, "endpoint_sample_consumed": False}
    try:
        local = verify_local(); atomic(out / "LOCAL_AUDIT.json", local)
        if not local["pass"]: raise RuntimeError("local_hash_audit_failed:" + repr(local["bad"]))
        remote_root = REMOTE
        r = ssh(args.ip, args.key, f"set -e; mkdir -p {remote_root}; nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader; sudo -n docker --version; df -h {remote_root}", timeout=120)
        (out / "REMOTE_PREFLIGHT.stdout").write_text(r.stdout); (out / "REMOTE_PREFLIGHT.stderr").write_text(r.stderr)
        if r.returncode: raise RuntimeError("remote_preflight_failed")
        # Reconcile the empty registration before staging; matched immutable files are preserved.
        r = ssh(args.ip, args.key, f"find {remote_root} -maxdepth 2 -type f -printf '%P %s\\n' 2>/dev/null || true", timeout=60)
        (out / "REMOTE_RECONCILE.txt").write_text(r.stdout)
        cp_manifest = {x["name"]: x for x in json.loads((PROJECT / "packet/CHECKPOINT_MANIFEST.json").read_text())["files"]}
        if args.reuse_staged:
            r = ssh(args.ip, args.key, remote_hash_script(cp_manifest, f"{remote_root}/checkpoint"), timeout=1800)
        else:
            stream_tar(args.ip, args.key, PROJECT / "packet/candidate-v0.5.15", f"{remote_root}/.candidate.staging", 900)
            stream_tar(args.ip, args.key, PROJECT / "inputs/checkpoint", f"{remote_root}/.checkpoint.staging", 1800)
            r = ssh(args.ip, args.key, remote_hash_script(cp_manifest, f"{remote_root}/.checkpoint.staging"), timeout=1800)
        (out / "REMOTE_CHECKPOINT_HASH.stdout").write_text(r.stdout); (out / "REMOTE_CHECKPOINT_HASH.stderr").write_text(r.stderr)
        if r.returncode: raise RuntimeError("remote_checkpoint_hash_failed")
        if not args.reuse_staged:
            r = ssh(args.ip, args.key, f"set -e; rm -rf {remote_root}/checkpoint {remote_root}/candidate-v0.5.15; mv {remote_root}/.checkpoint.staging {remote_root}/checkpoint; mv {remote_root}/.candidate.staging {remote_root}/candidate-v0.5.15; chmod -R a-w {remote_root}/checkpoint {remote_root}/candidate-v0.5.15; find {remote_root}/checkpoint -maxdepth 1 -type f -printf '%f %s\\n'", timeout=120)
            (out / "REMOTE_FINALIZE.stdout").write_text(r.stdout); (out / "REMOTE_FINALIZE.stderr").write_text(r.stderr)
            if r.returncode: raise RuntimeError("remote_finalize_failed")
        if args.stage_packet:
            stream_tar(args.ip, args.key, PROJECT / "packet", f"{remote_root}/.packet.staging", 300)
            packet_manifest = {
                name.removeprefix("packet/"): value
                for name, value in json.loads((PROJECT / "PACKET_MANIFEST.json").read_text()).items()
                if name.startswith("packet/")
            }
            r = ssh(args.ip, args.key, remote_hash_script(packet_manifest, f"{remote_root}/.packet.staging"), timeout=300)
            (out / "REMOTE_PACKET_HASH.stdout").write_text(r.stdout); (out / "REMOTE_PACKET_HASH.stderr").write_text(r.stderr)
            if r.returncode: raise RuntimeError("remote_packet_hash_failed")
            expected = json.dumps(packet_manifest, sort_keys=True)
            reconcile = f'''python3 - <<'PY'
import hashlib, json, os, pathlib, shutil
root=pathlib.Path({remote_root!r})
staging=root/'.packet.staging'; target=root/'packet'
expected=json.loads({expected!r})
for name,item in expected.items():
    src=staging/name; dst=target/name
    h=hashlib.sha256(src.read_bytes()).hexdigest()
    if h != item['sha256'] or src.stat().st_size != item['bytes']:
        raise SystemExit('staging_mismatch:'+name)
    if dst.exists() and dst.stat().st_size == item['bytes'] and hashlib.sha256(dst.read_bytes()).hexdigest() == item['sha256']:
        continue
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp=dst.with_name(dst.name+'.repair-tmp')
    shutil.copyfile(src, tmp)
    os.chmod(tmp, 0o444)
    os.replace(tmp, dst)
for path in target.rglob('*'):
    if path.is_file(): os.chmod(path, 0o444)
print('REMOTE_PACKET_RECONCILE=PASS')
PY'''
            r = ssh(args.ip, args.key, packet_finalize_transport(remote_root, reconcile), timeout=120)
            (out / "REMOTE_PACKET_FINALIZE.stdout").write_text(r.stdout); (out / "REMOTE_PACKET_FINALIZE.stderr").write_text(r.stderr)
            if r.returncode: raise RuntimeError("remote_packet_finalize_failed")
        if args.endpoint_only and not args.reuse_server:
            r = ssh(args.ip, args.key, disk_repair_command(), timeout=600)
            (out / "DISK_REPAIR.stdout").write_text(r.stdout); (out / "DISK_REPAIR.stderr").write_text(r.stderr)
            if r.returncode: raise RuntimeError("disk_repair_failed")
            begin = "MANIFEST_BEGIN\n"
            end = "\nMANIFEST_END"
            if begin not in r.stdout or end not in r.stdout:
                raise RuntimeError("manifest_size_failed:markers_missing")
            raw_manifest = r.stdout.split(begin, 1)[1].split(end, 1)[0]
            try:
                manifest_document = json.loads(raw_manifest)
                manifest_bytes = compressed_bytes(manifest_document)
            except (json.JSONDecodeError, ManifestError) as error:
                (out / "RAW_MANIFEST_INSPECT_VERBOSE.json").write_text(raw_manifest)
                raise RuntimeError(f"manifest_size_failed:{error}") from error
            raw_path = out / "RAW_MANIFEST_INSPECT_VERBOSE.json"
            raw_path.write_text(raw_manifest)
            free_bytes = None
            for line in r.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 5 and fields[0].startswith("/dev/"):
                    try:
                        free_bytes = int(fields[3]) * 1024
                    except ValueError:
                        free_bytes = None
                    break
            if free_bytes is None:
                raise RuntimeError("manifest_size_failed:docker_free_bytes_missing")
            slack_bytes = 2 * 1024**3
            required_bytes = manifest_bytes + slack_bytes
            atomic(out / "MANIFEST_SIZE_RESULT.json", {
                "schema_version": 1,
                "image": IMAGE,
                "raw_manifest_sha256": sha256(raw_path),
                "compressed_bytes": manifest_bytes,
                "docker_free_bytes": free_bytes,
                "slack_bytes": slack_bytes,
                "required_free_bytes": required_bytes,
                "pass": free_bytes >= required_bytes,
            })
            if free_bytes < required_bytes:
                raise RuntimeError("insufficient_space_for_pinned_image")
        if args.reuse_server:
            r = ssh(args.ip, args.key, f"set -e; sudo -n docker inspect {CONTAINER} --format '{{{{json .Config}}}}'; curl -fsS --max-time 5 http://127.0.0.1:30000/v1/models", timeout=120)
        else:
            r = ssh(args.ip, args.key, f"set -e; sudo -n docker pull {IMAGE}; sudo -n docker rm -f {CONTAINER} >/dev/null 2>&1 || true; {launch_command().replace('docker ', 'sudo -n docker ')}; sudo -n docker inspect {CONTAINER} --format '{{{{json .Config}}}}'", timeout=1800)
        (out / "SERVER_START.stdout").write_text(r.stdout); (out / "SERVER_START.stderr").write_text(r.stderr)
        if r.returncode: raise RuntimeError("server_start_failed")
        if args.endpoint_only:
            ready = ssh(args.ip, args.key, "for i in $(seq 1 180); do curl -fsS --max-time 3 http://127.0.0.1:30000/v1/models >/dev/null && exit 0; sleep 5; done; exit 1", timeout=max(60, min(900, int(args.deadline_epoch - time.time()))))
            (out / "SERVER_READY.stdout").write_text(ready.stdout); (out / "SERVER_READY.stderr").write_text(ready.stderr)
            if ready.returncode: raise RuntimeError("server_readiness_failed")
            runner = f"set -o pipefail; mkdir -p {remote_root}/endpoint; sudo -n env UPSTREAM_REBASE_ROOT={remote_root}/candidate-v0.5.15 UPSTREAM_REBASE_OUT={remote_root}/endpoint UPSTREAM_REBASE_REQUESTS=791 UPSTREAM_REBASE_CONTAINER={CONTAINER} python3 {remote_root}/packet/h100_matched_runner.py"
            r = ssh(args.ip, args.key, runner, timeout=max(600, int(args.deadline_epoch - time.time())))
            (out / "ENDPOINT.stdout").write_text(r.stdout); (out / "ENDPOINT.stderr").write_text(r.stderr)
            r2 = ssh(args.ip, args.key, f"sudo -n docker logs {CONTAINER} 2>&1", timeout=120)
            (out / "SERVER.log").write_text(r2.stdout + r2.stderr)
            if r.returncode: raise RuntimeError(f"endpoint_failed:{r.returncode}:{r.stderr[-2000:]}")
            subprocess.run(["scp", "-q", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", f"glmrunner@{args.ip}:{remote_root}/endpoint/FINAL_TERMINAL.json", str(out / "ENDPOINT_FINAL_TERMINAL.json")], check=False, timeout=120)
            terminal.update({"endpoint": json.loads((out / "ENDPOINT_FINAL_TERMINAL.json").read_text()), "candidate_sample_consumed": True, "endpoint_sample_consumed": True})
            terminal["classification"] = "scientific_terminal"
        else:
            runner = f"set -o pipefail; mkdir -p {remote_root}/discriminator; sudo -n env UPSTREAM_REBASE_ROOT={remote_root}/candidate-v0.5.15 UPSTREAM_REBASE_OUT={remote_root}/discriminator UPSTREAM_REBASE_REQUESTS=171 UPSTREAM_REBASE_CONTAINER={CONTAINER} python3 {remote_root}/packet/h100_matched_runner.py"
            r = ssh(args.ip, args.key, runner, timeout=max(600, int(args.deadline_epoch - time.time())))
            (out / "DISCRIMINATOR.stdout").write_text(r.stdout); (out / "DISCRIMINATOR.stderr").write_text(r.stderr)
            r2 = ssh(args.ip, args.key, f"sudo -n docker logs {CONTAINER} 2>&1", timeout=120)
            (out / "SERVER.log").write_text(r2.stdout + r2.stderr)
            if r.returncode:
                raise RuntimeError(f"discriminator_failed:{r.returncode}:{r.stderr[-2000:]}")
            # Retrieve compact result and raw rows before any conditional arm.
            subprocess.run(["scp", "-q", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", f"glmrunner@{args.ip}:{remote_root}/discriminator/FINAL_TERMINAL.json", str(out / "FINAL_TERMINAL.json")], check=False, timeout=120)
            final = json.loads((out / "FINAL_TERMINAL.json").read_text())
            terminal.update({"first_arm": final, "candidate_sample_consumed": True})
            if final.get("endpoint_admitted") is True:
                ssh(args.ip, args.key, f"set -e; sudo -n docker rm -f {CONTAINER}; sudo -n docker run -d --name {CONTAINER} --gpus all --ipc=host --network=host -v {REMOTE}/checkpoint:/work/checkpoint:ro -v {REMOTE}/candidate-v0.5.15:/work/candidate-v0.5.15:ro {IMAGE} python3 -m sglang.launch_server " + " ".join(json.loads((PROJECT / "packet/candidate-v0.5.15/inputs/ngram-launch.json").read_text())["args"]), timeout=1200)
                r = ssh(args.ip, args.key, f"mkdir -p {remote_root}/endpoint; sudo -n env UPSTREAM_REBASE_ROOT={remote_root}/candidate-v0.5.15 UPSTREAM_REBASE_OUT={remote_root}/endpoint UPSTREAM_REBASE_REQUESTS=791 UPSTREAM_REBASE_CONTAINER={CONTAINER} python3 {remote_root}/packet/h100_matched_runner.py", timeout=max(600, int(args.deadline_epoch - time.time())))
                (out / "ENDPOINT.stdout").write_text(r.stdout); (out / "ENDPOINT.stderr").write_text(r.stderr)
                if r.returncode:
                    raise RuntimeError(f"endpoint_failed:{r.returncode}:{r.stderr[-2000:]}")
                subprocess.run(["scp", "-q", "-i", str(args.key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", "UserKnownHostsFile=/root/.config/nebius/glm-campaign/known_hosts", f"glmrunner@{args.ip}:{remote_root}/endpoint/FINAL_TERMINAL.json", str(out / "ENDPOINT_FINAL_TERMINAL.json")], check=False, timeout=120)
                terminal["endpoint"] = json.loads((out / "ENDPOINT_FINAL_TERMINAL.json").read_text())
            terminal["classification"] = "scientific_terminal"
    except Exception as exc:
        terminal.update({"classification": "typed_external_or_recoverable_failure", "error": repr(exc)})
    finally:
        terminal["finished_at"] = now(); terminal["heartbeat_events"] = events; atomic(out / "TERMINAL.json", terminal)
        stop.set(); hb.join(5)
        subprocess.run(["env", f"PYTHONPATH={FACTORY}", *POOL, "release", "--project", PROJECT_NAME, "--condition", "maintenance"], check=False, timeout=60)
    return 0 if terminal["classification"] == "scientific_terminal" else 2


if __name__ == "__main__":
    raise SystemExit(main())
