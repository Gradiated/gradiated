#!/usr/bin/env python3
"""Repair-aware outer owner for the one admitted checkpoint-free L40S run."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import threading
import time


ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = ROOT.name
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
MAX_SECONDS = 90 * 60
FACTORY = Path("/root/workspace/research/factory/src")
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
HANDSHAKE = Path("/root/workspace/research/factory/tools/repair-handshake")
MANIFEST = ROOT / "L40S_DUAL_KV4_SM89_PACKET_MANIFEST.json"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def command(argv: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False, **kwargs)


def pool(*args: str, timeout: int = 60) -> dict:
    result = command(["env", f"PYTHONPATH={FACTORY}", *POOL, *args], timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"gpu_pool_{args[0]}:{result.stderr[-1000:]}")
    return json.loads(result.stdout)


def ssh_prefix(claim: dict) -> list[str]:
    resource = claim["resource"]
    host, user = resource.get("public_ipv4"), resource.get("ssh_user")
    identity, known = resource.get("identity_file"), resource.get("known_hosts_namespace")
    if user != "glmrunner" or not all(isinstance(x, str) and x for x in (host, identity, known)):
        raise RuntimeError("registered_l40s_missing_explicit_glmrunner_ssh_identity")
    if not Path(identity).is_file() or not Path(known).is_file():
        raise RuntimeError("registered_l40s_ssh_identity_not_present_on_controller")
    return ["ssh", "-i", identity, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}", "-o", "ConnectTimeout=15", f"{user}@{host}"]


def remote(prefix: list[str], script: str, timeout: int) -> subprocess.CompletedProcess[str]:
    return command([*prefix, "bash", "-s"], input=script, timeout=timeout)


def scp(prefix: list[str], source: str, target: str, timeout: int, remote_source: bool = False) -> subprocess.CompletedProcess[str]:
    host = prefix[-1]
    options = prefix[1:-1]
    left, right = (f"{host}:{source}", target) if remote_source else (source, f"{host}:{target}")
    return command(["scp", "-q", *options, left, right], timeout=timeout)


def remaining(deadline: float, reserve: int = 0) -> int:
    return max(0, int(deadline - time.time() - reserve))


def load_manifest() -> dict:
    value = json.loads(MANIFEST.read_text())
    files = value.get("files")
    if value.get("schema_version") != 1 or not isinstance(files, list):
        raise RuntimeError("packet_manifest_schema_invalid")
    for row in files:
        path = ROOT / row["path"]
        if not path.is_file() or path.stat().st_size != row["bytes"] or digest(path) != row["sha256"]:
            raise RuntimeError(f"packet_member_identity_mismatch:{row['path']}")
    return value


def stage(prefix: list[str], remote_root: str, manifest: dict, deadline: float) -> None:
    for row in manifest["files"]:
        local, remote_name = ROOT / row["path"], f"{remote_root}/packet/{row['path']}"
        probe = remote(prefix, f"set -e; mkdir -p {shlex.quote(str(Path(remote_name).parent))}; test -f {shlex.quote(remote_name)} && test \"$(sha256sum {shlex.quote(remote_name)} | cut -d' ' -f1)\" = {shlex.quote(row['sha256'])}", min(90, remaining(deadline, 300)))
        if probe.returncode == 0:
            continue
        partial = remote_name + ".part"
        copied = scp(prefix, str(local), partial, min(300, remaining(deadline, 300)))
        if copied.returncode:
            raise RuntimeError(f"packet_transfer_failed:{row['path']}:{copied.stderr[-600:]}")
        finalized = remote(prefix, f"set -e; test \"$(stat -c %s {shlex.quote(partial)})\" = {row['bytes']}; test \"$(sha256sum {shlex.quote(partial)} | cut -d' ' -f1)\" = {shlex.quote(row['sha256'])}; chmod 0444 {shlex.quote(partial)}; mv -f {shlex.quote(partial)} {shlex.quote(remote_name)}", min(120, remaining(deadline, 240)))
        if finalized.returncode:
            raise RuntimeError(f"packet_finalize_failed:{row['path']}:{finalized.stderr[-600:]}")


def heartbeat(stop: threading.Event, bench: str, events: list[dict]) -> None:
    while not stop.wait(25):
        try:
            result = pool("heartbeat", "--project", PROJECT, "--bench", bench)
            events.append({"at": now(), "kind": "heartbeat", "lease_until_utc": result["claim"]["lease_until_utc"]})
        except Exception as error:
            events.append({"at": now(), "kind": "heartbeat_error", "error": repr(error)})


def retrieve(prefix: list[str], remote_attempt: str, local: Path) -> dict:
    local.mkdir(parents=True, exist_ok=True)
    names = ("runner.stdout", "runner.stderr", "runner.exit", "LAUNCH_ATTEMPTED.json", "result/SCIENCE_STARTED.json", "result/ARM_FIRST_CALL_MARKERS.jsonl", "result/LOCAL_ROWS.json", "result/GLOBAL_ROWS.json", "result/TERMINAL.json", "result/INVOCATION_COMPLETE.json")
    rows = []
    for name in names:
        target = local / name.replace("/", "__")
        fetched = scp(prefix, f"{remote_attempt}/{name}", str(target) + ".part", 120, remote_source=True)
        if fetched.returncode == 0:
            os.replace(str(target) + ".part", target)
            rows.append({"path": name, "sha256": digest(target), "bytes": target.stat().st_size})
    value = {"schema_version": 1, "files": rows, "raw_present": all(n in {r['path'] for r in rows} for n in names[:3]), "science_started": any(r["path"].endswith("SCIENCE_STARTED.json") for r in rows), "terminal_present": any(r["path"].endswith("TERMINAL.json") for r in rows)}
    atomic(local / "RETRIEVAL.json", value)
    return value


def invoke(prefix: list[str], remote_root: str, attempt_id: str, deadline: float) -> str:
    attempt = f"{remote_root}/{attempt_id}"
    script = f"set +e; mkdir -p {shlex.quote(attempt)}; printf '%s\\n' '{{\"state\":\"launch_attempted\"}}' > {shlex.quote(attempt)}/LAUNCH_ATTEMPTED.json; sudo -n docker run --rm --gpus all --ipc=host --user \"$(id -u):$(id -g)\" -e PYTHONUNBUFFERED=1 -e TORCH_EXTENSIONS_DIR=/work/state/extensions -v {shlex.quote(remote_root)}:/work/state --entrypoint /bin/bash {shlex.quote(IMAGE)} -lc {shlex.quote(f'cd /work/state/packet && python3 sm89_dual_kv4_runner.py --artifact-root /work/state/{attempt_id}/result')} >{shlex.quote(attempt)}/runner.stdout 2>{shlex.quote(attempt)}/runner.stderr; rc=$?; echo $rc > {shlex.quote(attempt)}/runner.exit; exit $rc"
    remote(prefix, script, min(2700, remaining(deadline, 180)))
    return attempt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--deadline-seconds", type=int, default=MAX_SECONDS)
    args = parser.parse_args()
    if not 0 < args.deadline_seconds <= MAX_SECONDS or args.artifact_root.exists():
        raise SystemExit("invalid_owner_deadline_or_existing_artifact_root")
    manifest = load_manifest()
    preview = pool("show", "--bench", args.bench)
    if preview.get("accelerator") != "nvidia-l40s":
        raise SystemExit("director_bound_bench_is_not_l40s")
    prefix = ssh_prefix(preview)
    started, deadline = time.time(), time.time() + args.deadline_seconds
    args.artifact_root.mkdir(parents=True)
    claim = pool("claim", "--project", PROJECT, "--bench", args.bench, "--accelerator", "nvidia-l40s", "--lease-seconds", str(args.deadline_seconds))
    events = [{"at": now(), "kind": "claim", "claimed_at": claim["claim"]["claimed_at"]}]
    stop = threading.Event(); thread = threading.Thread(target=heartbeat, args=(stop, claim["id"], events), daemon=True); thread.start()
    remote_root = f"/home/glmrunner/gemma4-dual-kv4-{claim['claim']['claimed_at'].replace(':', '-')}"
    classification, release = "unknown_retained_boundary", None
    try:
        preflight = remote(prefix, "set -e; nvidia-smi --query-gpu=name,compute_cap,memory.total --format=csv,noheader,nounits; sudo -n docker version --format '{{.Server.Version}}'", min(120, remaining(deadline, 300)))
        (args.artifact_root / "preflight.stdout").write_text(preflight.stdout); (args.artifact_root / "preflight.stderr").write_text(preflight.stderr)
        if preflight.returncode or "L40S" not in preflight.stdout or "8.9" not in preflight.stdout:
            classification = "unsafe_or_incompatible_guest"; raise RuntimeError(classification)
        image = remote(prefix, f"set +e; sudo -n docker image inspect {shlex.quote(IMAGE)} >/dev/null || sudo -n docker pull {shlex.quote(IMAGE)}; sudo -n docker image inspect {shlex.quote(IMAGE)} >/dev/null", min(720, remaining(deadline, 600)))
        if image.returncode: raise RuntimeError(f"image_identity_or_pull_failed:{image.stderr[-800:]}")
        stage(prefix, remote_root, manifest, deadline)
        attempt = invoke(prefix, remote_root, "attempt-0", deadline)
        retrieval = retrieve(prefix, attempt, args.artifact_root / "attempt-0")
        if retrieval["terminal_present"] and retrieval["science_started"]:
            classification = "scientific_terminal_retrieved"
            contents = args.artifact_root / "BENCH_CONTENTS.json"; atomic(contents, {"project": PROJECT, "image": IMAGE, "checkpoint": "none", "state": "packet_and_extension_cache_retained", "result": classification})
            release = pool("release", "--project", PROJECT, "--bench", claim["id"], "--expected-claimed-at", claim["claim"]["claimed_at"], "--contents", str(contents), "--condition", "ready")
        else:
            diagnostic = args.artifact_root / "attempt-0" / "RETRIEVAL.json"
            repair_deadline = dt.datetime.fromtimestamp(deadline - 120, dt.timezone.utc).isoformat().replace("+00:00", "Z")
            ready = command([str(HANDSHAKE), "ready", "--root", str(args.artifact_root), "--repair-id", "g1", "--deadline", repair_deadline, "--failure-kind", "ordinary_launcher_compile_api_or_retrieval_defect", "--diagnostic", str(diagnostic), "--retry-scope", "full_unconsumed_or_retrieval_only"], timeout=30)
            if ready.returncode:
                raise RuntimeError(f"repair_ready_failed:{ready.stderr[-600:]}")
            waited = command([str(HANDSHAKE), "wait", "--root", str(args.artifact_root), "--repair-id", "g1", "--poll-seconds", "3"], timeout=max(1, remaining(deadline, 90)))
            if waited.returncode == 0 and json.loads(waited.stdout).get("state") == "requested":
                events.append({"at": now(), "kind": "repair_request_consumed", "repair_id": "g1"})
                repaired = invoke(prefix, remote_root, "attempt-1", deadline)
                repaired_retrieval = retrieve(prefix, repaired, args.artifact_root / "attempt-1")
                if repaired_retrieval["terminal_present"] and repaired_retrieval["science_started"]:
                    classification = "scientific_terminal_retrieved_after_repair"
                    contents = args.artifact_root / "BENCH_CONTENTS.json"; atomic(contents, {"project": PROJECT, "image": IMAGE, "checkpoint": "none", "state": "packet_and_extension_cache_retained", "result": classification})
                    release = pool("release", "--project", PROJECT, "--bench", claim["id"], "--expected-claimed-at", claim["claim"]["claimed_at"], "--contents", str(contents), "--condition", "ready")
                else:
                    classification = "repair_attempt_unretrieved_or_uninterpretable"
            else:
                classification = "repair_deadline_expired_retained_claim"
            if release is None:
                contents = args.artifact_root / "BENCH_CONTENTS.json"; atomic(contents, {"project": PROJECT, "image": IMAGE, "checkpoint": "none", "state": "repair diagnostic and packet retained", "result": classification})
                release = pool("release", "--project", PROJECT, "--bench", claim["id"], "--expected-claimed-at", claim["claim"]["claimed_at"], "--contents", str(contents), "--condition", "maintenance")
    except Exception as error:
        events.append({"at": now(), "kind": "owner_error", "error": repr(error)})
    finally:
        stop.set(); thread.join(timeout=2)
        terminal = {"schema_version": 1, "classification": classification, "claim": {"bench": claim["id"], "claimed_at": claim["claim"]["claimed_at"], "claim_seconds": max(0, time.time()-started), "hourly_rate_usd": claim["hourly_cost_usd"]}, "events": events, "release": release, "absolute_deadline_epoch": deadline}
        atomic(args.artifact_root / "OWNER_TERMINAL.json", terminal)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
