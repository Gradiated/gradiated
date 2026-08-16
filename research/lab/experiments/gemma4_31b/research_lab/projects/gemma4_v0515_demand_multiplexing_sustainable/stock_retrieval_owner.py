#!/usr/bin/env python3
"""Bounded, retrieval-only recovery for the already-launched stock run."""
import datetime as dt
import json
import pathlib
import subprocess
import sys
import time

P = pathlib.Path(__file__).resolve().parent
LAB = P.parents[1]
FACTORY = "/root/workspace/research/factory/src"
BENCH = "h200-ngram-verifier-e00kcm9nfhwt7e7gbc"
HOST = "89.169.99.101"
KEY = "/root/.config/nebius/glm-campaign/ssh_ed25519"
KNOWN = "/root/.config/nebius/glm-campaign/known_hosts"
REMOTE = "/home/glmrunner/gemma4-stock-multiplex"
DEADLINE = dt.datetime(2026, 7, 25, 9, 25, tzinfo=dt.timezone.utc)
RATE = 2.46
START = time.time()
ROOT = P / "artifacts" / "stock-multiplex-packet-id-repair-20260725t084123z"
OUT = ROOT / "retrieval-repair"


def atomic(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


def run(cmd, timeout):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ssh(command, timeout=45):
    return run([
        "ssh", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=2",
        "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}",
        f"glmrunner@{HOST}", command,
    ], timeout)


def heartbeat():
    return run([
        "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB),
        "heartbeat", "--project", "gemma4_v0515_demand_multiplexing_sustainable",
    ], 45)


def snapshot(tag):
    command = (
        f"cd {REMOTE}; "
        "echo '--- INVOCATION_STATE ---'; cat out/INVOCATION_STATE.json 2>&1 || true; "
        "echo '--- FINAL_PRESENT ---'; test -f out/FINAL_TERMINAL.json && echo yes || echo no; "
        "echo '--- WORKER_PID ---'; cat WORKER.pid 2>&1 || true; "
        "echo '--- WORKER_PROCESS ---'; test -f WORKER.pid && ps -p $(cat WORKER.pid) -o pid=,stat=,etime=,cmd= 2>&1 || true; "
        "echo '--- WORKER_LOG_TAIL ---'; tail -n 160 WORKER.log 2>&1 || true; "
        "echo '--- CONTAINERS ---'; docker ps -a --no-trunc 2>&1 || true"
    )
    try:
        result = ssh(command)
        (OUT / f"remote-{tag}.log").write_text(result.stdout + result.stderr)
        return result.returncode, result.stdout
    except Exception as exc:
        (OUT / f"remote-{tag}.log").write_text(repr(exc) + "\n")
        return None, ""


def retrieve():
    destination = OUT / "retrieved"
    result = run([
        "scp", "-r", "-p", "-i", KEY, "-o", "BatchMode=yes", "-o", "ConnectTimeout=15",
        "-o", "StrictHostKeyChecking=accept-new", "-o", f"UserKnownHostsFile={KNOWN}",
        f"glmrunner@{HOST}:{REMOTE}/out", str(destination),
    ], 180)
    (OUT / "retrieve.log").write_text(result.stdout + result.stderr)
    return result.returncode == 0


def finalize(result, consumed, classification):
    status = json.loads((P / "STATUS.json").read_text())
    # The original owner began at 08:41:23Z; charge all retained H200 time
    # since then at the metered rate, on top of prior attributed spend.
    began = dt.datetime(2026, 7, 25, 8, 41, 23, tzinfo=dt.timezone.utc).timestamp()
    spend = 1.49 + max(0.0, time.time() - began) / 3600 * RATE
    terminal = {
        "result": result,
        "classification": classification,
        "candidate_sample_consumed": consumed,
        "artifact_root": str(ROOT.relative_to(P)),
        "retrieval_artifacts": str(OUT.relative_to(P)),
    }
    status.update({"status": "complete", "active_session": None,
                   "actual_spend_usd": round(spend, 6), "terminal": terminal,
                   "candidate_sample_consumed": consumed})
    atomic(P / "STATUS.json", status)
    contents = {
        "project": "gemma4_v0515_demand_multiplexing_sustainable",
        "result": result, "candidate_sample_consumed": consumed,
        "artifacts": str(ROOT.relative_to(P)),
        "server_state": "Remote stock invocation was retrieval-repaired; inspect preserved remote logs before any reuse.",
    }
    atomic(P / "BENCH_CONTENTS.json", contents)
    run([
        "python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB), "release",
        "--project", "gemma4_v0515_demand_multiplexing_sustainable",
        "--condition", "maintenance", "--contents", str(P / "BENCH_CONTENTS.json"),
    ], 60)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    status = json.loads((P / "STATUS.json").read_text())
    status["active_session"] = {
        "unit": str(P / "OWNER_STATE_STOCK_RETRIEVAL_REPAIR.json"),
        "unit_manager": "pid", "deadline_utc": "2026-07-25T09:25:00Z",
        "artifact_root": str(ROOT), "bench_id": BENCH,
        "expected_terminal": "out/FINAL_TERMINAL.json",
    }
    atomic(P / "STATUS.json", status)
    while dt.datetime.now(dt.timezone.utc) < DEADLINE:
        heartbeat()
        tag = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dt%H%M%Sz")
        _, text = snapshot(tag)
        if "--- FINAL_PRESENT ---\nyes" in text:
            if retrieve():
                final = OUT / "retrieved" / "out" / "FINAL_TERMINAL.json"
                if final.exists():
                    payload = json.loads(final.read_text())
                    finalize(payload.get("result", "retrieved_scientific_terminal"),
                             payload.get("candidate_sample_consumed"), "retrieved_terminal")
                    return
            # A terminal exists but retrieval itself failed; retain the claim for retry.
        time.sleep(45)
    snapshot("deadline")
    finalize("typed_remote_unreachable_or_incomplete_retrieval", None,
             "external_retrieval_boundary")


if __name__ == "__main__":
    main()
