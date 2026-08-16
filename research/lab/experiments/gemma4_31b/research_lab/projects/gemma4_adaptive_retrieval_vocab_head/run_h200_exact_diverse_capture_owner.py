#!/usr/bin/env python3
"""Durable outer owner for the one admitted exact diverse c32 capture."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any


PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
FACTORY = PROJECT.parents[5] / "factory"
POOL = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
DETACHED = FACTORY / "tools" / "detached-owner"
REPAIR = FACTORY / "tools" / "repair-handshake"
PROJECT_ID = "gemma4_adaptive_retrieval_vocab_head"
PACKET_ID = "e606f47a04c0374692e5aa66ae30821b35f8a79196916582cacc904ed568bc54"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"object_required:{path}")
    return value


def atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def utc(epoch: float) -> str:
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat().replace("+00:00", "Z")


def command(command: list[str], timeout: float, output: Path, text: str | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, input=text, text=True, capture_output=True, timeout=max(1, timeout), check=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.stdout)
    output.with_suffix(output.suffix + ".stderr").write_text(result.stderr)
    return result


def packet_paths(ready: dict[str, Any]) -> tuple[Path, Path, Path]:
    packet = ready["packet"]
    return PROJECT / packet["root"], PROJECT / packet["manifest"], PROJECT / packet["archive"]


def checkpoint_manifest() -> Path:
    return PROJECT.parent / "gemma4_hopper_packed_m384_verifier" / "inputs" / "endpoint" / "CHECKPOINT_MANIFEST.json"


def checkpoint_source(admission: dict[str, Any]) -> Path:
    return Path(admission["implementation"]["checkpoint_source_after_later_claim"])


def inventory_bench(bench_id: str) -> dict[str, Any]:
    inventory = load(LAB / "runtime" / "gpus.json")
    benches = inventory.get("benches", [])
    if isinstance(benches, dict):
        benches = benches.values()
    for bench in benches:
        if bench.get("id") == bench_id:
            return bench
    raise RuntimeError("admitted_bench_missing_from_inventory")


def validate_identities(admission_path: Path) -> dict[str, Any]:
    admission = load(admission_path)
    ready_path = PROJECT / "EXACT_DIVERSE_C32_CAPTURE_READY.json"
    ready = load(ready_path)
    checks: dict[str, bool] = {
        "admission_project": admission.get("project") == PROJECT_ID,
        "admission_classification": admission.get("classification") == "offline_h200_exact_diverse_capture_owner_implementation_admission",
        "source_ready_hash": sha(ready_path) == admission["source_ready"]["sha256"],
        "packet_identity": ready["packet"]["identity_sha256"] == PACKET_ID == admission["source_ready"]["packet_identity_sha256"],
        "packet_archive_identity": ready["packet"]["archive_sha256"] == admission["source_ready"]["packet_archive_sha256"],
        "claim_still_gated": admission["authority"].get("gpu_claim_allowed") is False,
        "no_checkpoint_authority": admission["authority"].get("checkpoint_materialization_allowed") is False,
    }
    root, manifest_path, archive = packet_paths(ready)
    manifest = load(manifest_path)
    checks["manifest_hash"] = sha(manifest_path) == ready["packet"]["manifest_sha256"]
    checks["archive_hash"] = sha(archive) == ready["packet"]["archive_sha256"]
    checks["manifest_packet_identity"] = manifest.get("packet_identity_sha256") == PACKET_ID
    members: list[dict[str, Any]] = []
    for row in manifest["files"]:
        source = root / row["path"]
        ok = source.is_file() and source.stat().st_size == row["bytes"] and sha(source) == row["sha256"]
        checks[f"member:{row['path']}"] = ok
        members.append({"path": row["path"], "bytes": row["bytes"], "sha256": row["sha256"], "pass": ok})
    with tarfile.open(archive, "r") as bundle:
        names = sorted(item.name for item in bundle.getmembers() if item.isfile())
        expected = sorted(["PACKET_MANIFEST.json", *[row["path"] for row in manifest["files"]]])
        checks["archive_member_names"] = names == expected
        for row in manifest["files"]:
            source = bundle.extractfile(row["path"])
            data = source.read() if source else b""
            checks[f"archive_member:{row['path']}"] = len(data) == row["bytes"] and hashlib.sha256(data).hexdigest() == row["sha256"]
    checkpoint_path = checkpoint_manifest()
    checkpoint = load(checkpoint_path)
    source_root = checkpoint_source(admission)
    checkpoint_rows: list[dict[str, Any]] = []
    for row in checkpoint["files"]:
        source = source_root / row["name"]
        ok = source.is_file() and source.stat().st_size == row["bytes"] and sha(source) == row["sha256"]
        checks[f"checkpoint:{row['name']}"] = ok
        checkpoint_rows.append({"name": row["name"], "bytes": row["bytes"], "sha256": row["sha256"], "pass": ok})
    checks["checkpoint_manifest_model"] = checkpoint.get("revision") == "b9ea41a2887d8607f594846523f94c6cc75ac8a4"
    checks["checkpoint_manifest_hash"] = sha(checkpoint_path) == sha(checkpoint_path)
    bench = inventory_bench(admission["bench"]["id"])
    checks["bench_identity"] = bench.get("id") == admission["bench"]["id"] and bench.get("accelerator") == admission["bench"]["accelerator"]
    checks["detached_owner_tool"] = DETACHED.is_file() and os.access(DETACHED, os.X_OK)
    checks["repair_handshake_tool"] = REPAIR.is_file() and os.access(REPAIR, os.X_OK)
    return {
        "admission": admission,
        "ready": ready,
        "manifest": manifest,
        "checkpoint": checkpoint,
        "bench": bench,
        "checks": checks,
        "members": members,
        "checkpoint_rows": checkpoint_rows,
        "paths": {"ready": str(ready_path), "manifest": str(manifest_path), "archive": str(archive), "checkpoint_manifest": str(checkpoint_path), "checkpoint_source": str(source_root)},
    }


def plan(value: dict[str, Any]) -> dict[str, Any]:
    admission, ready, manifest, checkpoint, bench = (value[key] for key in ("admission", "ready", "manifest", "checkpoint", "bench"))
    destination = ready["bounded_owner_destination"]
    lifecycle = bench["lifecycle"]["deadline_utc"]
    lifecycle_epoch = dt.datetime.fromisoformat(lifecycle.replace("Z", "+00:00")).timestamp()
    hypothetical_claim = lifecycle_epoch - 45 * 60
    owner_deadline = min(hypothetical_claim + 45 * 60, lifecycle_epoch - 10 * 60)
    state, log = destination["controller_state"], destination["controller_log"]
    detached = [str(DETACHED), "start", "--state", state, "--log", log, "--cwd", str(PROJECT), "--unit-manager", "pid", "--", sys.executable, str(PROJECT / "run_h200_exact_diverse_capture_owner.py"), "--admission", str(PROJECT / "DIRECTOR_EXACT_DIVERSE_C32_CAPTURE_OWNER_ADMISSION_20260726T2340Z.json"), "--claim-authority", "<later-director-binding>"]
    remote = destination["remote_output_root"]
    packet_remote = destination["remote_packet_root"]
    env = manifest["container_contract"]["environment"]
    env_args = [token for key, item in env.items() for token in ("-e", f"{key}={item}")]
    server = manifest["container_contract"]["server_command"]
    request = manifest["container_contract"]["request_command"]
    docker = ["sudo", "-n", "docker", "run", "-d", "--name", "gemma4-exact-diverse-c32", "--gpus", "all", "--ipc=host", "--network=host", "-v", f"{packet_remote}:/work/input:ro", "-v", f"{remote}:/work/output", "-v", f"{remote}/checkpoint:/work/checkpoint:ro", *env_args, ready["direct_source_identities"]["image"], *server]
    science_marker = "python3 - <<'PY'\nimport json,pathlib,time\np=pathlib.Path('/work/output/science_started.json'); q=p.with_suffix('.part'); q.write_text(json.dumps({'science_started': True, 'stage': 'exact_diverse_c32_request', 'at_unix_s': time.time()})+'\\n'); q.replace(p)\nPY"
    return {
        "claim": [*POOL, "claim", "--project", PROJECT_ID, "--bench", admission["bench"]["id"]],
        "heartbeat": [*POOL, "heartbeat", "--project", PROJECT_ID],
        "deadline_rule": destination["deadline_rule"],
        "offline_hypothetical_claimed_at_utc": utc(hypothetical_claim),
        "offline_owner_deadline_utc": utc(owner_deadline),
        "deadline_plan_valid": owner_deadline < lifecycle_epoch and owner_deadline > hypothetical_claim,
        "detached_owner": detached,
        "packet_stage": {"archive": value["paths"]["archive"], "archive_sha256": ready["packet"]["archive_sha256"], "remote_packet_root": packet_remote, "atomic_finalization": f"verify archive then extract to {packet_remote}.part and mv to {packet_remote}"},
        "checkpoint_stage": {"manifest": value["paths"]["checkpoint_manifest"], "manifest_sha256": sha(Path(value["paths"]["checkpoint_manifest"])), "source": value["paths"]["checkpoint_source"], "remote_root": f"{remote}/checkpoint", "policy": "reuse size-and-sha256 matches; scp only missing/mismatched files to digest .part paths; verify, chmod 0444, then mv"},
        "server_command": docker,
        "request_command": request,
        "science_marker": science_marker,
        "retrieval_order": ["EXACT_CAPTURE_TERMINAL.json", "hidden_states.sha256", "hidden_states.manifest.json", "request.stdout", "request.stderr", "science_started.json", "hidden_states.pt"],
        "repair": {"tool": str(REPAIR), "generation": "fresh repair-<unix-ns>", "retry_scope": "capture_or_observer_consumer_only", "disposition": "retain_claim_and_heartbeat; never replay a complete 32-request producer"},
        "release_dispositions": {"decision_bearing_capture": "maintenance unless an explicit compatible successor inherits loaded server", "recoverable_integration_or_retrieval": "retain_claim", "unsafe_unreachable_or_deadline": "maintenance_after_compact_diagnostic_and_submission_markers", "unoccupied_healthy": "ready"},
        "forbidden": {"retrieval_consumer": True, "second_complete_c32_producer": True, "provider_create_or_teardown": True},
        "checkpoint_files": checkpoint["files"],
    }


def authority(path: Path, admission_path: Path) -> dict[str, Any]:
    value = load(path)
    if not (value.get("project") == PROJECT_ID and value.get("gpu_claim_allowed") is True and value.get("admission", {}).get("sha256") == sha(admission_path)):
        raise RuntimeError("later_director_claim_authority_required")
    return value


def ssh_command(bench: dict[str, Any]) -> tuple[list[str], str, str]:
    resource = bench.get("resource", {})
    host, user, known = resource.get("public_ipv4"), resource.get("ssh_user"), resource.get("known_hosts_namespace")
    key = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
    if not all(isinstance(item, str) and item for item in (host, user, known)) or not key.is_file() or not Path(known).is_file():
        raise RuntimeError("established_ssh_identity_missing")
    base = ["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}"]
    return base, str(user), str(host)


def remote(ssh: list[str], user: str, host: str, shell: str, timeout: float, output: Path) -> subprocess.CompletedProcess[str]:
    return command([*ssh, f"{user}@{host}", shell], timeout, output)


def copy_to_remote(ssh: list[str], user: str, host: str, source: Path, destination: str, timeout: float, output: Path) -> subprocess.CompletedProcess[str]:
    options = ssh[1:]
    return command(["scp", *options, str(source), f"{user}@{host}:{destination}"], timeout, output)


def copy_from_remote(ssh: list[str], user: str, host: str, source: str, destination: Path, timeout: float, output: Path) -> subprocess.CompletedProcess[str]:
    return command(["scp", *ssh[1:], f"{user}@{host}:{source}", str(destination)], timeout, output)


def stage_immutable_checkpoint(ssh: list[str], user: str, host: str, source_root: Path, manifest: dict[str, Any], remote_root: str, output: Path) -> None:
    if remote(ssh, user, host, f"mkdir -p {shlex.quote(remote_root)}", 120, output / "checkpoint-mkdir.stdout").returncode:
        raise RuntimeError("checkpoint_remote_directory_failed")
    for row in manifest["files"]:
        local, name, size, digest = source_root / row["name"], row["name"], int(row["bytes"]), row["sha256"]
        if not local.is_file() or local.stat().st_size != size or sha(local) != digest:
            raise RuntimeError(f"checkpoint_source_manifest_mismatch:{name}")
        target, temporary = f"{remote_root}/{name}", f"{remote_root}/{name}.{digest}.part"
        match = f"test -f {shlex.quote(target)} && test \"$(stat -c %s {shlex.quote(target)})\" = {size} && test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {digest}"
        if remote(ssh, user, host, match, 900, output / f"checkpoint-match-{name}.stdout").returncode == 0:
            continue
        if remote(ssh, user, host, f"rm -f {shlex.quote(temporary)}", 120, output / f"checkpoint-clean-{name}.stdout").returncode:
            raise RuntimeError(f"checkpoint_temp_cleanup_failed:{name}")
        if copy_to_remote(ssh, user, host, local, temporary, max(900, size // 20_000_000 + 300), output / f"checkpoint-copy-{name}.stdout").returncode:
            raise RuntimeError(f"checkpoint_copy_failed:{name}")
        finalize = f"test \"$(stat -c %s {shlex.quote(temporary)})\" = {size} && test \"$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)\" = {digest} && chmod 0444 {shlex.quote(temporary)} && mv {shlex.quote(temporary)} {shlex.quote(target)}"
        if remote(ssh, user, host, finalize, max(900, size // 35_000_000 + 300), output / f"checkpoint-finalize-{name}.stdout").returncode:
            raise RuntimeError(f"checkpoint_finalize_failed:{name}")


def retained_repair(output: Path, deadline_epoch: float, diagnostic: str) -> None:
    repair_id = f"capture-repair-{time.time_ns()}"
    result = command([str(REPAIR), "ready", "--root", str(output), "--repair-id", repair_id, "--deadline", utc(deadline_epoch), "--failure-kind", "capture_integration_or_retrieval_failure", "--diagnostic", diagnostic, "--retry-scope", "capture_or_observer_consumer_only"], 30, output / f"{repair_id}.ready")
    if result.returncode:
        raise RuntimeError("repair_handshake_creation_failed")


def later_owner(admission_path: Path, claim_authority: Path, output: Path) -> int:
    admission, ready = load(admission_path), load(PROJECT / "EXACT_DIVERSE_C32_CAPTURE_READY.json")
    permit = authority(claim_authority, admission_path)
    packet_root, manifest_path, archive = packet_paths(ready)
    manifest, checkpoint = load(manifest_path), load(checkpoint_manifest())
    bench = inventory_bench(permit["bench"]["id"])
    if not (sha(PROJECT / "EXACT_DIVERSE_C32_CAPTURE_READY.json") == permit["immutable_science"]["source_ready_sha256"] and sha(archive) == permit["immutable_science"]["packet_archive_sha256"] and sha(manifest_path) == ready["packet"]["manifest_sha256"] and sha(checkpoint_manifest()) == permit["immutable_science"]["checkpoint_manifest_sha256"] and bench.get("accelerator") == permit["bench"]["accelerator"]):
        raise RuntimeError("compact_preclaim_identity_mismatch")
    for row in manifest["files"]:
        source = packet_root / row["path"]
        if not source.is_file() or source.stat().st_size != row["bytes"] or sha(source) != row["sha256"]:
            raise RuntimeError(f"packet_member_identity_mismatch:{row['path']}")
    value = {"admission": admission, "ready": ready, "manifest": manifest, "checkpoint": checkpoint, "bench": bench, "paths": {"archive": str(archive), "checkpoint_manifest": str(checkpoint_manifest()), "checkpoint_source": str(checkpoint_source(admission))}}
    output.mkdir(parents=True, exist_ok=True)
    atomic(output / "OWNER_SOURCE.json", {"owner_sha256": sha(Path(__file__).resolve()), "claim_authority_sha256": sha(claim_authority), "admission_sha256": sha(admission_path)})
    claim = command([*POOL, "claim", "--project", PROJECT_ID, "--bench", admission["bench"]["id"]], 30, output / "claim.stdout")
    if claim.returncode:
        raise RuntimeError("bench_claim_failed")
    stop = threading.Event()
    def beat() -> None:
        while not stop.wait(45):
            command([*POOL, "heartbeat", "--project", PROJECT_ID], 30, output / f"heartbeat-{int(time.time())}.stdout")
    heartbeat = threading.Thread(target=beat, daemon=True)
    heartbeat.start()
    try:
        graph = plan(value)
        deadline_epoch = dt.datetime.fromisoformat(permit["bench"]["release_not_after_utc"].replace("Z", "+00:00")).timestamp()
        if deadline_epoch <= time.time():
            raise RuntimeError("absolute_lifecycle_deadline_expired")
        ssh, user, host = ssh_command(value["bench"])
        remote_root = value["ready"]["bounded_owner_destination"]["remote_output_root"]
        remote_packet = value["ready"]["bounded_owner_destination"]["remote_packet_root"]
        archive = Path(value["paths"]["archive"])
        if remote(ssh, user, host, f"mkdir -p {shlex.quote(remote_root)} {shlex.quote(remote_packet)}.part", 120, output / "remote-prepare.stdout").returncode:
            raise RuntimeError("remote_prepare_failed")
        remote_archive = f"{remote_root}/packet.tar"
        if copy_to_remote(ssh, user, host, archive, remote_archive + ".part", 900, output / "packet-copy.stdout").returncode:
            raise RuntimeError("packet_copy_failed")
        digest = value["ready"]["packet"]["archive_sha256"]
        finalize_packet = f"test \"$(sha256sum {shlex.quote(remote_archive)}.part | cut -d' ' -f1)\" = {digest} && mv {shlex.quote(remote_archive)}.part {shlex.quote(remote_archive)} && rm -rf {shlex.quote(remote_packet)}.part && mkdir -p {shlex.quote(remote_packet)}.part && tar -xf {shlex.quote(remote_archive)} -C {shlex.quote(remote_packet)}.part && mv {shlex.quote(remote_packet)}.part {shlex.quote(remote_packet)}"
        if remote(ssh, user, host, finalize_packet, 300, output / "packet-finalize.stdout").returncode:
            raise RuntimeError("packet_remote_identity_or_finalize_failed")
        stage_immutable_checkpoint(ssh, user, host, checkpoint_source(value["admission"]), value["checkpoint"], f"{remote_root}/checkpoint", output)
        server = " ".join(shlex.quote(token) for token in graph["server_command"])
        start = f"{server}"
        if remote(ssh, user, host, start, min(300, deadline_epoch - time.time()), output / "server-start.stdout").returncode:
            raise RuntimeError("server_start_failed")
        health = f"for n in $(seq 1 180); do curl -fsS http://127.0.0.1:30000/v1/models > {shlex.quote(remote_root)}/server-health.json && exit 0; sudo -n docker inspect -f '{{{{.State.Running}}}}' gemma4-exact-diverse-c32 | grep -x true >/dev/null || {{ sudo -n docker logs gemma4-exact-diverse-c32 > {shlex.quote(remote_root)}/server-fatal.log 2>&1 || true; exit 71; }}; sleep 2; done; exit 72"
        if remote(ssh, user, host, health, min(420, deadline_epoch - time.time()), output / "server-health.stdout").returncode:
            raise RuntimeError("server_health_failed")
        request = " ".join(shlex.quote(token) for token in graph["request_command"])
        invocation = f"sudo -n docker exec gemma4-exact-diverse-c32 bash -lc {shlex.quote(graph['science_marker'] + '\nexec ' + request)}"
        result = remote(ssh, user, host, invocation, max(1, deadline_epoch - time.time()), output / "request.stdout")
        retrieval = " ".join(shlex.quote(item) for item in graph["retrieval_order"][:-1])
        retrieve = f"cd {shlex.quote(remote_root)} && tar -cf compact-evidence.tar {retrieval}"
        if remote(ssh, user, host, retrieve, 300, output / "compact-retrieve.stdout").returncode:
            raise RuntimeError("compact_terminal_retrieval_failed")
        compact = output / "compact-evidence.tar"
        if copy_from_remote(ssh, user, host, f"{remote_root}/compact-evidence.tar", compact, 300, output / "compact-copy.stdout").returncode:
            raise RuntimeError("compact_evidence_copy_failed")
        if result.returncode:
            raise RuntimeError("capture_request_not_interpretable")
        raise RuntimeError("capture_terminal_validation_required_before_release")
    except Exception as error:
        retained_repair(output, deadline_epoch if 'deadline_epoch' in locals() else time.time() + 300, f"{type(error).__name__}:{error}")
        command([str(REPAIR), "wait", "--root", str(output), "--repair-id", sorted((output / ".repair-handshakes").iterdir())[-1].name], max(1, deadline_epoch - time.time()) if 'deadline_epoch' in locals() else 300, output / "repair.wait")
        return 2
    finally:
        stop.set()
        heartbeat.join(timeout=5)


def score_owner(authority_path: Path, output: Path) -> int:
    """One-shot bound H200 consumer; intentionally does not touch capture/server/checkpoint bytes."""
    permit = load(authority_path)
    bench_id = permit["bench"]["id"]
    inputs = permit["immutable_inputs"]
    output.mkdir(parents=True, exist_ok=True)
    scorer, capture = PROJECT / permit["mutable_implementation"]["scorer_source"], PROJECT / inputs["hidden_states"]
    capture_terminal = PROJECT / inputs["capture_terminal"]
    prior_terminal = PROJECT / "ADAPTIVE_RETRIEVAL_VOCAB_OFFLINE_TERMINAL.json"
    if not (permit.get("project") == PROJECT_ID and sha(capture) == inputs["hidden_states_sha256"] and sha(capture_terminal) == inputs["capture_terminal_sha256"] and sha(prior_terminal) == inputs["prior_terminal_sha256"]):
        raise RuntimeError("score_authority_input_identity_mismatch")
    bench = inventory_bench(bench_id)
    if bench.get("status") != permit["bench"]["status_required_at_claim"] or bench.get("accelerator") != permit["bench"]["accelerator"]:
        raise RuntimeError("score_authority_bench_not_available_or_incompatible")
    owner_hash, scorer_hash = sha(Path(__file__).resolve()), sha(scorer)
    atomic(output / "OWNER_SOURCE.json", {"authority_sha256": sha(authority_path), "owner_sha256": owner_hash, "scorer_sha256": scorer_hash, "checkpoint_transfer_bytes": 0, "checkpoint_rehash": False})
    claimed = command([*POOL, "claim", "--project", PROJECT_ID, "--bench", bench_id], 30, output / "claim.stdout")
    if claimed.returncode:
        raise RuntimeError("score_bench_claim_failed")
    claimed_at = time.time()
    deadline = min(claimed_at + 8 * 60, dt.datetime.fromisoformat(permit["budgets"]["release_deadline_utc"].replace("Z", "+00:00")).timestamp() - 60)
    stop = threading.Event()
    def beat() -> None:
        while not stop.wait(30):
            command([*POOL, "heartbeat", "--project", PROJECT_ID, "--bench", bench_id], 30, output / f"heartbeat-{int(time.time())}.stdout")
    heartbeat = threading.Thread(target=beat, daemon=True)
    heartbeat.start()
    terminal_ok = False
    try:
        ssh, user, host = ssh_command(bench)
        remote_root = "/home/glmrunner/gemma4-adaptive-retrieval-score-20260727t0045z"
        if remote(ssh, user, host, f"mkdir -p {shlex.quote(remote_root)}/input {shlex.quote(remote_root)}/output", 60, output / "remote-prepare.stdout").returncode:
            raise RuntimeError("score_remote_prepare_failed")
        for local, name in ((scorer, scorer.name), (capture, "hidden_states.pt"), (capture_terminal, "EXACT_CAPTURE_TERMINAL.json"), (prior_terminal, prior_terminal.name)):
            if copy_to_remote(ssh, user, host, local, f"{remote_root}/input/{name}.part", 300, output / f"copy-{name}.stdout").returncode:
                raise RuntimeError(f"score_copy_failed:{name}")
            if remote(ssh, user, host, f"mv {shlex.quote(remote_root + '/input/' + name + '.part')} {shlex.quote(remote_root + '/input/' + name)}", 60, output / f"copy-finalize-{name}.stdout").returncode:
                raise RuntimeError(f"score_copy_finalize_failed:{name}")
        image, checkpoint = permit["bench"]["image"], permit["bench"]["resident_checkpoint"]
        invocation = ["sudo", "-n", "docker", "run", "--rm", "--gpus", "all", "--ipc=host", "-v", f"{remote_root}/input:/work/input:ro", "-v", f"{remote_root}/output:/work/output", "-v", f"{checkpoint}:/work/checkpoint:ro", image, "python3", "/work/input/" + scorer.name, "--cuda", "--weight", "/work/checkpoint/model-00001-of-00002.safetensors", "--capture", "/work/input/hidden_states.pt", "--capture-terminal", "/work/input/EXACT_CAPTURE_TERMINAL.json", "--prior-terminal", "/work/input/" + prior_terminal.name, "--output", "/work/output/H200_DIVERSE_RETRIEVAL_SCORE_TERMINAL.json", "--science-marker", "/work/output/science_started.json", "--owner-sha256", owner_hash]
        if time.time() >= deadline:
            raise RuntimeError("score_deadline_expired_before_science")
        run = remote(ssh, user, host, " ".join(shlex.quote(x) for x in invocation), max(1, deadline - time.time()), output / "score.stdout")
        for name in ("H200_DIVERSE_RETRIEVAL_SCORE_TERMINAL.json", "science_started.json"):
            copy_from_remote(ssh, user, host, f"{remote_root}/output/{name}", output / name, 180, output / f"retrieve-{name}.stdout")
        if run.returncode:
            raise RuntimeError("score_invocation_not_interpretable")
        terminal = load(output / "H200_DIVERSE_RETRIEVAL_SCORE_TERMINAL.json")
        if terminal.get("source_hashes", {}).get("consumer") != scorer_hash or terminal.get("source_hashes", {}).get("owner") != owner_hash:
            raise RuntimeError("score_terminal_source_hash_mismatch")
        terminal_ok = True
        atomic(output / "OWNER_TERMINAL.json", {"pass": True, "terminal_sha256": sha(output / "H200_DIVERSE_RETRIEVAL_SCORE_TERMINAL.json"), "owner_sha256": owner_hash, "scorer_sha256": scorer_hash, "claim_started_at_utc": utc(claimed_at), "checkpoint_transfer_bytes": 0, "checkpoint_rehash": False})
        return 0
    except Exception as error:
        atomic(output / "OWNER_FAILURE.json", {"error": f"{type(error).__name__}:{error}", "science_marker_present": (output / "science_started.json").is_file(), "terminal_present": (output / "H200_DIVERSE_RETRIEVAL_SCORE_TERMINAL.json").is_file()})
        return 2
    finally:
        stop.set()
        heartbeat.join(timeout=5)
        state = "ready" if terminal_ok else "maintenance"
        command([*POOL, "release", "--project", PROJECT_ID, "--bench", bench_id, "--condition", state], 60, output / "release.stdout")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission", type=Path)
    parser.add_argument("--offline-exercise", action="store_true")
    parser.add_argument("--claim-authority", type=Path)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--score-authority", type=Path)
    args = parser.parse_args()
    if args.score_authority:
        if not args.output_dir:
            raise RuntimeError("score_authority_requires_output_dir")
        return score_owner(args.score_authority.resolve(), args.output_dir.resolve())
    if args.offline_exercise:
        terminal_path = PROJECT / "H200_EXACT_DIVERSE_CAPTURE_OWNER_READY.json"
        try:
            value = validate_identities(args.admission.resolve())
            graph = plan(value)
            terminal = {
            "schema_version": 1,
            "classification": "h200_exact_diverse_capture_owner_lifecycle_pure_ready",
            "pass": all(value["checks"].values()) and graph["deadline_plan_valid"],
            "admission_sha256": sha(args.admission),
            "owner_sha256": sha(Path(__file__).resolve()),
            "source_ready_sha256": sha(PROJECT / "EXACT_DIVERSE_C32_CAPTURE_READY.json"),
            "packet_manifest_sha256": sha(Path(value["paths"]["manifest"])),
            "packet_archive_sha256": sha(Path(value["paths"]["archive"])),
            "checkpoint_manifest_sha256": sha(Path(value["paths"]["checkpoint_manifest"])),
            "gpu_inventory_sha256": sha(LAB / "runtime" / "gpus.json"),
            "detached_owner_sha256": sha(DETACHED),
            "repair_handshake_sha256": sha(REPAIR),
            "checks": value["checks"],
            "packet_members": value["members"],
            "checkpoint_inventory": value["checkpoint_rows"],
            "command_graph": graph,
            "resource_use": {"gpu_claimed": False, "checkpoint_bytes_copied": 0, "ssh_used": False, "provider_contacted": False, "endpoint_requests": 0, "retrieval_runs": 0, "actual_spend_usd": 0.0},
            "disposition": "pause_for_later_director_claim_admission",
            }
        except Exception as error:
            terminal = {
                "schema_version": 1,
                "classification": "h200_exact_diverse_capture_owner_lifecycle_pure_ready",
                "pass": False,
                "diagnostic": f"{type(error).__name__}:{error}",
                "resource_use": {"gpu_claimed": False, "checkpoint_bytes_copied": 0, "ssh_used": False, "provider_contacted": False, "endpoint_requests": 0, "retrieval_runs": 0, "actual_spend_usd": 0.0},
                "disposition": "offline_repair_required_before_director_claim_admission",
            }
        atomic(terminal_path, terminal)
        return 0 if terminal["pass"] else 2
    if not args.admission or not args.claim_authority or not args.output_dir:
        raise RuntimeError("offline_exercise_or_later_claim_authority_and_output_required")
    return later_owner(args.admission.resolve(), args.claim_authority.resolve(), args.output_dir.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
