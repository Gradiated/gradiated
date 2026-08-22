#!/usr/bin/env python3
"""Durable future owner for the one-shot Gemma 4 sm_120 attention oracle.

This file is deliberately inert without a later director execution binding.
That binding names one available bench, the exact resident endpoint generation,
an SSH argv prefix, and an absolute release deadline.  It is the only authority
for the paid path; this preparation binding is *not* one.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
sys.path.insert(0, str(REPO / "research/factory/src"))

from grad_research.gpu_claim_session import GpuClaimSession  # noqa: E402
from grad_research.gpu_pool import GpuPool  # noqa: E402

PROJECT = "gemma4_vllm026_sm120_heterogeneous_attention_split"
WHEEL_SHA256 = "6ce4ca30616f0a35810391015622b197a7b8b267ed27f8716f0789db79ff578b"
ORACLE_SHA256 = "adb4f590988387fd32518b8955bef0c495fa6321235d13299f58dc230ad9e46b"
PREPARATION_BINDING = (
    HERE / "DIRECTOR_VLLM026_SM120_ATTENTION_SPLIT_COMPONENT_OWNER_PREPARATION_20260729T0740Z.json"
)
HANDSHAKE = REPO / "research/factory/tools/repair-handshake"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deadline_epoch(value: str) -> float:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("deadline must be timezone-aware")
    return parsed.timestamp()


def require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"future execution binding missing {name}")
    return value


def load_execution_binding(path: Path) -> dict[str, Any]:
    """Fail closed unless this is a later, explicit paid-execution binding."""
    binding = json.loads(path.read_text())
    if binding.get("classification") != "director_sm120_attention_split_execution_binding":
        raise ValueError("binding is not a later attention-split execution binding")
    if binding.get("project") != PROJECT or binding.get("preparation_binding_sha256") != sha256(PREPARATION_BINDING):
        raise ValueError("binding is not chained to this exact preparation binding")
    required = ("bench_id", "absolute_release_deadline_utc", "remote_root")
    for field in required:
        require_text(binding.get(field), field)
    ssh_argv = binding.get("ssh_argv")
    if not isinstance(ssh_argv, list) or not ssh_argv or not all(isinstance(x, str) and x for x in ssh_argv):
        raise ValueError("binding must supply a nonempty exact ssh_argv list")
    predecessor = binding.get("predecessor")
    if not isinstance(predecessor, dict):
        raise ValueError("binding must name a future resident predecessor")
    if not isinstance(predecessor.get("server_pid"), int) or not isinstance(predecessor.get("start_ticks"), int):
        raise ValueError("binding predecessor must bind server_pid and start_ticks")
    validate_predecessor_state(predecessor)
    if binding.get("oracle_sha256") != ORACLE_SHA256 or binding.get("wheel_sha256") != WHEEL_SHA256:
        raise ValueError("binding does not preserve oracle or wheel identity")
    if deadline_epoch(binding["absolute_release_deadline_utc"]) <= time.time():
        raise ValueError("execution binding release deadline has passed")
    return binding


def validate_predecessor_state(predecessor: dict[str, Any]) -> str:
    state = predecessor.get("state")
    if state == "live_exact":
        return state
    if state != "already_stopped":
        raise ValueError("binding predecessor state must be live_exact or already_stopped")
    required_text = ("stopped_by_claim_generation", "invalid_attempt_terminal_sha256")
    for field in required_text:
        require_text(predecessor.get(field), f"predecessor.{field}")
    if len(predecessor["invalid_attempt_terminal_sha256"]) != 64:
        raise ValueError("binding predecessor invalid-attempt terminal digest must be SHA-256")
    census = predecessor.get("post_claim_quiescent_census")
    if not isinstance(census, dict) or census.get("zero_accelerator_allocations") is not True:
        raise ValueError("already-stopped predecessor requires zero-allocation post-claim census")
    forbidden = census.get("forbidden_processes")
    if not isinstance(forbidden, list) or sorted(forbidden) != ["attention-oracle", "norm-fp8", "vllm"]:
        raise ValueError("already-stopped predecessor requires the exact process census")
    return state


def remote(binding: dict[str, Any], command: str, *, timeout: int, input_bytes: bytes | None = None) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        [*binding["ssh_argv"], command], input=input_bytes, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, timeout=timeout, check=False,
    )


def remote_checked(binding: dict[str, Any], command: str, *, timeout: int, input_bytes: bytes | None = None) -> bytes:
    result = remote(binding, command, timeout=timeout, input_bytes=input_bytes)
    if result.returncode:
        raise RuntimeError(f"remote command failed ({result.returncode}): {result.stderr.decode(errors='replace')[-2000:]}")
    return result.stdout


def stage_oracle_after_claim(binding: dict[str, Any], generation_root: str) -> str:
    """Reconcile one small immutable program; checkpoint bytes are never touched."""
    source = HERE / "future_sm120_oracle.py"
    if sha256(source) != ORACLE_SHA256:
        raise RuntimeError("local oracle hash no longer matches the director binding")
    remote_path = f"{generation_root}/future_sm120_oracle.py"
    part = f"{remote_path}.part.{os.getpid()}"
    quoted_root, quoted_target, quoted_part = map(shlex.quote, (generation_root, remote_path, part))
    check = f"mkdir -p {quoted_root}; if test -f {quoted_target} && test $(sha256sum {quoted_target} | awk '{{print $1}}') = {ORACLE_SHA256}; then exit 0; fi; rm -f {quoted_part}; cat > {quoted_part}; test $(sha256sum {quoted_part} | awk '{{print $1}}') = {ORACLE_SHA256}; chmod 0444 {quoted_part}; mv -f {quoted_part} {quoted_target}"
    remote_checked(binding, check, timeout=300, input_bytes=source.read_bytes())
    return remote_path


def stop_exact_predecessor_and_fence(binding: dict[str, Any], artifact_root: Path) -> None:
    """Fence the bound predecessor, including a hash-bound stopped generation."""
    predecessor = binding["predecessor"]
    pid, ticks = predecessor["server_pid"], predecessor["start_ticks"]
    state = validate_predecessor_state(predecessor)
    artifact_root.mkdir(parents=True, exist_ok=True)
    if state == "already_stopped":
        script = f'''set -eu
pid={pid}; expected={ticks}
test ! -e /proc/$pid
allocations="$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null || true)"
test -z "$allocations"
for proc in /proc/[0-9]*; do
  candidate="${{proc#/proc/}}"
  test "$candidate" = "$$" && continue
  args="$(tr '\\0' ' ' < "$proc/cmdline" 2>/dev/null || true)"
  case "$args" in
    *vllm*|*attention-oracle*|*norm-fp8*) echo "forbidden_process=$candidate:$args" >&2; exit 1 ;;
  esac
done
printf 'predecessor_state=already_stopped\\nprior_claim_generation=%s\\ninvalid_attempt_terminal_sha256=%s\\naccelerator_allocations=0\\nforbidden_processes=0\\n' {shlex.quote(predecessor["stopped_by_claim_generation"])} {shlex.quote(predecessor["invalid_attempt_terminal_sha256"])}
'''
        result = remote(binding, script, timeout=90)
        (artifact_root / "predecessor_already_stopped_census.stdout").write_bytes(result.stdout)
        (artifact_root / "predecessor_already_stopped_census.stderr").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("future-bound already-stopped predecessor census failed")
        return
    # The PID check happens before every signal. Descendants are stopped only
    # after that check, preventing a reused PID from becoming a broad stop.
    script = f'''set -eu
pid={pid}; expected={ticks}
ticks() {{ awk '{{print $22}}' /proc/$1/stat 2>/dev/null || true; }}
test "$(ticks "$pid")" = "$expected"
desc() {{ for c in $(pgrep -P "$1" 2>/dev/null || true); do desc "$c"; echo "$c"; done; }}
targets="$(desc "$pid") $pid"
kill -TERM $targets 2>/dev/null || true
for n in $(seq 1 30); do test -e /proc/$pid || break; sleep 1; done
test ! -e /proc/$pid
sleep 2
nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader || true
'''
    result = remote(binding, script, timeout=90)
    (artifact_root / "predecessor_stop.stdout").write_bytes(result.stdout)
    (artifact_root / "predecessor_stop.stderr").write_bytes(result.stderr)
    if result.returncode:
        raise RuntimeError("future-bound predecessor PID/start-tick fence failed")
    allocations = result.stdout.decode(errors="replace").strip()
    allowed = binding.get("allowed_gpu_processes_after_fence", [])
    if allocations and allocations not in allowed:
        raise RuntimeError(f"accelerator fence is not quiescent: {allocations[-1000:]}")


def retrieve_generation(binding: dict[str, Any], remote_root: str, local_root: Path) -> list[str]:
    local_root.mkdir(parents=True, exist_ok=True)
    listing = remote_checked(binding, f"find {shlex.quote(remote_root)} -maxdepth 1 -type f -printf '%f\\n' | sort", timeout=90).decode().splitlines()
    kept: list[str] = []
    for name in listing:
        if not name or "/" in name or name.startswith("."):
            continue
        data = remote_checked(binding, f"cat {shlex.quote(remote_root + '/' + name)}", timeout=300)
        (local_root / name).write_bytes(data)
        kept.append(name)
    return kept


def oracle_terminal(local_root: Path) -> dict[str, Any] | None:
    path = local_root / "SM120_ATTENTION_SPLIT_ORACLE.json"
    if not path.is_file():
        return None
    value = json.loads(path.read_text())
    if not isinstance(value, dict) or value.get("classification") not in {"oracle_pass", "oracle_failed"}:
        return None
    # A terminal is only complete if both arm records and the exact path proof exist.
    control, candidate, proof = value.get("control"), value.get("candidate"), value.get("path_proof")
    if not isinstance(control, dict) or not isinstance(candidate, dict) or not isinstance(proof, dict):
        return None
    if control.get("exit_code") != 0 or candidate.get("exit_code") != 0:
        return None
    if not isinstance(control.get("output"), dict) or not isinstance(candidate.get("output"), dict):
        return None
    if not control["output"].get("rows") or not candidate["output"].get("rows"):
        return None
    if not all(proof.get(key) is True for key in ("control_triton", "candidate_triton", "candidate_flex")):
        return None
    return value


def repair_wait(artifact_root: Path, repair_id: str, deadline: str, diagnostic: Path) -> dict[str, Any]:
    ready = subprocess.run([str(HANDSHAKE), "ready", "--root", str(artifact_root), "--repair-id", repair_id,
                            "--deadline", deadline, "--failure-kind", "integration", "--diagnostic", str(diagnostic),
                            "--retry-scope", "retrieve_or_adopt_existing_attention_oracle_terminal"], capture_output=True, text=True, check=False)
    if ready.returncode:
        raise RuntimeError(f"cannot publish retained repair: {ready.stderr[-1000:]}")
    waited = subprocess.run([str(HANDSHAKE), "wait", "--root", str(artifact_root), "--repair-id", repair_id,
                              "--deadline", deadline, "--poll-seconds", "15"], capture_output=True, text=True, check=False)
    if not waited.stdout:
        raise RuntimeError("repair handshake produced no state")
    return json.loads(waited.stdout.splitlines()[-1])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=Path, required=True,
                        help="later director binding; the preparation binding is rejected")
    parser.add_argument("--artifact-root", type=Path, required=True)
    args = parser.parse_args()
    binding = load_execution_binding(args.execution_binding.resolve())
    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    pool = GpuPool(LAB)
    terminal_path = artifact_root / "TERMINAL.json"
    with GpuClaimSession(pool, PROJECT, binding["bench_id"], lease_seconds=900, heartbeat_seconds=45) as claim:
        generation = claim.claimed_at.replace(":", "").replace("+", "_")
        generation_root = f"{binding['remote_root'].rstrip('/')}/generations/{generation}"
        local_generation = artifact_root / "generations" / generation
        atomic_json(artifact_root / "OWNER_STATE.json", {"phase": "claimed", "claimed_at": claim.claimed_at,
                    "bench_id": binding["bench_id"], "generation_root": generation_root, "updated_at_utc": now()})
        try:
            # The predecessor fence is the first remote mutation after claim.
            # A stopped predecessor must prove its new quiescent generation
            # before the immutable oracle is staged or a request can be sent.
            stop_exact_predecessor_and_fence(binding, local_generation)
            staged_oracle = stage_oracle_after_claim(binding, generation_root)
            command = f"mkdir -p {shlex.quote(generation_root + '/run')}; {shlex.quote(binding['runtime_python'])} {shlex.quote(staged_oracle)} --wheel {shlex.quote(binding['runtime_wheel'])} --model {shlex.quote(binding['checkpoint_path'])} --output {shlex.quote(generation_root + '/run')}"
            atomic_json(local_generation / "SUBMISSION.json", {"submission_definition": "one parent all-TRITON then layer-aware oracle", "submitted_at_utc": now(), "command": command})
            result = remote(binding, command, timeout=max(60, int(deadline_epoch(binding["absolute_release_deadline_utc"]) - time.time() - 180)))
            (local_generation / "oracle_parent.stdout").write_bytes(result.stdout)
            (local_generation / "oracle_parent.stderr").write_bytes(result.stderr)
            retrieved = retrieve_generation(binding, generation_root + "/run", local_generation)
            terminal = oracle_terminal(local_generation)
            if terminal is None:
                # Do not replay a partially evidenced control/candidate arm. The
                # only supported repair scope is retrieval/adoption of its bytes.
                diagnostic = local_generation / "REPAIR_DIAGNOSTIC.txt"
                diagnostic.write_text(f"parent_exit={result.returncode}; retrieved={retrieved}; no complete oracle terminal\n")
                repair_id = f"attention-oracle-{generation}-r1"
                state = repair_wait(artifact_root, repair_id, binding["absolute_release_deadline_utc"], diagnostic)
                if state.get("state") != "requested":
                    raise RuntimeError(f"repair deadline/state prevents terminal adoption: {state}")
                retrieved = retrieve_generation(binding, generation_root + "/run", local_generation)
                terminal = oracle_terminal(local_generation)
                if terminal is None:
                    raise RuntimeError("unretrieved or incomplete oracle remains unknown after retrieval repair")
            final = {"schema_version": 1, "classification": terminal["classification"], "claimed_at": claim.claimed_at,
                     "oracle_returncode": result.returncode, "oracle_terminal": terminal,
                     "per_arm_evidence": {"control": "control.json", "candidate": "candidate.json", "retrieved": retrieved},
                     "component_only": True, "endpoint_c32_executed": False, "completed_at_utc": now()}
            atomic_json(terminal_path, final)
            claim.release(condition="maintenance", contents={"project": PROJECT, "attention_split_terminal": final["classification"],
                          "artifacts": str(artifact_root), "server_state": "Future bound predecessor stopped and GPU fence recorded; runtime/checkpoint remain resident."})
            return 0 if final["classification"] == "oracle_pass" else 3
        except Exception as error:
            # Keep the heartbeat owner alive through an explicit repair handshake;
            # context exit is the deadline/unsafe maintenance fallback only.
            diagnostic = artifact_root / "OWNER_EXCEPTION.txt"
            diagnostic.write_text(repr(error) + "\n")
            atomic_json(artifact_root / "OWNER_STATE.json", {"phase": "retained_repair", "claimed_at": claim.claimed_at,
                        "error": repr(error), "updated_at_utc": now()})
            repair_id = f"attention-owner-{generation}-r2"
            try:
                repair_wait(artifact_root, repair_id, binding["absolute_release_deadline_utc"], diagnostic)
            finally:
                atomic_json(terminal_path, {"schema_version": 1, "classification": "typed_owner_deadline_or_unrepaired_boundary",
                                             "claimed_at": claim.claimed_at, "diagnostic": str(diagnostic), "completed_at_utc": now()})
            raise


if __name__ == "__main__":
    raise SystemExit(main())
