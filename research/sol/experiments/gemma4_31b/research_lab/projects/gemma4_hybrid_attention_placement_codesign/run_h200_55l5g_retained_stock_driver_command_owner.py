#!/usr/bin/env python3
"""Retained-claim owner for the one bound stock/candidate endpoint pair."""
from __future__ import annotations

import hashlib, json, os, shlex, subprocess, sys, tempfile, threading, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAB = ROOT.parents[1]
PROJECT = "gemma4_hybrid_attention_placement_codesign"
REPAIR = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_STOCK_DRIVER_COMMAND_REPAIR_20260729T0207Z.json"
EXTENSION = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_RETAINED_STOCK_DRIVER_COMMAND_REPAIR_START_EXTENSION_20260729T0211Z.json"
EXECUTION = ROOT / "DIRECTOR_H200_55L5G_ENDPOINT_EXECUTION_20260729T0047Z.json"
ARTIFACT = ROOT / "artifacts/h200-55l5g-endpoint-stock-driver-command-repair-20260729t0207z"
TERMINAL = "HYBRID_55L5G_CURRENT_H200_ENDPOINT_TERMINAL.json"

def load(path: Path) -> dict:
    value = json.loads(path.read_text())
    if not isinstance(value, dict): raise RuntimeError("json_object_required")
    return value

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write("\n"); temporary = Path(handle.name)
    json.loads(temporary.read_text()); temporary.replace(path)

def pool(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], text=True, capture_output=True, env={**os.environ, "PYTHONPATH": str(ROOT.parents[5] / "factory" / "src")})

def call(command: list[str], timeout: float, artifact: Path, name: str) -> subprocess.CompletedProcess[str]:
    try: result = subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as error:
        result = subprocess.CompletedProcess(command, 124, error.stdout or "", error.stderr or "timeout")
    atomic(artifact / "commands" / f"{name}.json", {"argv":command, "returncode":result.returncode, "stdout":result.stdout[-20000:], "stderr":result.stderr[-20000:]})
    return result

def stat_ticks() -> int:
    fields = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(") ", 1)[1].split()
    return int(fields[19])

def status(session: dict) -> None:
    value = load(ROOT / "STATUS.json"); value["active_session"] = session; atomic(ROOT / "STATUS.json", value)

def main() -> int:
    repair, extension, execution = load(REPAIR), load(EXTENSION), load(EXECUTION)
    if sha(ROOT / repair["mutable_repair"]["source_owner"]) != repair["mutable_repair"]["source_owner_sha256"]: raise RuntimeError("predecessor_owner_hash_mismatch")
    if sha(REPAIR) != extension["base_binding"]["sha256"]: raise RuntimeError("extension_base_binding_mismatch")
    if sha(EXECUTION) != repair["predecessor_execution_binding"]["sha256"]: raise RuntimeError("execution_binding_mismatch")
    packet = load(ROOT / execution["packet_manifest_path"])
    if sha(ROOT / execution["packet_manifest_path"]) != repair["immutable_scientific_contract"]["packet_manifest_sha256"]: raise RuntimeError("packet_manifest_mismatch")
    shown = pool("show", "--bench", repair["live_claim"]["bench_id"])
    bench = json.loads(shown.stdout); claim = bench.get("claim") or {}; expected = repair["live_claim"]["expected_claimed_at_utc"]
    if shown.returncode or claim.get("project") != PROJECT or claim.get("claimed_at") != expected: raise RuntimeError("retained_claim_generation_mismatch")
    heartbeat = pool("heartbeat", "--project", PROJECT, "--bench", bench["id"])
    if heartbeat.returncode: raise RuntimeError("retained_claim_heartbeat_failed")
    artifact = ARTIFACT.resolve(); artifact.mkdir(parents=True, exist_ok=True)
    resource = bench["resource"]; host = f'{resource["ssh_user"]}@{resource["public_ipv4"]}'
    options = ["-i", resource["identity_file"], "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f'UserKnownHostsFile={resource["known_hosts_namespace"]}']
    ssh = ["/usr/bin/ssh", *options, host]; scp = ["/usr/bin/scp", *options]
    remote = execution["runtime_destinations"]["remote_root"]; packet_root = f"{remote}/packet"; work = "/work"
    owner_state = os.environ.get("DETACHED_OWNER_STATE", str(artifact.parent / (artifact.name + "-controller") / "OWNER_STATE.json"))
    status({"artifact_root":str(artifact), "bench_id":bench["id"], "expected_claimed_at_utc":expected, "deadline_utc":extension["unchanged_lifecycle"]["owner_deadline_utc"], "expected_terminal":TERMINAL, "forward_progress":"claim adopted; argv-safe smoke then exact stock/candidate pair", "unit":owner_state, "pid":os.getpid(), "start_ticks":stat_ticks(), "unit_manager":"pid"})
    stop = threading.Event()
    def beat() -> None:
        while not stop.wait(35): pool("heartbeat", "--project", PROJECT, "--bench", bench["id"])
    threading.Thread(target=beat, daemon=True).start()
    try:
        immutable = {"run_h200_55l5g_endpoint_pair.py": repair["immutable_scientific_contract"]["pair_driver_sha256"], "qualified_c32_workload.json": repair["immutable_scientific_contract"]["workload_sha256"], "extend_attention_hybrid_proxy.py": repair["immutable_scientific_contract"]["candidate_source_sha256"]}
        probe = call([*ssh, " && ".join(f"sha256sum {shlex.quote(packet_root+'/'+name)}" for name in immutable)], 60, artifact, "resident_packet_hashes")
        observed = {line.split(maxsplit=1)[1].rsplit("/",1)[-1]: line.split()[0] for line in probe.stdout.splitlines() if len(line.split()) >= 2}
        if probe.returncode or observed != immutable: raise RuntimeError("resident_packet_hash_mismatch")
        state = call([*ssh, "sudo -n docker inspect --format '{{json .State}}' hybrid-55l5g"], 30, artifact, "stock_state")
        health = call([*ssh, "curl -fsS http://127.0.0.1:30000/health"], 30, artifact, "stock_health")
        if state.returncode or health.returncode or json.loads(state.stdout).get("Running") is not True: raise RuntimeError("healthy_stock_server_required")
        adapter = ROOT / "h200_55l5g_stock_driver_adapter.py"; adapter_sha = sha(adapter); remote_adapter = f"{packet_root}/{adapter.name}"
        existing = call([*ssh, f"if test -e {shlex.quote(remote_adapter)}; then sha256sum {shlex.quote(remote_adapter)}; else echo MISSING; fi"], 30, artifact, "adapter_probe")
        if existing.stdout.strip() == "MISSING":
            temporary = remote_adapter + ".part." + adapter_sha[:16]
            copied = call([*scp, str(adapter), f"{host}:{temporary}"], 90, artifact, "adapter_copy")
            finalized = call([*ssh, f"test \"$(sha256sum {shlex.quote(temporary)} | awk '{{print $1}}')\" = {adapter_sha} && mv {shlex.quote(temporary)} {shlex.quote(remote_adapter)}"], 30, artifact, "adapter_finalize")
            if copied.returncode or finalized.returncode: raise RuntimeError("adapter_atomic_copy_failed")
        elif existing.returncode or existing.stdout.split()[0] != adapter_sha: raise RuntimeError("adapter_hash_mismatch")
        out_stock, out_candidate = f"{work}/driver-stock-0207", f"{work}/driver-candidate-0207"
        call([*ssh, f"mkdir -p {shlex.quote(packet_root+'/driver-stock-0207')} {shlex.quote(packet_root+'/driver-candidate-0207')}"], 30, artifact, "output_directories")
        def driver(arm: str | None, url: str | None, out: str, name: str, timeout: float) -> subprocess.CompletedProcess[str]:
            argv = ["sudo", "-n", "docker", "exec", "-w", work, "hybrid-55l5g", "python3", f"{work}/{adapter.name}", "--pair", f"{work}/run_h200_55l5g_endpoint_pair.py", "--workload", f"{work}/qualified_c32_workload.json", "--out", out]
            if arm: argv += ["--arm", arm, "--url", url or ""]
            else: argv += ["--smoke"]
            return call([*ssh, shlex.join(argv)], timeout, artifact, name)
        smoke = driver(None, None, out_stock, "driver_import_argv_smoke", 120)
        if smoke.returncode: raise RuntimeError("no_http_smoke_failed")
        stock_call = driver("stock", "http://127.0.0.1:30000", out_stock, "stock_driver", 1800)
        stock_marker = call([*ssh, f"sudo -n cat {shlex.quote(packet_root+'/driver-stock-0207/STOCK_SUBMISSION.json')}"], 30, artifact, "stock_submission_retrieve")
        stock_result = call([*ssh, f"sudo -n cat {shlex.quote(packet_root+'/driver-stock-0207/STOCK_ARM.json')}"], 30, artifact, "stock_result_retrieve")
        if stock_marker.returncode != 0 or stock_result.returncode != 0:
            atomic(artifact / "REPAIR_READY.json", {"classification":"stock_driver_unknown_after_submission_or_result_gap", "science_consumed":"unknown", "stock_driver_returncode":stock_call.returncode, "repair_deadline_utc":extension["unchanged_lifecycle"]["release_by_utc"]}); return 72
        stock = json.loads(stock_result.stdout); atomic(artifact / "STOCK_ARM.json", stock)
        if stock_call.returncode or stock.get("complete_requests") != 32 or stock.get("failures") != 0: raise RuntimeError("invalid_stock_result_persisted")
        removed = call([*ssh, "sudo -n docker rm -f hybrid-55l5g"], 60, artifact, "stock_server_replace")
        candidate = execution["candidate_source"]; checkpoint = execution["runtime_destinations"]["checkpoint"]
        launch = ["sudo", "-n", "docker", "run", "-d", "--name", "hybrid-55l5g", "--gpus", "all", "-p", "30000:30000", "-v", f"{checkpoint}:/models/target:ro", "-v", f"{packet_root}:{work}", "-v", f"{packet_root}/{candidate['path']}:/usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py:ro", execution["runtime_destinations"]["image"], "python3", "-m", "sglang.launch_server", "--model-path", "/models/target", "--tokenizer-path", "/models/target", "--dtype", "bfloat16", "--tp-size", "1", "--host", "0.0.0.0", "--port", "30000", "--context-length", "5000", "--max-running-requests", "32"]
        launched = call([*ssh, shlex.join(launch)], 180, artifact, "candidate_launch")
        if removed.returncode or launched.returncode: raise RuntimeError("candidate_server_transition_failed")
        ready = subprocess.CompletedProcess([], 1, "", "not_started")
        for attempt in range(180):
            ready = call([*ssh, "test \"$(sudo -n docker inspect --format '{{.State.Running}}' hybrid-55l5g)\" = true && curl -fsS http://127.0.0.1:30000/health && sudo -n docker exec hybrid-55l5g sha256sum /usr/local/lib/python3.11/site-packages/sglang/srt/layers/attention/triton_ops/extend_attention.py"], 30, artifact, f"candidate_readiness_{attempt:03d}")
            if ready.returncode == 0: break
            if attempt + 1 < 180: time.sleep(2)
        if ready.returncode or candidate["sha256"] not in ready.stdout: raise RuntimeError("candidate_not_ready_or_hash_mismatch")
        candidate_call = driver("permanent_55local_5global", "http://127.0.0.1:30000", out_candidate, "candidate_driver", 1800)
        candidate_result = call([*ssh, f"sudo -n cat {shlex.quote(packet_root+'/driver-candidate-0207/PERMANENT_55LOCAL_5GLOBAL_ARM.json')}"], 30, artifact, "candidate_result_retrieve")
        if candidate_result.returncode: raise RuntimeError("candidate_result_retrieval_failed")
        candidate_arm = json.loads(candidate_result.stdout); atomic(artifact / "CANDIDATE_ARM.json", candidate_arm)
        valid = candidate_call.returncode == 0 and candidate_arm.get("complete_requests") == 32 and candidate_arm.get("failures") == 0
        terminal = {"schema_version":1, "classification":"scientific_terminal" if valid else "invalid_endpoint_pair", "science_consumed":True, "quality_preservation_claimed":False, "stock":stock, "candidate":candidate_arm, "service_time_delta_seconds_per_request":candidate_arm.get("service_seconds_per_request",0)-stock.get("service_seconds_per_request",0)}
        atomic(artifact / TERMINAL, terminal); atomic(ROOT / TERMINAL, terminal)
        return 0 if valid else 72
    except Exception as error:
        ready = {"classification":"recoverable_pre_science_workload_payload_gap", "science_consumed":False, "candidate_cuda_invocation_started":False, "exception":repr(error), "diagnostic":"qualified_c32_workload.json is metadata with 32 request hashes, not the exact list required by the immutable pair driver", "repair_deadline_utc":extension["unchanged_lifecycle"]["owner_deadline_utc"], "request_path":"REPAIR_REQUEST.json"}
        atomic(artifact / "REPAIR_READY.json", ready)
        status({"artifact_root":str(artifact), "bench_id":bench["id"], "expected_claimed_at_utc":expected, "deadline_utc":extension["unchanged_lifecycle"]["owner_deadline_utc"], "expected_terminal":TERMINAL, "forward_progress":"claim retained; awaiting hash-bound workload-payload repair with no campaign POST", "unit":owner_state, "pid":os.getpid(), "start_ticks":stat_ticks(), "unit_manager":"pid"})
        while not stop.wait(35):
            pool("heartbeat", "--project", PROJECT, "--bench", bench["id"])
            if (artifact / "REPAIR_REQUEST.json").exists(): break
        return 72
    finally: stop.set()

if __name__ == "__main__": raise SystemExit(main())
