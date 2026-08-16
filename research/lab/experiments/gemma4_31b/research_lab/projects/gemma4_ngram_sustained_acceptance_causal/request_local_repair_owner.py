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
PROJECT = "gemma4_ngram_sustained_acceptance_causal"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
REMOTE = Path("/home/glmrunner/gemma4-request-local-verified-trunk")
CONTAINER_ROOT = Path("/home/glmrunner/gemma4-ngram-tail-overlap")
DEADLINE = dt.datetime(2026, 7, 25, 5, 3, tzinfo=dt.timezone.utc)
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
        f"env REQUEST_LOCAL_ROOT={shlex.quote(str(REMOTE))} "
        f"REQUEST_LOCAL_RESULT_OUT={shlex.quote(str(remote_out))} "
        f"REQUEST_LOCAL_CONTAINER_OUT={shlex.quote(str(CONTAINER_ROOT / 'out'))} "
        f"REQUEST_LOCAL_REQUESTS={count} python3 remote_request_local_endpoint.py"
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
    trace_archive = CONTAINER_ROOT / "out" / f"request-local-ngram.before-{label}.jsonl"
    command = (
        f"test ! -e {shlex.quote(str(trace_archive))} && "
        f"if test -e {shlex.quote(str(CONTAINER_ROOT / 'out/request-local-ngram.jsonl'))}; "
        f"then mv {shlex.quote(str(CONTAINER_ROOT / 'out/request-local-ngram.jsonl'))} {shlex.quote(str(trace_archive))}; fi; "
        f"rm -f {shlex.quote(str(CONTAINER_ROOT / 'out/OVERLAY_STATE.json'))}; "
        f"sudo docker cp {shlex.quote(str(REMOTE / 'request_local_verified_trunk_sitecustomize.py'))} "
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
        "&& grep -q worker_initialized /home/glmrunner/gemma4-ngram-tail-overlap/out/request-local-ngram.jsonl "
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
    artifact = P / "artifacts" / now().strftime("repair-localization-%Y%m%dt%H%M%Sz")
    artifact.mkdir(parents=True)
    prior = float(json.loads((P / "STATUS.json").read_text())["actual_spend_usd"])
    started = time.monotonic()
    claim = pool("claim", "--project", PROJECT, "--bench", BENCH, "--lease-seconds", "300")
    (artifact / "claim.stdout").write_text(claim.stdout)
    (artifact / "claim.stderr").write_text(claim.stderr)
    if claim.returncode:
        raise RuntimeError("typed_pool_boundary:claim:" + claim.stderr[-500:])
    stop = threading.Event()

    def heartbeat():
        while not stop.wait(45):
            result = pool("heartbeat", "--project", PROJECT)
            atomic(P / "OWNER_HEARTBEAT.json", {"at_utc": now().isoformat(), "returncode": result.returncode, "stderr": result.stderr})

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    disposition = "maintenance"
    try:
        ip = ip_address()
        for name in ("request_local_verified_trunk_sitecustomize.py", "remote_request_local_endpoint.py"):
            source = P / name
            target = REMOTE / name
            staged = scp(ip, source, str(target) + ".part")
            if staged.returncode:
                raise RuntimeError(f"recoverable_staging_defect:{name}:{staged.stderr[-500:]}")
            verified = ssh(
                ip,
                f"test \"$(sha256sum {shlex.quote(str(target))}.part | cut -d' ' -f1)\" = {digest(source)} "
                f"&& mv -f {shlex.quote(str(target))}.part {shlex.quote(str(target))}",
                60,
            )
            if verified.returncode:
                raise RuntimeError(f"recoverable_staging_hash_defect:{name}")
        activate(ip, artifact, "discriminator-" + artifact.name)
        discriminator, discriminator_out = launch_stage(ip, artifact, "discriminator-0-790", 791)
        activation_exact = (
            discriminator.get("overlay", {}).get("overlay") == "request_local_verified_trunk"
            and discriminator.get("overlay_trace_rows", 0) > 0
        )
        semantics_exact = discriminator.get("decision", {}).get("normalized_semantics_exact") is True
        full = None
        if activation_exact and semantics_exact and now() < DEADLINE - dt.timedelta(minutes=13):
            activate(ip, artifact, "full-" + artifact.name)
            full, _ = launch_stage(ip, artifact, "repaired-full-0-1035", 1036)
        spend = prior + (time.monotonic() - started) / 3600 * RATE
        terminal = {
            "classification": "repaired_full_endpoint_complete" if full else "localization_discriminator_complete",
            "artifact_root": str(artifact.relative_to(P)),
            "repair_candidate_sample_consumed": True,
            "discriminator": {
                "activation_proved": activation_exact,
                "normalized_semantics_exact": semantics_exact,
                "requests": discriminator.get("primary", {}).get("requests"),
            },
            "full_endpoint": full,
        }
        status(
            "Activation-localization discriminator completed; conditional repaired endpoint "
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
            "repair_candidate_sample_consumed": True,
            "server_state": "Healthy patched SGLang server remains loaded; director disposition required before incompatible reuse.",
            "checkpoint": "/home/glmrunner/gemma4-h200-ngram-decode-equivalent-verifier/checkpoint remains resident and read-only.",
            "runtime": "Pinned SGLang v0.5.13 FP8, page-1 E5M2 KV, native depth-12 NGRAM.",
            "activation_proved": activation_exact,
            "discriminator_semantics_exact": semantics_exact,
            "conditional_full_endpoint_consumed": full is not None,
        }
        atomic(P / "BENCH_CONTENTS.json", contents)
        release = pool("release", "--project", PROJECT, "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json"))
        (artifact / "release.stdout").write_text(release.stdout)
        (artifact / "release.stderr").write_text(release.stderr)
        disposition = "terminal_retrieved_released_maintenance"
    except Exception as exc:
        spend = prior + (time.monotonic() - started) / 3600 * RATE
        diagnostic = {"classification": "recoverable_repair_attempt", "error": repr(exc), "candidate_science_consumed": False}
        atomic(artifact / "OWNER_EXCEPTION.json", diagnostic)
        atomic(P / "REPAIR_READY.json", {"at_utc": now().isoformat(), "deadline_utc": DEADLINE.isoformat().replace("+00:00", "Z"), "artifact_root": str(artifact.relative_to(P)), "bench_id": BENCH, "diagnostic": diagnostic})
        status("Recoverable activation/localization defect retained under the claimed warm bench.", spend, None, diagnostic)
        if now() >= DEADLINE - dt.timedelta(minutes=1):
            contents = {
                "schema_version": 1,
                "project": PROJECT,
                "result": "recoverable_repair_attempt",
                "artifacts": str(artifact.relative_to(P)),
                "server_state": "Retained patched server requires director inspection.",
                "error": repr(exc),
            }
            atomic(P / "BENCH_CONTENTS.json", contents)
            pool("release", "--project", PROJECT, "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json"))
            disposition = "deadline_release_maintenance"
        raise
    finally:
        stop.set()
        thread.join(2)
        atomic(P / "OWNER_TERMINAL.json", {"at_utc": now().isoformat(), "disposition": disposition, "conservative_provider_spend_usd": prior + (time.monotonic() - started) / 3600 * RATE, "artifact_root": str(artifact)})


if __name__ == "__main__":
    main()
