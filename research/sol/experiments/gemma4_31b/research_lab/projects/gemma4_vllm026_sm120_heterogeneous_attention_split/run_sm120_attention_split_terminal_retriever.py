#!/usr/bin/env python3
"""Retrieve and adopt the one bound, already-complete SM120 oracle terminal."""
from __future__ import annotations

import argparse, datetime as dt, hashlib, json, os, shlex, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
LAB = HERE.parents[1]
REPO = HERE.parents[6]
sys.path.insert(0, str(REPO / "research/factory/src"))
from grad_research.gpu_claim_session import GpuClaimSession
from grad_research.gpu_pool import GpuPool

PROJECT = "gemma4_vllm026_sm120_heterogeneous_attention_split"

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def atom(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as f:
        json.dump(value, f, indent=2, sort_keys=True); f.write("\n"); tmp = Path(f.name)
    json.loads(tmp.read_text()); os.replace(tmp, path)

def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

def ssh_argv(bench: dict) -> list[str]:
    r = bench["resource"]
    for k in ("ssh_identity_path", "known_hosts_namespace", "public_ipv4", "ssh_port", "ssh_user"):
        if not r.get(k): raise RuntimeError(f"claimed bench missing {k}")
    return ["ssh", "-i", r["ssh_identity_path"], "-o", "IdentitiesOnly=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={r['known_hosts_namespace']}", "-o", "ConnectTimeout=15", "-p", str(r["ssh_port"]), f"{r['ssh_user']}@{r['public_ipv4']}"]

def remote(argv: list[str], command: str, timeout: int = 90) -> bytes:
    p = subprocess.run([*argv, command], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if p.returncode: raise RuntimeError(f"remote exit={p.returncode}: {p.stderr.decode(errors='replace')[-1500:]}")
    return p.stdout

def main() -> int:
    ap = argparse.ArgumentParser(); ap.add_argument("--binding", type=Path, required=True); ap.add_argument("--artifact-root", type=Path, required=True); a = ap.parse_args()
    b = json.loads(a.binding.read_text())
    if b.get("classification") != "director_corrected_sm120_terminal_retrieval_binding" or b.get("project") != PROJECT: raise RuntimeError("wrong retrieval binding")
    expected = b["observed_terminal"]
    if dt.datetime.fromisoformat(b["bench"]["absolute_release_deadline_utc"].replace("Z", "+00:00")) <= dt.datetime.now(dt.timezone.utc): raise RuntimeError("retrieval release fence passed")
    root = a.artifact_root.resolve(); root.mkdir(parents=True, exist_ok=True)
    pool = GpuPool(LAB)
    with GpuClaimSession(pool, PROJECT, b["bench"]["id"], lease_seconds=300, heartbeat_seconds=20) as claim:
        bench = pool.show(b["bench"]["id"])
        if bench.get("claim", {}).get("claimed_at") != claim.claimed_at: raise RuntimeError("claim generation mismatch")
        argv = ssh_argv(bench); rroot = expected["root"]
        census = remote(argv, "set -eu; test ! -e /proc/%d; test -z \"$(nvidia-smi --query-compute-apps=pid --format=csv,noheader 2>/dev/null || true)\"; ps -eo pid=,args= | grep -E '[f]uture_sm120_oracle|[a]ttention-oracle|[n]orm-fp8' || true" % expected["remote_parent_pid"])
        if census.strip(): raise RuntimeError("remote executor census not quiescent: " + census.decode(errors="replace")[-800:])
        atom(root / "PROGRESS.json", {"phase":"claimed_quiescent_retrieval", "claimed_at":claim.claimed_at, "census":census.decode(errors="replace"), "updated_at_utc":now()})
        names = {"SM120_ATTENTION_SPLIT_ORACLE.json": expected["terminal"], "control.json": expected["control"], "candidate.json": expected["candidate"]}
        # Existing captures are preserved alongside the three bound decision files.
        captures = ["control.stdout", "control.stderr", "candidate.stdout", "candidate.stderr", "oracle_parent_r2.stdout", "oracle_parent_r2.stderr"]
        for name, spec in names.items():
            data = remote(argv, "cat " + shlex.quote(rroot + "/" + name), 180)
            p = root / name; p.write_bytes(data)
            if len(data) != spec["bytes"] or digest(p) != spec["sha256"]: raise RuntimeError(f"bound digest mismatch: {name}")
        retrieved = list(names)
        for name in captures:
            probe = subprocess.run([*argv, "test -f " + shlex.quote(rroot + "/" + name)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if probe.returncode == 0:
                p = root / name; p.write_bytes(remote(argv, "cat " + shlex.quote(rroot + "/" + name), 180)); retrieved.append(name)
        terminal = json.loads((root / "SM120_ATTENTION_SPLIT_ORACLE.json").read_text())
        proof = terminal.get("path_proof", {})
        rows_complete = (terminal.get("classification") in {"oracle_pass", "oracle_failed"} and isinstance(terminal.get("control"), dict) and isinstance(terminal.get("candidate"), dict) and bool(terminal["control"].get("output", {}).get("rows")) and bool(terminal["candidate"].get("output", {}).get("rows")))
        if not rows_complete: raise RuntimeError("retrieved terminal lacks either bound arm row ledger")
        proof_complete = all(proof.get(k) is True for k in ("control_triton", "candidate_triton", "candidate_flex"))
        final = {"schema_version":1, "classification":terminal["classification"], "claimed_at":claim.claimed_at, "binding_sha256":digest(a.binding), "remote_root":rroot, "remote_terminal_sha256":digest(root / "SM120_ATTENTION_SPLIT_ORACLE.json"), "control_sha256":digest(root / "control.json"), "candidate_sha256":digest(root / "candidate.json"), "captures":{n:digest(root / n) for n in retrieved if n not in names}, "oracle_terminal":terminal, "retrieved":retrieved, "rows_complete":True, "path_proof_complete":proof_complete, "adoption_disposition":"component_negative" if proof_complete else "incomplete_path_proof", "completed_at_utc":now(), "scientific_replay":False}
        atom(root / "TERMINAL.json", final)
        claim.release(condition="maintenance", contents={"project":PROJECT, "attention_split_terminal":terminal["classification"], "artifacts":str(root), "server_state":"Corrected terminal retrieved; quiescent RTX runtime/checkpoint/caches retained for director disposition."})
        return 0

if __name__ == "__main__": raise SystemExit(main())
