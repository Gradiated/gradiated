#!/usr/bin/env python3
"""R5 retained-claim candidate dispatcher with explicit repair and release paths."""
import argparse, datetime as dt, hashlib, json, os, pathlib, subprocess, threading, time

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
REPAIR = "/root/workspace/research/factory/tools/repair-handshake"
ENV = {**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"}


def now(): return dt.datetime.now(dt.UTC)
def sha(path): return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)
def call(command, timeout): return subprocess.run(command, text=True, capture_output=True, check=False, timeout=timeout, env=ENV)
def left(deadline, reserve=0): return max(1, int((deadline - now()).total_seconds()) - reserve)
def release(binding, condition):
    return call(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), "release", "--project", binding["project"], "--bench", binding["bench_id"], "--expected-claimed-at", binding["claimed_at"], "--condition", condition], 60)


def valid_pair(pair):
    rows = pair.get("candidate", {}).get("rows", [])
    return pair.get("candidate", {}).get("complete_requests") == 32 and len(rows) == 32 and all({"chunks", "finish_reason", "usage", "sse_events", "exact_emitted_chunk_match"} <= set(row) for row in rows)


def wait_repair(root, deadline, generation, diagnostic):
    repair_id = f"endpoint-r5-{generation}-{int(time.time())}"
    while now() < deadline:
        try:
            ready = call([REPAIR, "ready", "--root", str(root), "--repair-id", repair_id, "--deadline", deadline.isoformat(), "--failure-kind", "candidate_only_recoverable", "--diagnostic", sha(diagnostic), "--retry-scope", "candidate_only"], 30)
            if ready.returncode:
                raise RuntimeError("repair_ready_failed:" + ready.stderr[-300:])
            put(root / "PROGRESS.json", {"phase": "repair_wait", "repair_id": repair_id, "at_utc": now().isoformat()})
            waited = call([REPAIR, "wait", "--root", str(root), "--repair-id", repair_id, "--deadline", deadline.isoformat()], left(deadline))
            state = json.loads(waited.stdout).get("state") if waited.returncode == 0 else "expired"
            if state != "requested": return False
            request = root / ".repair-handshakes" / repair_id / "REPAIR_REQUEST.json"
            request.replace(request.with_name("REPAIR_REQUEST." + sha(request) + ".consumed.json"))
            return True
        except Exception as error:
            put(root / f"REPAIR_SETUP_DIAGNOSTIC-g{generation}.json", {"classification": "recoverable_repair_setup_failure", "error": repr(error), "repair_id": repair_id, "at_utc": now().isoformat()})
            time.sleep(min(1, max(0, (deadline - now()).total_seconds())))
    return False


def prepare(binding, root, deadline):
    packet = json.loads((PROJECT / "ENDPOINT_INTEGRATION_PACKET_R5.json").read_text())
    if sha(PROJECT / "ENDPOINT_INTEGRATION_PACKET_R5.json") != binding["packet_sha256"]: raise RuntimeError("packet_hash")
    for name, digest in packet["files"].items():
        if sha(PROJECT / name) != digest: raise RuntimeError("packet_member_hash:" + name)
    inventory = json.loads(call(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), "show", "--bench", binding["bench_id"]], 30).stdout)
    resource = inventory["resource"]
    if inventory.get("claim", {}).get("claimed_at") != binding["claimed_at"] or resource["gpu_uuid"] != binding["gpu_uuid"] or resource["ssh_ed25519_fingerprint"] != binding["ssh_fingerprint"] or inventory["lifecycle"]["watchdog"]["main_pid"] != binding["watchdog_main_pid"]: raise RuntimeError("claim_identity_mismatch")
    remote, key, known = binding["remote_project_root"], resource["ssh_identity_path"], resource["known_hosts_namespace"]
    host = resource["ssh_user"] + "@" + resource["public_ipv4"]
    ssh = ["ssh", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + known, host]
    archive = root / "packet.tar"
    subprocess.run(["tar", "-cf", str(archive), "-C", str(PROJECT), *packet["files"]], check=True, timeout=120)
    for command in ([*ssh, f"mkdir -p {remote}/project {remote}/artifacts"], ["scp", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + known, str(archive), host + ":" + remote + "/packet.tar.part"], [*ssh, f"tar -xf {remote}/packet.tar.part -C {remote}/project && mv {remote}/packet.tar.part {remote}/packet.tar"]):
        result = call(command, left(deadline, 240))
        if result.returncode: raise RuntimeError("stage_failed:" + result.stderr[-300:])
    oracle = root / "CONTROL_EMITTED_CHUNK_ORACLE.json"
    subprocess.run(["python3", str(PROJECT / "fixed_floor_crossop_control_chunk_oracle.py"), "--control-root", binding["control_root"], "--terminal-sha256", binding["control_terminal_sha256"], "--output", str(oracle)], check=True, timeout=90)
    copied = call(["scp", "-i", key, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + known, str(oracle), host + ":" + remote + "/CONTROL_EMITTED_CHUNK_ORACLE.json"], left(deadline, 180))
    if copied.returncode: raise RuntimeError("oracle_stage_failed:" + copied.stderr[-300:])
    return remote, ssh


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--binding", type=pathlib.Path, required=True); parser.add_argument("--artifact-root", type=pathlib.Path, required=True); parser.add_argument("--ready-file", type=pathlib.Path, required=True); args = parser.parse_args()
    binding, root = json.loads(args.binding.read_text()), args.artifact_root
    if not binding.get("claim_allowed"): raise RuntimeError("r5_execution_binding_not_authorized")
    root.mkdir(parents=True, exist_ok=True)
    deadline = dt.datetime.fromisoformat(binding["absolute_release_deadline_utc"].replace("Z", "+00:00"))
    stop = threading.Event()
    def heartbeat():
        while not stop.wait(35):
            result = call(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), "heartbeat", "--project", binding["project"]], 30)
            put(root / "HEARTBEAT.json", {"at_utc": now().isoformat(), "rc": result.returncode, "stderr": result.stderr[-400:]})
    threading.Thread(target=heartbeat, daemon=True).start()
    generation, prepared, terminal = 0, None, None
    try:
        while now() < deadline:
            try:
                if prepared is None:
                    prepared = prepare(binding, root, deadline)
                    put(args.ready_file, {"phase": "staged", "at_utc": now().isoformat(), "claimed_at": binding["claimed_at"]})
                remote, ssh = prepared
                output = f"{remote}/artifacts/candidate-r5-g{generation}"
                put(root / "PROGRESS.json", {"phase": "candidate_only", "generation": generation, "output": output, "at_utc": now().isoformat()})
                worker = call([*ssh, f"python3 {remote}/project/run_fixed_floor_crossop_endpoint_candidate_only_r5.py --project {remote}/project --checkpoint {binding['checkpoint_path']} --oracle {remote}/CONTROL_EMITTED_CHUNK_ORACLE.json --output {output}"], left(deadline, 120))
                (root / f"worker-g{generation}.stdout").write_text(worker.stdout); (root / f"worker-g{generation}.stderr").write_text(worker.stderr)
                candidate = root / f"PAIR_TERMINAL-candidate-g{generation}.json"
                got = call(["scp", "-i", binding["ssh_identity_path"], "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + binding["known_hosts"], binding["ssh_host"] + ":" + output + "/PAIR_TERMINAL.json", str(candidate)], left(deadline, 90))
                if worker.returncode == 0 and got.returncode == 0:
                    pair = json.loads(candidate.read_text())
                    if valid_pair(pair):
                        terminal = {"classification": "decision_bearing_candidate_only_endpoint", "science_consumed": True, "pair_sha256": sha(candidate), "pair": pair}; put(root / "PAIR_TERMINAL.json", terminal); break
                raise RuntimeError("candidate_invalid_or_unretrieved")
            except Exception as error:
                diagnostic = root / f"RECOVERABLE_DIAGNOSTIC-g{generation}.json"
                put(diagnostic, {"scope": "candidate_only", "classification": "recoverable_controller_or_consumer_failure", "error": repr(error), "generation": generation, "at_utc": now().isoformat()})
                if not wait_repair(root, deadline, generation, diagnostic):
                    terminal = {"classification": "repair_deadline_boundary", "science_consumed": False, "diagnostic": str(diagnostic)}; break
                generation += 1
        if terminal is None: terminal = {"classification": "absolute_deadline_boundary", "science_consumed": False, "generation": generation}
    finally:
        stop.set(); put(root / "TERMINAL.json", terminal or {"classification": "unknown"})
        condition = "ready" if terminal and terminal["classification"] == "decision_bearing_candidate_only_endpoint" else "maintenance"
        release(binding, condition)


if __name__ == "__main__": main()
