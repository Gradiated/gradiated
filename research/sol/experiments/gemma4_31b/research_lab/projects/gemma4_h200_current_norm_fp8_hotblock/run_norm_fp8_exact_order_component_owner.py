#!/usr/bin/env python3
"""Durable, generation-fenced owner for the exact-order component run."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import threading
import time

HERE = pathlib.Path(__file__).resolve().parent
LAB = HERE.parents[1]
PROJECT = "gemma4_h200_current_norm_fp8_hotblock"
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
REPAIR = "/root/workspace/research/factory/tools/repair-handshake"
IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
INPUTS = {
    "MECHANISM_REPAIR_TERMINAL.json": "b1d8254ee3cc78eb3e09e28064baa1ac666746c789f9f74d01fc65d5a82fc199",
    "inputs/gemma4-layer0-norm-qkv-component.safetensors": "dfa05dcf1f3f9ad6dd40f5318cf6c2c6d55eb93beebf0239f205e7fa88b85829",
    "h200_runner.py": "99656cd8d13139421a7fe8c7ab878f3efb00d8cb5904614af07222f591823b80",
    "norm_fp8_decode_exact_order.cu": "fba1452c2cf460a92d229f9944b8fc14f77b10ce7490269e6c9307feb772c792",
    "norm_fp8_decode_exact_order.py": "f18dfe570ee7bc2d7863d8982205f028d4f617ce9784be7f943a14a363f3956d",
    "runtime_adapter.py": "adbd48db4599b05920026fdd070b893ee885ae08d63e5b6235cee0cd8d379471",
}


def atomic(path: pathlib.Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    json.loads(part.read_text())
    os.replace(part, path)


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


class Recoverable(Exception):
    def __init__(self, phase: str, detail: str):
        self.phase, self.detail = phase, detail
        super().__init__(f"{phase}:{detail}")


class Owner:
    """One owner, one claim, and an explicit repair-generation loop."""

    def __init__(self, binding: dict, root: pathlib.Path, ready_file: pathlib.Path):
        self.binding, self.root, self.ready_file = binding, root, ready_file
        self.bench, self.claimed_at = binding["bench"], binding["claimed_at"]
        claimed = dt.datetime.fromisoformat(self.claimed_at.replace("Z", "+00:00")).timestamp()
        release = dt.datetime.fromisoformat(binding["absolute_release_deadline_utc"].replace("Z", "+00:00")).timestamp()
        self.deadline = min(release, claimed + binding["maximum_claim_seconds"])
        resource = self.bench["resource"]
        self.host, self.user = resource["public_ipv4"], resource["ssh_user"]
        self.key, self.known_hosts = resource["ssh_identity_path"], resource["known_hosts_namespace"]
        self.remote_root = "/home/glmrunner/norm-fp8-exact-order-20260730t0730z"
        self.stop, self.heartbeat_error = threading.Event(), None
        self.generation, self.phase, self.releases = 0, "owner_adoption", []

    def event(self, name: str, **fields: object) -> None:
        row = {"at_utc": utc(), "event": name, "generation": self.generation, "phase": self.phase, **fields}
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / "OWNER_EVENTS.jsonl").open("a") as out:
            out.write(json.dumps(row, sort_keys=True) + "\n")
        atomic(self.root / "OWNER_PROGRESS.json", row)

    def left(self, reserve: int = 0) -> int:
        return max(1, int(self.deadline - time.time() - reserve))

    def run(self, args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
        return subprocess.run(args, text=True, capture_output=True, timeout=min(timeout, self.left()))

    def ssh(self, script: str, timeout: int = 300) -> subprocess.CompletedProcess[str]:
        return self.run(["ssh", "-i", self.key, "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}", f"{self.user}@{self.host}", script], timeout)

    def heartbeat_loop(self) -> None:
        while not self.stop.wait(30):
            result = self.run([*POOL, "heartbeat", "--project", PROJECT, "--bench", self.bench["id"]], 30)
            if result.returncode:
                self.heartbeat_error = result.stderr[-500:]
                self.event("heartbeat_failure", diagnostic=self.heartbeat_error)
                return

    def adopt(self) -> None:
        self.phase = "owner_adopted"
        self.event("claim_generation_validated", bench=self.bench["id"], claimed_at=self.claimed_at)
        atomic(self.ready_file, {"at_utc": utc(), "claim_generation": self.claimed_at, "generation": 0,
                                 "phase": "owner_adopted_heartbeat_started", "remote_root": self.remote_root})
        self.event("owner_adopted", ready_file=str(self.ready_file))

    def stage(self) -> None:
        self.phase = "immutable_staging"
        result = self.ssh(f"mkdir -p {shlex.quote(self.remote_root)}/inputs", 60)
        if result.returncode: raise Recoverable(self.phase, result.stderr[-600:])
        for relative, digest in INPUTS.items():
            local = HERE / relative
            if hashlib.sha256(local.read_bytes()).hexdigest() != digest: raise Recoverable(self.phase, f"local_digest:{relative}")
            target = f"{self.remote_root}/{relative}"
            check = self.ssh(f"test -f {shlex.quote(target)} && test $(sha256sum {shlex.quote(target)} | cut -d' ' -f1) = {digest}", 300)
            if check.returncode:
                part = target + f".part.{os.getpid()}"
                copy = self.run(["scp", "-i", self.key, "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}", str(local), f"{self.user}@{self.host}:{part}"], max(300, int(local.stat().st_size / 10_000_000) + 120))
                if copy.returncode: raise Recoverable(self.phase, f"copy:{relative}:{copy.stderr[-300:]}")
                finish = self.ssh(f"test $(sha256sum {shlex.quote(part)} | cut -d' ' -f1) = {digest} && chmod 0444 {shlex.quote(part)} && mv {shlex.quote(part)} {shlex.quote(target)}", 600)
                if finish.returncode: raise Recoverable(self.phase, f"finalize:{relative}:{finish.stderr[-300:]}")
            self.event("input_verified", input=relative, sha256=digest)

    def run_science(self) -> None:
        self.phase = "image_pull"
        pull = self.ssh(f"sudo -n docker pull {IMAGE}", self.left(900))
        if pull.returncode: raise Recoverable(self.phase, pull.stderr[-600:])
        self.phase = "scientific_runner"
        gpu = self.bench["contents"]["gpu_uuid"]
        command = f"cd {shlex.quote(self.remote_root)} && sudo -n docker run --rm --user $(id -u):$(id -g) --gpus 'device={gpu}' -v {shlex.quote(self.remote_root)}:/work -w /work {IMAGE} bash -lc 'python3 h200_runner.py --component-safetensors inputs/gemma4-layer0-norm-qkv-component.safetensors --output out --repetitions 100 > ../worker.stdout 2> ../worker.stderr'"
        self.event("science_started", command="bound_h200_runner_repetitions_100")
        worker = self.ssh(command, self.left(600))
        self.event("scientific_runner_returned", returncode=worker.returncode, stderr=worker.stderr[-600:])

    def retrieve(self) -> dict:
        self.phase = "terminal_retrieval"
        local = self.root / "remote-output"; local.mkdir(parents=True, exist_ok=True)
        result = self.run(["scp", "-i", self.key, "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={self.known_hosts}", f"{self.user}@{self.host}:{self.remote_root}/out/TERMINAL.json", str(local / "TERMINAL.json")], 300)
        if result.returncode: raise Recoverable(self.phase, result.stderr[-600:])
        terminal = json.loads((local / "TERMINAL.json").read_text())
        if terminal.get("classification") not in {"component_positive", "component_negative"} or not terminal.get("ledger_complete"):
            raise Recoverable(self.phase, "incomplete_component_terminal")
        atomic(self.root / "TERMINAL.json", terminal)
        return terminal

    def release(self, condition: str, reason: str) -> None:
        if self.releases: return
        contents = self.root / "RELEASE_CONTENTS.json"
        atomic(contents, {"project": PROJECT, "release_reason": reason, "claim_generation": self.claimed_at, "generation": self.generation})
        result = self.run([*POOL, "release", "--project", PROJECT, "--bench", self.bench["id"], "--expected-claimed-at", self.claimed_at, "--condition", condition, "--contents", str(contents)], 60)
        self.releases.append({"condition": condition, "returncode": result.returncode})
        self.event("bench_release", condition=condition, returncode=result.returncode, reason=reason)

    def await_repair(self, error: Recoverable) -> bool:
        repair_id = f"norm-fp8-exact-order-{self.generation}"
        deadline = dt.datetime.fromtimestamp(max(time.time(), self.deadline - 90), dt.timezone.utc).isoformat().replace("+00:00", "Z")
        self.event("repair_ready", diagnostic=error.detail, repair_id=repair_id, retry_scope=error.phase)
        ready = self.run([REPAIR, "ready", "--root", str(self.root), "--repair-id", repair_id, "--deadline", deadline, "--failure-kind", "recoverable_owner_phase", "--diagnostic", error.detail, "--retry-scope", error.phase], self.left())
        if ready.returncode: return False
        waited = self.run([REPAIR, "wait", "--root", str(self.root), "--repair-id", repair_id, "--deadline", deadline], self.left())
        if waited.returncode != 0: return False
        state = json.loads(waited.stdout).get("state")
        if state != "requested": return False
        request = self.root / ".repair-handshakes" / repair_id / "REPAIR_REQUEST.json"
        consumed = request.with_name(f"REPAIR_REQUEST.{hashlib.sha256(request.read_bytes()).hexdigest()}.consumed.json")
        os.replace(request, consumed)
        self.generation += 1
        self.event("repair_request_consumed", request=str(consumed), retry_phase=error.phase)
        return True

    def execute(self) -> int:
        thread = threading.Thread(target=self.heartbeat_loop, daemon=True); thread.start()
        try:
            self.adopt()
            phase = "immutable_staging"
            while True:
                try:
                    if phase == "immutable_staging": self.stage(); phase = "image_pull"
                    if phase in {"image_pull", "scientific_runner"}: self.run_science(); phase = "terminal_retrieval"
                    terminal = self.retrieve()
                    self.release("ready", terminal["classification"])
                    return 0
                except Recoverable as error:
                    phase = error.phase
                    if self.heartbeat_error or not self.await_repair(error):
                        self.release("maintenance", "heartbeat_loss_or_repair_deadline")
                        return 2
        finally:
            self.stop.set(); thread.join(3)


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--binding", type=pathlib.Path, required=True); parser.add_argument("--ready-file", type=pathlib.Path, required=True); args = parser.parse_args()
    binding = json.loads(args.binding.read_text())
    owner = Owner(binding, pathlib.Path(binding["artifact_root"]), args.ready_file)
    if not pathlib.Path(owner.key).is_file(): raise RuntimeError("claimed_ssh_identity_missing")
    return owner.execute()


if __name__ == "__main__":
    raise SystemExit(main())
