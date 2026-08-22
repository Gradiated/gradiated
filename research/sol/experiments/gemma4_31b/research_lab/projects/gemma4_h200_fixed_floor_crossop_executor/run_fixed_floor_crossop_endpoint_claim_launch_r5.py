#!/usr/bin/env python3
"""The sole future R5 claim, derive, and durable-owner launch seam."""
import argparse, datetime as dt, json, pathlib, subprocess, sys

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
DETACHED = "/root/workspace/research/factory/tools/detached-owner"

def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)

def run(command, timeout=60):
    result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr[-600:] or result.stdout[-600:])
    return result.stdout

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-spec", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    parser.add_argument("--pool-command", nargs="+", default=POOL)
    parser.add_argument("--detached-owner", default=DETACHED)
    args = parser.parse_args()
    spec = json.loads(args.execution_spec.read_text())
    if not spec.get("claim_allowed"):
        raise RuntimeError("fresh_director_execution_binding_required")
    bench = spec["bench_id"]
    pool = args.pool_command
    run([*pool, "claim", "--project", spec["project"], "--bench", bench])
    current = json.loads(run([*pool, "show", "--bench", bench]))
    claim = current.get("claim") or {}
    resource, lifecycle = current["resource"], current["lifecycle"]
    if claim.get("claimed_at") is None:
        raise RuntimeError("claim_not_observed")
    binding = {**spec, "claimed_at": claim["claimed_at"], "gpu_uuid": resource["gpu_uuid"], "ssh_fingerprint": resource["ssh_ed25519_fingerprint"], "watchdog_main_pid": lifecycle["watchdog"]["main_pid"], "ssh_identity_path": resource["ssh_identity_path"], "known_hosts": resource["known_hosts_namespace"], "ssh_host": resource["ssh_user"] + "@" + resource["public_ipv4"]}
    root = args.artifact_root.resolve()
    derived, ready, state, log = root / "ENDPOINT_R5_EXECUTION_BINDING.json", root / "OWNER_READY.json", root / "OWNER_STATE.json", root / "OWNER.log"
    put(derived, binding)
    launched = json.loads(run([args.detached_owner, "start", "--unit-manager", "pid", "--state", str(state), "--log", str(log), "--cwd", str(PROJECT), "--ready-file", str(ready), "--stabilize-seconds", "30", "--", sys.executable, str(PROJECT / "run_fixed_floor_crossop_endpoint_owner_r5.py"), "--binding", str(derived), "--artifact-root", str(root), "--ready-file", str(ready)], 45))
    if not launched.get("live") or not launched.get("ready"):
        raise RuntimeError("owner_not_ready")
    status = PROJECT / "STATUS.json"
    record = json.loads(status.read_text())
    record["active_session"] = {"artifact_root": str(root), "deadline_utc": binding["absolute_release_deadline_utc"], "expected_terminal": "PAIR_TERMINAL.json", "forward_progress": "R5 owner crossed claim/binding validation into staged candidate-only dispatch.", "pid": launched["pid"], "start_ticks": launched["start_ticks"], "unit": str(state), "unit_manager": "pid"}
    put(status, record)
    print(json.dumps({"binding": str(derived), "owner_state": str(state), "pid": launched["pid"], "start_ticks": launched["start_ticks"]}, sort_keys=True))

if __name__ == "__main__": main()
