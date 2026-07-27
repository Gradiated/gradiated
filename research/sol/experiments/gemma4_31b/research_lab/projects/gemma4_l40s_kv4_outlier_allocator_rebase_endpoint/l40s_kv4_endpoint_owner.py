#!/usr/bin/env python3
"""One bounded, director-bound L40S owner for the fixed KV4-outlier c32 arm.

It is deliberately inert until a director supplies a registered bench, an SSH
identity, a digest-checked runtime image, and a project-local checkpoint
snapshot.  It never creates provider resources.
"""
from __future__ import annotations

import argparse, datetime as dt, hashlib, json, os, shutil, subprocess, threading, time, shlex
from pathlib import Path

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
POOL = ["env", "PYTHONPATH=/root/workspace/research/factory/src", "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
HANDSHAKE = "/root/workspace/research/factory/tools/repair-handshake"
PROJECT_ID = "gemma4_l40s_kv4_outlier_allocator_rebase_endpoint"
COMMIT = "c6a6200a1a778a799ba61c395ac292317f01ebc9"
MODEL = "google/gemma-4-31B-it"
MEM_FRACTION = "0.953"
LIFECYCLE_SECONDS = 2400

SOURCES = {
    "exact_c32_consumer.py": ("../gemma4_l40s_current_runtime_fp8_endpoint_rebase/exact_c32_consumer.py", "37f6d5be144a909557de6caca6c70c5db1706987a115a6e428fe7acb9e736e6d"),
    "WORKLOAD.json": ("../gemma4_prefill_cuda_graph_padding_rebase/inputs/workload/WORKLOAD.json", "7a05fa6218a5fbfd87744bca1ac491949ddd64bf0d58007b4d3569594f08225d"),
    "LAUNCH.json": ("../gemma4_prefill_cuda_graph_padding_rebase/inputs/workload/LAUNCH.json", "a48f6910df002c422543089685476fb9af845f957184f326ba0807b58029c1de"),
    "MODEL_CONFIG.json": ("../gemma4_prefill_cuda_graph_padding_rebase/inputs/workload/MODEL_CONFIG.json", "e967dd38bc5cfd38bd09a995a7bf4a754075df2b46aba68f7fbb5a791e6d8dd1"),
    "sglang_local_kv4_outlier.py": ("../gemma4_l40s_local_kv4_outlier_codesign/sglang_local_kv4_outlier.py", "16bd6477f1be675bbae83492f057fcb37496026ebf1d7ab9c43e9193d66b8163"),
    "local_kv4_outlier_cuda.cu": ("../gemma4_l40s_local_kv4_outlier_codesign/local_kv4_outlier_cuda.cu", "6d8a84bd5ef5a1fbacbd95a99e1aa7c180b8d39e590ee1fd657d2da51e4e3944"),
    "local_kv4_outlier_bindings.cpp": ("../gemma4_l40s_local_kv4_outlier_codesign/local_kv4_outlier_bindings.cpp", "903ccfd27fb74e21d498aa5c98ce7c179f20e315c4963ab3be1162983aaaebd6"),
}

def now(): return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()
def atomic(path, value):
    tmp = path.with_suffix(path.suffix + ".part"); tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n"); os.replace(tmp, path)
def run(args, **kw): return subprocess.run(args, text=True, capture_output=True, check=False, **kw)
def pool(*args, **kw):
    r = run([*POOL, *args], **kw)
    if r.returncode: raise RuntimeError(f"gpu_pool_{args[0]}:{r.stderr[-800:]}")
    return json.loads(r.stdout)
def remote(args, script, timeout):
    return run(["ssh", "-i", str(args.identity), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={args.known_hosts}", f"{args.ssh_user}@{args.ssh_host}", "bash", "-s"], input=script, timeout=timeout)
def scp(args, source, target, timeout):
    r = run(["scp", "-q", "-i", str(args.identity), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={args.known_hosts}", str(source), f"{args.ssh_user}@{args.ssh_host}:{target}"], timeout=timeout)
    if r.returncode: raise RuntimeError(f"scp:{source.name}:{r.stderr[-500:]}")

def freeze_packet():
    packet = PROJECT / "packet"
    manifest = packet / "PACKET_MANIFEST.json"
    if manifest.exists():
        data = json.loads(manifest.read_text())
        if all((packet / name).is_file() and digest(packet / name) == row["sha256"] for name, row in data["files"].items()): return packet, data
        raise RuntimeError("project_packet_digest_mismatch")
    tmp = PROJECT / ".packet.part"
    if tmp.exists(): shutil.rmtree(tmp)
    tmp.mkdir()
    files = {}
    for name, (relative, expected) in SOURCES.items():
        source = (PROJECT / relative).resolve()
        if digest(source) != expected: raise RuntimeError(f"upstream_binding_mismatch:{name}")
        shutil.copyfile(source, tmp / name)
        os.chmod(tmp / name, 0o444)
        files[name] = {"sha256": expected, "bytes": (tmp / name).stat().st_size, "source": str(source)}
    launch = json.loads((tmp / "LAUNCH.json").read_text()); values = launch["args"]
    i = values.index("--mem-fraction-static") + 1
    if values[i] != "0.85": raise RuntimeError("inherited_launch_contract_changed")
    values[i] = MEM_FRACTION
    (tmp / "LAUNCH.json").write_text(json.dumps(launch, indent=2, sort_keys=True) + "\n")
    os.chmod(tmp / "LAUNCH.json", 0o444)
    files["LAUNCH.json"]["sha256"] = digest(tmp / "LAUNCH.json"); files["LAUNCH.json"]["bytes"] = (tmp / "LAUNCH.json").stat().st_size
    atomic(tmp / "PACKET_MANIFEST.json", {"schema_version": 1, "files": files, "fixed_mem_fraction_static": MEM_FRACTION, "runtime_commit": COMMIT})
    os.replace(tmp, packet)
    return packet, json.loads((packet / "PACKET_MANIFEST.json").read_text())

def checkpoint_manifest(checkpoint, manifest):
    checkpoint, manifest = checkpoint.resolve(), manifest.resolve()
    if PROJECT not in checkpoint.parents or PROJECT not in manifest.parents: raise RuntimeError("checkpoint_must_be_project_local")
    rows = json.loads(manifest.read_text())["files"]
    for row in rows:
        p = checkpoint / row["path"]
        if not p.is_file() or p.stat().st_size != row["bytes"] or digest(p) != row["sha256"]: raise RuntimeError(f"checkpoint_snapshot_mismatch:{row['path']}")
    return rows

def reconcile(args, local, remote_root, identity, deadline):
    target = f"{remote_root}/{local.name}"; q = "'"
    probe = remote(args, f"set -eu; mkdir -p {remote_root}; test -f {target} && test \"$(sha256sum {target}|cut -d' ' -f1)\" = {identity['sha256']} && test \"$(stat -c %s {target})\" = {identity['bytes']} && exit 0; exit 9", min(120, max(30, int(deadline-time.time()))))
    if probe.returncode == 0: return
    partial = target + ".part"; scp(args, local, partial, max(60, int(deadline-time.time()-300)))
    final = remote(args, f"set -eu; test \"$(sha256sum {partial}|cut -d' ' -f1)\" = {identity['sha256']}; test \"$(stat -c %s {partial})\" = {identity['bytes']}; chmod 0444 {partial}; mv -f {partial} {target}", 180)
    if final.returncode: raise RuntimeError(f"remote_finalize_failed:{local.name}:{final.stderr[-300:]}")

def heartbeat(stop, bench, events):
    while not stop.wait(25):
        try: pool("heartbeat", "--project", PROJECT_ID, "--bench", bench); events.append({"at": now(), "kind": "heartbeat", "pass": True})
        except Exception as e: events.append({"at": now(), "kind": "heartbeat", "pass": False, "error": repr(e)})

def main():
    p = argparse.ArgumentParser(); p.add_argument("--bench", required=True); p.add_argument("--ssh-host", required=True); p.add_argument("--ssh-user", required=True); p.add_argument("--identity", type=Path, required=True); p.add_argument("--known-hosts", type=Path, required=True); p.add_argument("--checkpoint", type=Path, required=True); p.add_argument("--checkpoint-manifest", type=Path, required=True); p.add_argument("--image", required=True); p.add_argument("--artifact-root", type=Path, required=True); p.add_argument("--deadline-seconds", type=int, default=LIFECYCLE_SECONDS); args = p.parse_args()
    if args.deadline_seconds != LIFECYCLE_SECONDS or args.ssh_user != "glmrunner" or args.artifact_root.exists() or not args.identity.is_file() or not args.known_hosts.is_file(): raise SystemExit("director_bound_owner_precondition_failed")
    packet, packet_manifest = freeze_packet(); checkpoints = checkpoint_manifest(args.checkpoint, args.checkpoint_manifest)
    started, deadline = time.time(), time.time() + args.deadline_seconds; args.artifact_root.mkdir(parents=True); events=[]; claim=None; stop=threading.Event(); classification="pre_science_failure"; consumed=False
    try:
        claim = pool("claim", "--project", PROJECT_ID, "--bench", args.bench, "--model", MODEL, "--lease-seconds", str(args.deadline_seconds)); bench, claimed_at = claim["id"], claim["claim"]["claimed_at"]
        if bench != args.bench or claim.get("accelerator") != "nvidia-l40s": raise RuntimeError("director_bound_l40s_mismatch")
        events.append({"at":now(),"kind":"claim","bench":bench,"claimed_at":claimed_at}); t=threading.Thread(target=heartbeat,args=(stop,bench,events),daemon=True); t.start()
        pre = remote(args, "set -eu; nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader,nounits; sudo -n docker version --format '{{.Server.Version}}'", 120); (args.artifact_root/"preflight.stdout").write_text(pre.stdout); (args.artifact_root/"preflight.stderr").write_text(pre.stderr)
        if pre.returncode or "L40S" not in pre.stdout or "8.9" not in pre.stdout: raise RuntimeError("l40s_sm89_preflight_failed")
        root=f"/home/glmrunner/gemma4-kv4-outlier-{claimed_at.replace(':','-')}"; remote(args, f"set -eu; mkdir -p {root}/packet {root}/checkpoint {root}/output", 60)
        for name,row in packet_manifest["files"].items(): reconcile(args, packet/name, f"{root}/packet", row, deadline)
        for row in checkpoints: reconcile(args, args.checkpoint/row["path"], f"{root}/checkpoint", row, deadline)
        launch_args = json.loads((packet / "LAUNCH.json").read_text())["args"]
        launch_code = "from sglang_local_kv4_outlier import install_current_runtime; install_current_runtime(); import runpy; runpy.run_module('sglang.launch_server', run_name='__main__')"
        command = "cd /work/packet && python3 -c " + shlex.quote(launch_code) + " " + " ".join(shlex.quote(x) for x in launch_args)
        start_script = f"""set -euo pipefail
sudo -n docker pull {shlex.quote(args.image)}
test \"$(sudo -n docker image inspect {shlex.quote(args.image)} --format '{{{{index .Config.Labels \"org.opencontainers.image.revision\"}}}}')\" = {COMMIT}
sudo -n docker rm -f gemma4-kv4-outlier >/dev/null 2>&1 || true
sudo -n docker run -d --name gemma4-kv4-outlier --gpus all --ipc=host --network=host -v {root}/checkpoint:/work/checkpoint:ro -v {root}/packet:/work/packet:ro {shlex.quote(args.image)} bash -lc {shlex.quote(command)}
"""
        start = remote(args, start_script, min(900,max(120,int(deadline-time.time()-600))))
        (args.artifact_root/"server-start.stdout").write_text(start.stdout); (args.artifact_root/"server-start.stderr").write_text(start.stderr)
        if start.returncode: raise RuntimeError("runtime_image_or_server_start_failed")
        ready=False
        for _ in range(120):
            health=remote(args,"curl -fsS --max-time 3 http://127.0.0.1:30000/v1/models",20)
            inspect=remote(args,"sudo -n docker inspect -f '{{.State.Running}}' gemma4-kv4-outlier",20)
            if health.returncode==0: ready=True; break
            if inspect.stdout.strip() != "true": raise RuntimeError("server_exited_before_ready")
            time.sleep(5)
        if not ready: raise RuntimeError("server_readiness_deadline")
        out=f"{root}/output/attempt-1"; worker=remote(args,f"set -o pipefail; rm -rf {out}; mkdir -p {out}; python3 {root}/packet/exact_c32_consumer.py --output {out}/result --workload {root}/packet/WORKLOAD.json --arm kv4-outlier-l40s-fixed-0953 >{out}/consumer.stdout 2>{out}/consumer.stderr; rc=$?; sudo -n docker logs gemma4-kv4-outlier >{out}/server.log 2>&1 || true; exit $rc", max(180,int(deadline-time.time()-180)))
        fetch=run(["scp","-r","-q","-i",str(args.identity),"-o","BatchMode=yes","-o","StrictHostKeyChecking=yes","-o",f"UserKnownHostsFile={args.known_hosts}",f"{args.ssh_user}@{args.ssh_host}:{out}",str(args.artifact_root/"attempt-1")],timeout=180); atomic(args.artifact_root/"retrieval.json",{"returncode":fetch.returncode,"stderr":fetch.stderr[-1000:]})
        science=(args.artifact_root/"attempt-1/result/SCIENCE_STARTED.json").exists(); terminal=args.artifact_root/"attempt-1/result/TERMINAL.json"; consumed=science
        if not terminal.exists(): raise RuntimeError("terminal_retrieval_or_consumer_defect")
        measured=json.loads(terminal.read_text()); valid=worker.returncode==0 and measured.get("sample_consumed") is True
        classification="scientific_pass" if valid and measured.get("pass") else "scientific_negative"; atomic(args.artifact_root/"MEASURED_TERMINAL.json",measured)
    except Exception as e:
        atomic(args.artifact_root/"OWNER_ERROR.json",{"at":now(),"error":repr(e),"sample_consumed":consumed})
        if claim and not consumed and time.time() < deadline-120:
            repair_deadline=dt.datetime.fromtimestamp(deadline-120,dt.timezone.utc).isoformat().replace("+00:00","Z")
            subprocess.run([HANDSHAKE,"ready","--root",str(args.artifact_root),"--repair-id",f"{claim['id']}-{int(started)}","--deadline",repair_deadline,"--failure-kind","ordinary_pre_science_owner_defect","--diagnostic",str(args.artifact_root/"OWNER_ERROR.json"),"--retry-scope","owner_startup_or_retrieval_only"],check=False,timeout=30)
            wait = subprocess.run([HANDSHAKE, "wait", "--root", str(args.artifact_root), "--repair-id", f"{claim['id']}-{int(started)}", "--poll-seconds", "5"], timeout=max(30, int(deadline-time.time()-90)), capture_output=True, text=True)
            atomic(args.artifact_root / "REPAIR_WAIT.json", {"returncode": wait.returncode, "stdout": wait.stdout[-2000:], "stderr": wait.stderr[-2000:]})
            classification = "absolute_repair_deadline" if wait.returncode else "repair_request_requires_relaunch"
        classification="typed_owner_failure"
    finally:
        stop.set()
        if claim:
            contents=args.artifact_root/"resident_contents.json"; atomic(contents,{"model":MODEL,"runtime_commit":COMMIT,"packet_manifest_sha256":digest(packet/"PACKET_MANIFEST.json"),"classification":classification,"sample_consumed":consumed})
            condition="ready" if classification.startswith("scientific") else "maintenance"
            release=pool("release","--project",PROJECT_ID,"--bench",claim["id"],"--expected-claimed-at",claim["claim"]["claimed_at"],"--contents",str(contents),"--condition",condition)
            atomic(args.artifact_root/"OWNER_TERMINAL.json",{"classification":classification,"sample_consumed":consumed,"events":events,"release":release,"started_at":started,"deadline_at":deadline})
    return 0 if classification=="scientific_pass" else 2
if __name__ == "__main__": raise SystemExit(main())
