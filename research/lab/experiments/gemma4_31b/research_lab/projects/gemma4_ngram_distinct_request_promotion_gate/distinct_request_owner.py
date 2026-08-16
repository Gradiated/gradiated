#!/usr/bin/env python3
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
DETACHED_OWNER = Path("/root/workspace/research/factory/tools/detached-owner")
REPAIR_HANDSHAKE = Path("/root/workspace/research/factory/tools/repair-handshake")
PROJECT = "gemma4_ngram_distinct_request_promotion_gate"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = Path("/home/glmrunner/gemma4-distinct-request-promotion")
CONTAINER_ROOT = Path("/home/glmrunner/gemma4-ngram-tail-overlap")
PREDECESSOR_STATUS = P.parent / "gemma4_ngram_sustained_acceptance_causal" / "STATUS.json"
PREDECESSOR_DEADLINE = dt.datetime(2026, 7, 25, 5, 3, tzinfo=dt.timezone.utc)
DEADLINE = dt.datetime(2026, 7, 25, 6, 0, tzinfo=dt.timezone.utc)
RATE = 2.46


def now():
    return dt.datetime.now(dt.timezone.utc)


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    part.replace(path)


def run(args, timeout=None, **kwargs):
    return subprocess.run(args, text=True, capture_output=True, check=False, timeout=timeout, **kwargs)


def pool(*args):
    return run(
        ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), *args],
        env={**os.environ, "PYTHONPATH": str(FACTORY)},
    )


def ssh(ip, command, timeout=900):
    return run(
        [
            "ssh", "-i", str(KEY), "-o", "BatchMode=yes", "-o", "ServerAliveInterval=20",
            "-o", "ServerAliveCountMax=3", "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={KNOWN}", f"glmrunner@{ip}", command,
        ],
        timeout=timeout,
    )


def scp(ip, source, target):
    return run(
        [
            "scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}",
            str(source), f"glmrunner@{ip}:{target}",
        ],
        timeout=300,
    )


def scp_from(ip, source, target):
    return run(
        [
            "scp", "-p", "-i", str(KEY), "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}",
            f"glmrunner@{ip}:{source}", str(target),
        ],
        timeout=300,
    )


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ip_address():
    sys.path.insert(0, str(NEBIUS))
    from placement_control import extract_public_ipv4, get_instance
    return extract_public_ipv4(get_instance("computeinstance-e00kcm9nfhwt7e7gbc"))


def status(summary, spend, active_session=None, terminal=None):
    state = json.loads((P / "STATUS.json").read_text())
    state["summary"] = summary
    state["actual_spend_usd"] = spend
    state["active_session"] = active_session
    if terminal is not None:
        state["terminal"] = terminal
    atomic(P / "STATUS.json", state)


def bench_state():
    result = pool("list")
    if result.returncode:
        raise RuntimeError("typed_pool_boundary:list:" + result.stderr[-500:])
    benches = json.loads(result.stdout)["benches"]
    return next(bench for bench in benches if bench["id"] == BENCH)


def stage_packet(ip, artifact):
    packet = artifact / "PACKET.tar"
    made = run(
        [
            "tar",
            "-cf",
            str(packet),
            "-C",
            str(P),
            "inputs",
            "remote_distinct_request_endpoint.py",
            "distinct_request_sitecustomize.py",
            "distinct_request_gate.py",
            "artifacts/offline-source-probe/RESULT.json",
        ]
    )
    if made.returncode:
        raise RuntimeError("recoverable_packet_defect:" + made.stderr[-500:])
    prepared = ssh(ip, f"mkdir -p {shlex.quote(str(REMOTE))}", 60)
    if prepared.returncode:
        raise RuntimeError("recoverable_remote_directory_defect:" + prepared.stderr[-500:])
    target = REMOTE / "PACKET.tar"
    copied = scp(ip, packet, str(target) + ".part")
    if copied.returncode:
        raise RuntimeError("recoverable_packet_transfer_defect:" + copied.stderr[-500:])
    packet_sha256 = digest(packet)
    extracted = ssh(
        ip,
        f"test \"$(sha256sum {shlex.quote(str(target))}.part | cut -d' ' -f1)\" = {packet_sha256} "
        f"&& mv -f {shlex.quote(str(target))}.part {shlex.quote(str(target))} "
        f"&& cd {shlex.quote(str(REMOTE))} && tar -xf PACKET.tar",
        180,
    )
    atomic(
        artifact / "PACKET.json",
        {
            "packet_sha256": packet_sha256,
            "remote_root": str(REMOTE),
            "returncode": extracted.returncode,
            "stderr": extracted.stderr,
        },
    )
    if extracted.returncode:
        raise RuntimeError("recoverable_packet_extract_defect:" + extracted.stderr[-500:])


def retrieve(ip, remote_out, local_root):
    pack = f"/home/glmrunner/{remote_out.name}.tar.gz"
    command = (
        f"tar -czf {shlex.quote(pack)} -C {shlex.quote(str(remote_out.parent))} "
        f"{shlex.quote(remote_out.name)} && sha256sum {shlex.quote(pack)}"
    )
    made = ssh(ip, command, 300)
    (local_root / f"{remote_out.name}.archive.stdout").write_text(made.stdout)
    (local_root / f"{remote_out.name}.archive.stderr").write_text(made.stderr)
    if made.returncode:
        raise RuntimeError(f"recoverable_retrieval_defect:{remote_out.name}:archive")
    target = local_root / f"{remote_out.name}.tar.gz"
    copied = scp_from(ip, pack, target)
    if copied.returncode:
        raise RuntimeError(f"recoverable_retrieval_defect:{remote_out.name}:scp:{copied.stderr[-400:]}")
    if digest(target) != made.stdout.split()[0]:
        raise RuntimeError(f"recoverable_retrieval_defect:{remote_out.name}:hash")
    extracted = run(["tar", "-xzf", str(target), "-C", str(local_root)])
    if extracted.returncode:
        raise RuntimeError(f"recoverable_retrieval_defect:{remote_out.name}:extract")
    return local_root / remote_out.name


def launch_stage(ip, artifact, label, count):
    remote_out = REMOTE / f"out-{label}-{artifact.name}"
    command = (
        f"cd {shlex.quote(str(REMOTE))} && "
        f"test ! -e {shlex.quote(str(remote_out))} && "
        f"env DISTINCT_REQUEST_ROOT={shlex.quote(str(REMOTE))} "
        f"DISTINCT_REQUEST_RESULT_OUT={shlex.quote(str(remote_out))} "
        f"DISTINCT_REQUEST_CONTAINER_OUT={shlex.quote(str(CONTAINER_ROOT / 'out'))} "
        f"DISTINCT_REQUEST_REQUESTS={count} python3 remote_distinct_request_endpoint.py"
    )
    result = ssh(ip, command, max(60, int((DEADLINE - now()).total_seconds())))
    (artifact / f"{label}.worker.stdout").write_text(result.stdout)
    (artifact / f"{label}.worker.stderr").write_text(result.stderr)
    local_out = retrieve(ip, remote_out, artifact)
    terminal_path = local_out / "FINAL_TERMINAL.json"
    attempt_path = local_out / "ATTEMPT_TERMINAL.json"
    if terminal_path.exists():
        return json.loads(terminal_path.read_text()), local_out
    diagnostic = json.loads(attempt_path.read_text()) if attempt_path.exists() else {
        "classification": "recoverable_worker_exit_without_terminal",
        "error": result.stderr[-4000:],
        "candidate_science_consumed": False,
    }
    raise RuntimeError("recoverable_remote_stage:" + json.dumps(diagnostic, sort_keys=True))


def activate(ip, artifact, label):
    trace_archive = CONTAINER_ROOT / "out" / f"distinct-request-ngram.before-{label}.jsonl"
    command = (
        f"test ! -e {shlex.quote(str(trace_archive))} && "
        f"if test -e {shlex.quote(str(CONTAINER_ROOT / 'out/distinct-request-ngram.jsonl'))}; "
        f"then mv {shlex.quote(str(CONTAINER_ROOT / 'out/distinct-request-ngram.jsonl'))} {shlex.quote(str(trace_archive))}; fi; "
        f"rm -f {shlex.quote(str(CONTAINER_ROOT / 'out/OVERLAY_STATE.json'))}; "
        f"sudo docker cp {shlex.quote(str(REMOTE / 'distinct_request_gate.py'))} "
        f"gemma4-ngram-tail-overlap:/usr/lib/python3.12/distinct_request_gate.py && "
        f"sudo docker cp {shlex.quote(str(REMOTE / 'distinct_request_sitecustomize.py'))} "
        f"gemma4-ngram-tail-overlap:/usr/lib/python3.12/sitecustomize.py && "
        f"sudo docker restart gemma4-ngram-tail-overlap >/dev/null"
    )
    restarted = ssh(ip, command, 180)
    (artifact / f"{label}.restart.stdout").write_text(restarted.stdout)
    (artifact / f"{label}.restart.stderr").write_text(restarted.stderr)
    if restarted.returncode:
        raise RuntimeError(f"recoverable_activation_restart:{label}:{restarted.stderr[-600:]}")
    verify = ssh(
        ip,
        "for i in $(seq 1 180); do "
        "if test -s /home/glmrunner/gemma4-ngram-tail-overlap/out/OVERLAY_STATE.json "
        "&& grep -q worker_initialized /home/glmrunner/gemma4-ngram-tail-overlap/out/distinct-request-ngram.jsonl "
        "&& curl -fsS http://127.0.0.1:30000/v1/models >/dev/null; then "
        "sha256sum /usr/lib/python3.12/sitecustomize.py; "
        "cat /home/glmrunner/gemma4-ngram-tail-overlap/out/OVERLAY_STATE.json; exit 0; fi; sleep 2; done; "
        "sudo docker logs --tail 120 gemma4-ngram-tail-overlap >&2; exit 1",
        420,
    )
    (artifact / f"{label}.activation.stdout").write_text(verify.stdout)
    (artifact / f"{label}.activation.stderr").write_text(verify.stderr)
    if verify.returncode:
        raise RuntimeError(f"recoverable_activation_proof_missing:{label}:{verify.stderr[-1200:]}")


def main():
    global DEADLINE
    artifact = P / "artifacts" / now().strftime("distinct-request-%Y%m%dt%H%M%Sz")
    artifact.mkdir(parents=True)
    prior = float(json.loads((P / "STATUS.json").read_text())["actual_spend_usd"])
    offline = json.loads((P / "artifacts/offline-source-probe/RESULT.json").read_text())
    if offline.get("result") != "offline_distinct_request_support_two_gate_pass":
        raise RuntimeError("offline_gate_not_passed")
    claim_cutoff = DEADLINE - dt.timedelta(minutes=22)
    while now() < claim_cutoff:
        state = bench_state()
        atomic(
            artifact / "QUEUE_STATE.json",
            {
                "at_utc": now().isoformat(),
                "predecessor": "gemma4_ngram_sustained_acceptance_causal",
                "predecessor_deadline_utc": PREDECESSOR_DEADLINE.isoformat(),
                "bench_status": state["status"],
                "claim": state.get("claim"),
            },
        )
        if state["status"] == "available" and state.get("claim") is None:
            break
        time.sleep(20)
    else:
        terminal = {
            "classification": "typed_predecessor_or_time_boundary",
            "candidate_sample_consumed": False,
            "need": "released warm H200 with at least 22 minutes before 06:00Z",
        }
        status(
            "Offline gate passed, but the priority-8600 predecessor did not release enough time for an interpretable discriminator.",
            prior,
            None,
            terminal,
        )
        atomic(P / "OWNER_TERMINAL.json", {"at_utc": now().isoformat(), "disposition": "typed_predecessor_or_time_boundary", "conservative_provider_spend_usd": prior, "artifact_root": str(artifact)})
        return
    claim = pool(
        "claim",
        "--project",
        PROJECT,
        "--bench",
        BENCH,
        "--lease-seconds",
        "300",
    )
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        raise RuntimeError("typed_pool_boundary:claim:" + claim.stderr[-500:])
    started = time.monotonic()
    DEADLINE = min(DEADLINE, now() + dt.timedelta(minutes=50))
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT)
            atomic(P / "OWNER_HEARTBEAT.json", {"at_utc": now().isoformat(), "returncode": result.returncode, "stderr": result.stderr})

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    disposition = "maintenance"
    discriminator = None
    full = None
    attempt = 0
    try:
        ip = ip_address()
        while True:
            try:
                stage_packet(ip, artifact)
                if discriminator is None:
                    activate(ip, artifact, f"discriminator-a{attempt}")
                    discriminator, _ = launch_stage(
                        ip,
                        artifact,
                        f"discriminator-0-790-a{attempt}",
                        791,
                    )
                decision = discriminator.get("decision", {})
                activation_exact = (
                    discriminator.get("overlay", {}).get("overlay")
                    == "distinct_request_support_two_write_promotion"
                    and decision.get("positive_activation_identity") is True
                    and discriminator.get("overlay_trace_rows", 0) > 0
                )
                semantics_exact = decision.get("normalized_semantics_exact") is True
                reliability_exact = decision.get("failures_zero") is True
                unaffected_long = (
                    decision.get("unaffected_requests_retain_long_trunks") is True
                )
                discriminator_pass = (
                    activation_exact
                    and semantics_exact
                    and reliability_exact
                    and unaffected_long
                )
                if discriminator_pass and now() < DEADLINE - dt.timedelta(minutes=18):
                    activate(ip, artifact, f"full-a{attempt}")
                    full, _ = launch_stage(
                        ip,
                        artifact,
                        f"full-0-1035-a{attempt}",
                        1036,
                    )
                break
            except Exception as exc:
                diagnostic = {
                    "classification": "recoverable_integration_or_consumer_defect",
                    "error": repr(exc),
                    "candidate_science_consumed": discriminator is not None,
                    "discriminator_persisted": discriminator is not None,
                    "full_endpoint_persisted": full is not None,
                }
                atomic(artifact / f"ATTEMPT_{attempt}_FAILURE.json", diagnostic)
                if attempt > 0 or now() >= DEADLINE - dt.timedelta(minutes=4):
                    raise
                ready = run(
                    [
                        str(REPAIR_HANDSHAKE),
                        "ready",
                        "--root",
                        str(artifact),
                        "--deadline",
                        (DEADLINE - dt.timedelta(minutes=2)).isoformat().replace("+00:00", "Z"),
                        "--failure-kind",
                        "integration_or_consumer_defect",
                        "--diagnostic",
                        json.dumps(diagnostic, sort_keys=True),
                        "--retry-scope",
                        "patch and repeat only the unpersisted discriminator or full consumer",
                    ]
                )
                if ready.returncode:
                    raise RuntimeError("repair_handshake_ready_failed:" + ready.stderr[-500:]) from exc
                status(
                    "Recoverable defect retrieved; the durable owner is heartbeating the retained claim and waiting for one hash-bound repair.",
                    prior + (time.monotonic() - started) / 3600 * RATE,
                    json.loads((P / "STATUS.json").read_text()).get("active_session"),
                    diagnostic,
                )
                while now() < DEADLINE - dt.timedelta(minutes=2):
                    repair = run(
                        [
                            str(REPAIR_HANDSHAKE),
                            "status",
                            "--root",
                            str(artifact),
                        ]
                    )
                    if repair.returncode == 0:
                        atomic(
                            artifact / "REPAIR_CONSUMED.json",
                            json.loads(repair.stdout),
                        )
                        attempt += 1
                        break
                    time.sleep(20)
                else:
                    raise RuntimeError("typed_repair_deadline_boundary") from exc
        spend = prior + (time.monotonic() - started) / 3600 * RATE
        terminal = {
            "classification": "full_endpoint_complete" if full else "discriminator_complete",
            "artifact_root": str(artifact.relative_to(P)),
            "candidate_sample_consumed": True,
            "discriminator": {
                "activation_proved": activation_exact,
                "normalized_semantics_exact": semantics_exact,
                "failures_zero": reliability_exact,
                "unaffected_requests_retain_long_trunks": unaffected_long,
                "passed": discriminator_pass,
                "requests": discriminator.get("primary", {}).get("requests"),
            },
            "full_endpoint": full,
        }
        status(
            "Distinct-request discriminator completed; conditional full endpoint "
            + ("completed." if full else "was not admitted within the release budget."),
            spend,
            None,
            terminal,
        )
        contents = {
            "schema_version": 1,
            "project": PROJECT,
            "result": terminal["classification"],
            "artifacts": str(artifact.relative_to(P)),
            "candidate_sample_consumed": True,
            "server_state": "Healthy patched SGLang server remains loaded; director disposition required before incompatible reuse.",
            "checkpoint": "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.",
            "runtime": "Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, native depth-12 NGRAM.",
            "activation_proved": activation_exact,
            "discriminator_semantics_exact": semantics_exact,
            "discriminator_unaffected_long_trunks": unaffected_long,
            "conditional_full_endpoint_consumed": full is not None,
        }
        atomic(P / "BENCH_CONTENTS.json", contents)
        release = pool("release", "--project", PROJECT, "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json"))
        (artifact / "release.stdout").write_text(release.stdout)
        (artifact / "release.stderr").write_text(release.stderr)
        disposition = "terminal_retrieved_released_maintenance"
    except Exception as exc:
        spend = prior + (time.monotonic() - started) / 3600 * RATE
        diagnostic = {"classification": "recoverable_repair_attempt", "error": repr(exc), "candidate_science_consumed": discriminator is not None, "discriminator_persisted": discriminator is not None}
        atomic(artifact / "OWNER_EXCEPTION.json", diagnostic)
        contents = {
            "schema_version": 1,
            "project": PROJECT,
            "result": "recoverable_repair_attempt",
            "artifacts": str(artifact.relative_to(P)),
            "server_state": "Retained patched server requires director inspection.",
            "candidate_sample_consumed": discriminator is not None,
            "error": repr(exc),
        }
        atomic(P / "BENCH_CONTENTS.json", contents)
        release = pool("release", "--project", PROJECT, "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json"))
        (artifact / "release.stdout").write_text(release.stdout)
        (artifact / "release.stderr").write_text(release.stderr)
        status("Recoverable defect retained with compact diagnostics; bench released to maintenance for deliberate recovery.", spend, None, diagnostic)
        disposition = "recoverable_release_maintenance"
    finally:
        stop.set()
        thread.join(2)
        atomic(P / "OWNER_TERMINAL.json", {"at_utc": now().isoformat(), "disposition": disposition, "conservative_provider_spend_usd": prior + (time.monotonic() - started) / 3600 * RATE, "artifact_root": str(artifact)})


if __name__ == "__main__":
    main()
