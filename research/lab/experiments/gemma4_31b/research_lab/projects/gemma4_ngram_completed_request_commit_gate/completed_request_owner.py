#!/usr/bin/env python3
"""Durable owner for the one admitted completed-request discriminator."""
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path

P = Path(__file__).resolve().parent
LAB = P.parents[1]
FACTORY = Path("/root/workspace/research/factory/src")
NEBIUS = Path("/root/workspace/research/lab/experiments/glm47flash/campaign_100/nebius")
KEY = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = Path("/root/.config/nebius/glm-campaign/known_hosts")
PROJECT = "gemma4_ngram_completed_request_commit_gate"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = Path("/home/glmrunner/gemma4-completed-request-commit")
CONTAINER = "gemma4-ngram-tail-overlap"
CONTAINER_OUT = Path("/home/glmrunner/gemma4-ngram-tail-overlap/out")
DEADLINE = dt.datetime(2026, 7, 25, 6, 0, tzinfo=dt.timezone.utc)
RATE = 2.46

def now(): return dt.datetime.now(dt.timezone.utc)
def atomic(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n"); part.replace(path)
def run(args, timeout=None, **kwargs): return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout, **kwargs)
def pool(*args): return run(["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args], env={**os.environ, "PYTHONPATH": str(FACTORY)})
def ssh(ip, command, timeout=900):
    return run(["ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ServerAliveInterval=20", "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{ip}", command], timeout)
def scp(ip, source, target):
    return run(["scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", str(source), f"glmrunner@{ip}:{target}"], 600)
def scp_from(ip, source, target):
    return run(["scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{ip}:{source}", str(target)], 600)
def digest(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def ip_address():
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance
    value = extract_public_ipv4(get_instance("computeinstance-e00kcm9nfhwt7e7gbc"))
    if not value: raise RuntimeError("typed_provider_boundary:no_public_ip")
    return value
def status(summary, spend, session=None, terminal=None):
    state = json.loads((P / "STATUS.json").read_text())
    state.update({"summary": summary, "actual_spend_usd": spend, "active_session": session})
    if terminal is not None: state["terminal"] = terminal
    atomic(P / "STATUS.json", state)
def stage_packet(ip, artifact):
    packet = artifact / "PACKET.tar"
    members = ["inputs", "completed_request_buffer.py", "completed_request_sitecustomize.py", "remote_completed_request_endpoint.py", "EXECUTION_BINDING.json", "DIRECTOR_BINDING_VERIFIED.json", "artifacts/offline-lifecycle-probe/RESULT.json"]
    made = run(["tar", "-cf", str(packet), "-C", str(P), *members])
    if made.returncode: raise RuntimeError("recoverable_packet_defect:" + made.stderr[-500:])
    target = REMOTE / "PACKET.tar"; expected = digest(packet)
    command = f"mkdir -p {shlex.quote(str(REMOTE))} && rm -f {shlex.quote(str(target))}.{expected}.part && true"
    if ssh(ip, command, 60).returncode: raise RuntimeError("recoverable_remote_directory_defect")
    copied = scp(ip, packet, str(target) + f".{expected}.part")
    if copied.returncode: raise RuntimeError("recoverable_packet_transfer_defect:" + copied.stderr[-500:])
    extracted = ssh(ip, f"test \"$(sha256sum {shlex.quote(str(target))}.{expected}.part | cut -d' ' -f1)\" = {expected} && mv -f {shlex.quote(str(target))}.{expected}.part {shlex.quote(str(target))} && cd {shlex.quote(str(REMOTE))} && tar -xf PACKET.tar", 240)
    atomic(artifact / "PACKET.json", {"packet_sha256": expected, "remote_root": str(REMOTE), "returncode": extracted.returncode, "stderr": extracted.stderr})
    if extracted.returncode: raise RuntimeError("recoverable_packet_extract_defect:" + extracted.stderr[-500:])
def activate(ip, artifact):
    old_trace = CONTAINER_OUT / f"completed-request-ngram.before-{artifact.name}.jsonl"
    command = f"test ! -e {shlex.quote(str(old_trace))} && if test -e {shlex.quote(str(CONTAINER_OUT / 'completed-request-ngram.jsonl'))}; then mv {shlex.quote(str(CONTAINER_OUT / 'completed-request-ngram.jsonl'))} {shlex.quote(str(old_trace))}; fi; rm -f {shlex.quote(str(CONTAINER_OUT / 'OVERLAY_STATE.json'))}; sudo docker cp {shlex.quote(str(REMOTE / 'completed_request_buffer.py'))} {CONTAINER}:/usr/lib/python3.12/completed_request_buffer.py && sudo docker cp {shlex.quote(str(REMOTE / 'completed_request_sitecustomize.py'))} {CONTAINER}:/usr/lib/python3.12/sitecustomize.py && sudo docker restart {CONTAINER} >/dev/null"
    restarted = ssh(ip, command, 240)
    (artifact / "activation.restart.stdout").write_text(restarted.stdout); (artifact / "activation.restart.stderr").write_text(restarted.stderr)
    if restarted.returncode: raise RuntimeError("recoverable_activation_restart:" + restarted.stderr[-800:])
    proof = ssh(ip, f"for i in $(seq 1 180); do if test -s {shlex.quote(str(CONTAINER_OUT / 'OVERLAY_STATE.json'))} && grep -q worker_initialized {shlex.quote(str(CONTAINER_OUT / 'completed-request-ngram.jsonl'))} && curl -fsS http://127.0.0.1:30000/v1/models >/dev/null; then sha256sum /usr/lib/python3.12/sitecustomize.py; cat {shlex.quote(str(CONTAINER_OUT / 'OVERLAY_STATE.json'))}; exit 0; fi; sleep 2; done; sudo docker logs --tail 120 {CONTAINER} >&2; exit 1", 420)
    (artifact / "activation.proof.stdout").write_text(proof.stdout); (artifact / "activation.proof.stderr").write_text(proof.stderr)
    if proof.returncode: raise RuntimeError("recoverable_activation_proof_missing:" + proof.stderr[-1200:])
def retrieve(ip, remote_out, artifact):
    archive = f"/home/glmrunner/{remote_out.name}.tar.gz"
    made = ssh(ip, f"tar -czf {shlex.quote(archive)} -C {shlex.quote(str(remote_out.parent))} {shlex.quote(remote_out.name)} && sha256sum {shlex.quote(archive)}", 300)
    (artifact / "archive.stdout").write_text(made.stdout); (artifact / "archive.stderr").write_text(made.stderr)
    if made.returncode: raise RuntimeError("recoverable_retrieval_defect:archive")
    local = artifact / Path(archive).name
    copied = scp_from(ip, archive, local)
    if copied.returncode: raise RuntimeError("recoverable_retrieval_defect:scp:" + copied.stderr[-500:])
    if digest(local) != made.stdout.split()[0]: raise RuntimeError("recoverable_retrieval_defect:hash")
    if run(["tar", "-xzf", str(local), "-C", str(artifact)]).returncode: raise RuntimeError("recoverable_retrieval_defect:extract")
    return artifact / remote_out.name
def launch(ip, artifact):
    remote_out = REMOTE / f"out-discriminator-0-790-{artifact.name}"
    command = f"cd {shlex.quote(str(REMOTE))} && test ! -e {shlex.quote(str(remote_out))} && env COMPLETED_REQUEST_ROOT={shlex.quote(str(REMOTE))} COMPLETED_REQUEST_RESULT_OUT={shlex.quote(str(remote_out))} COMPLETED_REQUEST_CONTAINER_OUT={shlex.quote(str(CONTAINER_OUT))} COMPLETED_REQUEST_REQUESTS=791 python3 remote_completed_request_endpoint.py"
    result = ssh(ip, command, max(60, int((DEADLINE - now()).total_seconds())))
    (artifact / "worker.stdout").write_text(result.stdout); (artifact / "worker.stderr").write_text(result.stderr)
    local = retrieve(ip, remote_out, artifact)
    final = local / "FINAL_TERMINAL.json"; attempt = local / "ATTEMPT_TERMINAL.json"
    if final.exists(): return json.loads(final.read_text()), local
    diagnostic = json.loads(attempt.read_text()) if attempt.exists() else {"classification":"recoverable_worker_exit_without_terminal", "error":result.stderr[-4000:], "candidate_science_consumed":False}
    raise RuntimeError("recoverable_remote_stage:" + json.dumps(diagnostic, sort_keys=True))
def main():
    artifact = P / "artifacts" / now().strftime("completed-request-%Y%m%dt%H%M%Sz"); artifact.mkdir(parents=True)
    prior = float(json.loads((P / "STATUS.json").read_text()).get("actual_spend_usd", 0.0))
    claim = pool("claim", "--project", PROJECT, "--bench", BENCH, "--lease-seconds", "300")
    (artifact / "claim.stdout").write_text(claim.stdout); (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode: raise RuntimeError("typed_pool_boundary:claim:" + claim.stderr[-500:])
    started = time.monotonic(); deadline = min(DEADLINE, now() + dt.timedelta(minutes=45)); stop = threading.Event(); terminal = None; disposition = "claim_retained_for_repair"
    def beat():
        while not stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT); atomic(P / "OWNER_HEARTBEAT.json", {"at_utc":now().isoformat(), "returncode":result.returncode, "stderr":result.stderr})
    thread = threading.Thread(target=beat, daemon=True); thread.start()
    try:
        ip = ip_address(); stage_packet(ip, artifact); activate(ip, artifact)
        terminal, _ = launch(ip, artifact)
        spent = prior + (time.monotonic()-started)/3600*RATE
        decision = terminal.get("decision", {})
        gate = all(decision.get(k) is True for k in ("positive_activation_identity", "normalized_semantics_exact", "failures_zero", "post_request_32_unaffected_requests_retain_long_trunks"))
        record = {"classification":"discriminator_complete", "artifact_root":str(artifact.relative_to(P)), "candidate_sample_consumed":terminal.get("candidate_science_consumed", False), "endpoint_admitted":gate, "discriminator_decision":decision}
        status("Completed-request discriminator retrieved; full endpoint not run unless every recorded gate passes within the immutable deadline.", spent, None, record)
        contents = {"schema_version":1,"project":PROJECT,"result":terminal.get("result"),"artifacts":str(artifact.relative_to(P)),"candidate_sample_consumed":terminal.get("candidate_science_consumed",False),"activation_proved":decision.get("positive_activation_identity"),"discriminator_semantics_exact":decision.get("normalized_semantics_exact"),"discriminator_unaffected_long_trunks":decision.get("post_request_32_unaffected_requests_retain_long_trunks"),"conditional_full_endpoint_consumed":False,"server_state":"Healthy completed-request-patched SGLang server remains loaded; director disposition required before incompatible reuse.","checkpoint":"/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.","runtime":"Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, native depth-12 NGRAM."}
        atomic(P / "BENCH_CONTENTS.json", contents)
        release = pool("release", "--project", PROJECT, "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json")); (artifact / "release.stdout").write_text(release.stdout); (artifact / "release.stderr").write_text(release.stderr)
        disposition = "scientific_terminal_retrieved_released_maintenance"
    except Exception as exc:
        spent = prior + (time.monotonic()-started)/3600*RATE
        diagnostic = {"classification":"recoverable_integration_or_consumer_defect", "error":repr(exc), "candidate_science_consumed":bool(terminal and terminal.get("candidate_science_consumed")), "artifact_root":str(artifact.relative_to(P))}
        atomic(artifact / "OWNER_EXCEPTION.json", diagnostic)
        status("Recoverable defect retained under the claimed bench for in-place repair; do not release before evidence retrieval.", spent, json.loads((P / "STATUS.json").read_text()).get("active_session"), diagnostic)
        disposition = "repair_ready_claim_retained"
    finally:
        stop.set(); thread.join(2)
        atomic(P / "OWNER_TERMINAL.json", {"at_utc":now().isoformat(), "disposition":disposition, "conservative_provider_spend_usd":prior + (time.monotonic()-started)/3600*RATE, "artifact_root":str(artifact)})
if __name__ == "__main__": main()
