#!/usr/bin/env python3
"""Replacement owner for the director-authorized same-claim R2 transition."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parents[1]
PROJECT = "gemma4_h200_current_norm_fp8_hotblock"
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
COMPONENT = "dfa05dcf1f3f9ad6dd40f5318cf6c2c6d55eb93beebf0239f205e7fa88b85829"


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class R2:
    def __init__(self, transition: dict, state_path: pathlib.Path):
        self.transition = transition
        self.claim = transition["claim"]
        self.predecessor = transition["predecessor_owner"]
        self.root = HERE / transition["mutable_implementation"]["replacement_artifact_root"]
        self.root.mkdir(parents=True, exist_ok=True)
        self.state_path = state_path
        self.remote_root = transition["resident_state"]["remote_root"]
        self.bench_id = self.claim["bench_id"]
        self.claimed_at = self.claim["claimed_at"]
        self.deadline = dt.datetime.fromisoformat(self.claim["effective_claim_deadline_utc"].replace("Z", "+00:00")).timestamp()
        self.takeover = self.root / "TAKEOVER.json"
        self.stop = threading.Event()
        self.heartbeat_error = ""

    def left(self, reserve: int = 0) -> int:
        return max(1, int(self.deadline - time.time() - reserve))

    def run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, text=True, capture_output=True, timeout=min(timeout, self.left()))

    def event(self, event: str, **fields: object) -> None:
        row = {"at_utc": utc(), "event": event, "claim_generation": self.claimed_at, **fields}
        with (self.root / "R2_EVENTS.jsonl").open("a") as out:
            out.write(json.dumps(row, sort_keys=True) + "\n")
        atomic(self.root / "R2_PROGRESS.json", row)

    def pool(self) -> dict:
        result = self.run([*POOL, "show", "--bench", self.bench_id], 30)
        if result.returncode:
            raise RuntimeError("pool_show:" + result.stderr[-300:])
        return json.loads(result.stdout)

    def validate_claim(self) -> dict:
        bench = self.pool()
        claim = bench.get("claim") or {}
        if bench.get("status") != "claimed" or claim.get("project") != PROJECT or claim.get("claimed_at") != self.claimed_at:
            raise RuntimeError("claim_identity_changed")
        return bench

    def ssh(self, bench: dict, script: str, timeout: int = 90) -> subprocess.CompletedProcess[str]:
        resource = bench["resource"]
        return self.run([
            "ssh", "-i", resource["ssh_identity_path"], "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
            f"{resource['ssh_user']}@{resource['public_ipv4']}", script,
        ], timeout)

    def heartbeat(self) -> None:
        while not self.stop.wait(20):
            result = self.run([*POOL, "heartbeat", "--project", PROJECT, "--bench", self.bench_id], 30)
            if result.returncode:
                self.heartbeat_error = result.stderr[-300:]
                self.event("heartbeat_failure", diagnostic=self.heartbeat_error)
                return

    def standby(self) -> dict:
        bench = self.validate_claim()
        remote = self.ssh(bench, " && ".join([
            f"test -d {self.remote_root}",
            f"test \"$(sha256sum {self.remote_root}/inputs/gemma4-layer0-norm-qkv-component.safetensors | cut -d' ' -f1)\" = {COMPONENT}",
            f"sudo -n docker image inspect {IMAGE} >/dev/null",
            "! sudo -n docker ps --format '{{.Names}} {{.Image}}' | grep -q norm-fp8-exact-order",
        ]))
        if remote.returncode:
            raise RuntimeError("resident_state_invalid:" + remote.stderr[-500:])
        ready = {
            "at_utc": utc(), "classification": "r2_standby_ready", "claim_generation": self.claimed_at,
            "bench_id": self.bench_id, "predecessor_pid": self.predecessor["pid"],
            "predecessor_start_ticks": self.predecessor["start_ticks"], "remote_root": self.remote_root,
            "component_sha256": COMPONENT, "runtime_image": IMAGE, "state_path": str(self.state_path),
        }
        atomic(self.root / "R2_STANDBY_READY.json", ready)
        self.event("standby_ready", remote_root=self.remote_root)
        return bench

    def wait_takeover(self) -> None:
        while time.time() < self.deadline - 180:
            if self.takeover.exists():
                payload = json.loads(self.takeover.read_text())
                if payload.get("claim_generation") == self.claimed_at and payload.get("predecessor_pid") == self.predecessor["pid"]:
                    return
                raise RuntimeError("takeover_identity_mismatch")
            if self.heartbeat_error:
                raise RuntimeError("heartbeat_lost")
            time.sleep(1)
        raise RuntimeError("takeover_deadline")

    def update_status(self) -> None:
        status_path = HERE / "STATUS.json"
        status = json.loads(status_path.read_text())
        record = json.loads(self.state_path.read_text())
        status["active_session"] = {
            "artifact_root": str(self.root), "deadline_utc": self.claim["effective_claim_deadline_utc"],
            "expected_terminal": "TERMINAL.json", "forward_progress": "r2_scientific_runner_started",
            "pid": record["pid"], "start_ticks": record["start_ticks"], "unit": str(self.state_path), "unit_manager": "pid",
        }
        status["same_claim_transition"]["r2_takeover_at_utc"] = utc()
        atomic(status_path, status)

    def run_science(self, bench: dict) -> dict:
        remote_check = self.ssh(bench, "! pgrep -af '[h]200_runner.py|[d]ocker run.*norm-fp8'", 30)
        if remote_check.returncode:
            raise RuntimeError("competing_remote_executor")
        atomic(self.root / "R2_OWNER_READY.json", {
            "at_utc": utc(), "classification": "r2_takeover_complete", "claim_generation": self.claimed_at,
            "bench_id": self.bench_id, "remote_root": self.remote_root, "retry_scope": "scientific_runner_then_terminal_retrieval",
        })
        self.update_status()
        self.event("takeover_complete")
        command = (
            f"cd {self.remote_root} && if test -e out-r2; then mv out-r2 out-r2.partial-$(date -u +%Y%m%dT%H%M%SZ); fi && "
            f"sudo -n docker run --rm --user $(id -u):$(id -g) --gpus 'device={bench['contents']['gpu_uuid']}' "
            f"-v {self.remote_root}:/work -w /work {IMAGE} bash -lc "
            "'python3 h200_runner.py --component-safetensors inputs/gemma4-layer0-norm-qkv-component.safetensors --output out-r2 --repetitions 100' "
            "> worker-r2.stdout 2> worker-r2.stderr"
        )
        self.event("scientific_runner_launch", output="out-r2")
        worker = self.ssh(bench, command, self.left(180))
        atomic(self.root / "WORKER_R2_RESULT.json", {
            "at_utc": utc(), "returncode": worker.returncode, "stdout": worker.stdout[-2000:], "stderr": worker.stderr[-2000:],
        })
        self.event("scientific_runner_returned", returncode=worker.returncode)
        resource = bench["resource"]
        terminal_local = self.root / "remote-output" / "TERMINAL.json"
        terminal_local.parent.mkdir(parents=True, exist_ok=True)
        retrieved = self.run([
            "scp", "-i", resource["ssh_identity_path"], "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
            f"{resource['ssh_user']}@{resource['public_ipv4']}:{self.remote_root}/out-r2/TERMINAL.json", str(terminal_local),
        ], self.left(120))
        if retrieved.returncode:
            raise RuntimeError("terminal_retrieval:" + retrieved.stderr[-500:])
        terminal = json.loads(terminal_local.read_text())
        if terminal.get("classification") not in {"component_positive", "component_negative"} or not terminal.get("ledger_complete"):
            raise RuntimeError("incomplete_terminal")
        atomic(self.root / "TERMINAL.json", terminal)
        return terminal

    def release(self, condition: str, reason: str) -> None:
        contents = self.root / "RELEASE_CONTENTS.json"
        atomic(contents, {"project": PROJECT, "claim_generation": self.claimed_at, "release_reason": reason, "r2": True})
        result = self.run([*POOL, "release", "--project", PROJECT, "--bench", self.bench_id,
                           "--expected-claimed-at", self.claimed_at, "--condition", condition, "--contents", str(contents)], 45)
        self.event("release", condition=condition, returncode=result.returncode, reason=reason)

    def execute(self) -> int:
        thread = threading.Thread(target=self.heartbeat, daemon=True); thread.start()
        try:
            self.standby()
            self.wait_takeover()
            bench = self.validate_claim()
            terminal = self.run_science(bench)
            self.release("ready", terminal["classification"])
            return 0
        except Exception as error:
            self.event("r2_failure", diagnostic=str(error))
            if time.time() >= self.deadline - 90 or self.heartbeat_error:
                self.release("maintenance", "r2_failure_or_deadline")
            return 2
        finally:
            self.stop.set(); thread.join(2)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transition", type=pathlib.Path, required=True)
    parser.add_argument("--state-path", type=pathlib.Path, required=True)
    args = parser.parse_args()
    return R2(json.loads(args.transition.read_text()), args.state_path).execute()


if __name__ == "__main__":
    raise SystemExit(main())
