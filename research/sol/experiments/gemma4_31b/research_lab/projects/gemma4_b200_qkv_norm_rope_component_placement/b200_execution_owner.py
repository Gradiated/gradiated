#!/usr/bin/env python3
"""Bound controller-host lifecycle for the one B200 QKV component ledger."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import subprocess
import tempfile
import threading
import time
from typing import Any
from grad_research.gpu_pool import GpuPool

PROJECT = "gemma4_b200_qkv_norm_rope_component_placement"
BENCH = "b200-qkv-placement-computeinstance-i00gfqs16jywacph24"
LAB = pathlib.Path("/root/workspace/research/sol/experiments/gemma4_31b/research_lab")
ROOT = pathlib.Path(__file__).resolve().parent
RELEASE_FENCE = "2026-07-29T18:57:00Z"
BINDING_SHA256 = "0bd04a21698b41784b598c0349a7e3056a539219d17fd16060e20e01e1dd7e49"

def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)

def iso() -> str:
    return utcnow().isoformat().replace("+00:00", "Z")

def when(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))

def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)

def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

class Owner:
    def __init__(self, binding_path: pathlib.Path) -> None:
        self.binding_path = binding_path.resolve()
        self.binding = json.loads(self.binding_path.read_text())
        self.root = ROOT / "artifacts" / "b200-qkv-component-repair-20260729t1822z"
        self.root.mkdir(parents=True, exist_ok=True)
        self.progress = self.root / "OWNER_PROGRESS.json"
        self.runtime_state = self.root / "OWNER_RUNTIME_STATE.json"
        self.phase_times: dict[str, str] = {"owner_started_at_utc": iso()}
        self.pool = GpuPool(LAB)
        self.claimed_at: str | None = None
        self.stop = threading.Event()
        self.heartbeat_error: str | None = None
        self.thread: threading.Thread | None = None
        self.science_started = False
        self.release_fence = when(self.binding["lifecycle"]["generation_fenced_release_by_utc"])
        self.remote_root = "/home/glmrunner/gemma4-b200-qkv-component-repair-20260729t1822z"
        self.remote_output_parent = f"{self.remote_root}/output-parent-repair-20260729t1822z"
        self.remote_output = f"{self.remote_output_parent}/run"

    def remaining(self, cap: int) -> int:
        value = int((self.release_fence - utcnow()).total_seconds())
        if value <= 0:
            raise TimeoutError("generation-fenced release deadline reached")
        return min(cap, value)

    def record(self, phase: str, **extra: Any) -> None:
        self.phase_times[phase] = iso()
        state = {
            "schema_version": 1, "phase": phase, "phase_times": self.phase_times,
            "claimed_at": self.claimed_at, "science_started": self.science_started,
            "heartbeat_error": self.heartbeat_error, **extra,
        }
        atomic_json(self.progress, state)
        atomic_json(self.runtime_state, state)

    def command(self, args: list[str], *, name: str, cap: int, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(args, input=input_text, text=True, capture_output=True,
                                timeout=self.remaining(cap), check=False)
        (self.root / f"{name}.stdout").write_text(result.stdout)
        (self.root / f"{name}.stderr").write_text(result.stderr)
        return result

    def require(self, args: list[str], *, name: str, cap: int, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
        result = self.command(args, name=name, cap=cap, input_text=input_text)
        if result.returncode:
            raise RuntimeError(f"{name} failed ({result.returncode}): {result.stderr[-1600:]}")
        return result

    def validate(self) -> None:
        files = {
            "inputs/bound/qkv_direct_consumer_bench.py": "10d2538ce6d35a4fbedf4b8db946d8e93d7004690fa1a0c6f0cae3c6427e63ff",
            "inputs/bound/H200_RESULT.json": "ad4192d8cb86c56791f2470e5b4bd0586a4e445d033e03cda76326677a938caf",
            "inputs/bound/H200_SCIENTIFIC_TERMINAL.json": "6aa40802441a36184129bcef9486180acf0b5eba432b68715085d9f7c58d55a2",
        }
        if digest(self.binding_path) != BINDING_SHA256:
            raise RuntimeError("binding digest mismatch")
        if self.binding["project"] != PROJECT or self.binding["bench"]["id"] != BENCH:
            raise RuntimeError("binding scope mismatch")
        for relative, expected in files.items():
            if digest(ROOT / relative) != expected:
                raise RuntimeError(f"immutable digest mismatch: {relative}")
        status = json.loads((ROOT / "STATUS.json").read_text())
        if status["authorized_spend_usd"] != 5.0 or status["actual_spend_usd"] != 0.0:
            raise RuntimeError("exact $5 reservation / prior spend mismatch")
        if utcnow() > when(self.binding["lifecycle"]["claim_start_by_utc"]):
            raise RuntimeError("claim-start fence passed")
        self.record("binding_validated")

    def heartbeat(self) -> None:
        while not self.stop.wait(45):
            try:
                row = self.pool.heartbeat(PROJECT, bench_id=BENCH)
                claim = row.get("claim") or {}
                if claim.get("claimed_at") != self.claimed_at:
                    raise RuntimeError("claim generation changed")
            except Exception as error:
                self.heartbeat_error = repr(error)
                self.stop.set()
                self.record("heartbeat_failed")
                return

    def claim(self) -> dict[str, Any]:
        row = self.pool.claim(PROJECT, bench_id=BENCH, lease_seconds=2200)
        claim = row.get("claim") or {}
        if claim.get("project") != PROJECT or not claim.get("claimed_at"):
            raise RuntimeError("invalid claim response")
        self.claimed_at = str(claim["claimed_at"])
        self.thread = threading.Thread(target=self.heartbeat, daemon=True)
        self.thread.start()
        self.record("bench_claimed", bench_status=row.get("status"))
        return row

    def ssh(self, row: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
        resource = row["resource"]
        key = pathlib.Path(resource["ssh_identity_path"])
        known = pathlib.Path(resource["known_hosts_namespace"])
        if not key.is_file() or not known.is_file():
            raise RuntimeError("strict SSH identity or known-hosts namespace missing")
        if resource["ssh_ed25519_fingerprint"] != self.binding["bench"]["ssh_ed25519_fingerprint"]:
            raise RuntimeError("strict SSH fingerprint mismatch")
        self.record("strict_ssh_verified", fingerprint=resource["ssh_ed25519_fingerprint"])
        return (["ssh", "-i", str(key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
                 "-o", f"UserKnownHostsFile={known}", "-o", "ConnectTimeout=20",
                 f"{resource['ssh_user']}@{resource['public_ipv4']}"], resource)

    def remote(self, ssh: list[str], script: str, name: str, cap: int) -> subprocess.CompletedProcess[str]:
        return self.command(ssh + ["bash", "-s"], name=name, cap=cap, input_text=script)

    def execute(self, row: dict[str, Any]) -> None:
        ssh, resource = self.ssh(row)
        image = self.binding["immutable_science"]["image"]
        image_digest = image.split("@", 1)[1]
        prepare = f"""set -euo pipefail
mkdir -p {self.remote_root} {self.remote_output_parent}
rm -rf {self.remote_output}
sudo -n docker pull {image}
sudo -n docker image inspect {image} --format '{{{{json .RepoDigests}}}}' | grep -F '{image_digest}'
"""
        prepared = self.remote(ssh, prepare, "prepare", 600)
        if prepared.returncode:
            raise RuntimeError(f"remote prepare failed: {prepared.stderr[-1600:]}")
        self.record("remote_prepared")
        scp = ["scp", "-i", str(resource["ssh_identity_path"]), "-o", "BatchMode=yes",
               "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={resource['known_hosts_namespace']}",
               str(ROOT / "inputs/bound/qkv_direct_consumer_bench.py"),
               f"{resource['ssh_user']}@{resource['public_ipv4']}:{self.remote_root}/qkv_direct_consumer_bench.py"]
        self.require(scp, name="stage", cap=120)
        remote_hash = self.require(ssh + ["sha256sum", f"{self.remote_root}/qkv_direct_consumer_bench.py"],
                                   name="remote_hash", cap=60).stdout.split()[0]
        if remote_hash != self.binding["immutable_science"]["runner"]["sha256"]:
            raise RuntimeError("remote runner hash mismatch")
        self.record("runner_staged", remote_runner_sha256=remote_hash)
        run = f"""set -euo pipefail
sudo -n docker run --rm --gpus all -e RUNTIME_IMAGE_IDENTITY='{image}' -e BOUND_GPU_UUID='{self.binding['bench']['gpu_uuid']}' -v '{self.remote_root}:/work:ro' -v '{self.remote_output_parent}:/output-parent' '{image}' python3 /work/qkv_direct_consumer_bench.py --output-dir /output-parent/run
"""
        self.record("pre_science_container_launch")
        worker = self.remote(ssh, run, "worker", 1800)
        marker = self.remote(ssh, f"test -f {self.remote_output}/SCIENTIFIC_STARTED && cat {self.remote_output}/SCIENTIFIC_STARTED || true",
                             "science_marker", 60)
        self.science_started = bool(marker.stdout.strip())
        self.record("worker_returned", worker_exit_code=worker.returncode)
        self.retrieve(ssh)
        if worker.returncode:
            raise RuntimeError(f"worker failed after marker={self.science_started}: {worker.stderr[-1600:]}")

    def retrieve(self, ssh: list[str]) -> None:
        self.record("retrieval_started")
        archive = self.root / "remote-output.tar.gz"
        with archive.open("wb") as stream:
            result = subprocess.run(ssh + ["tar", "-C", self.remote_output, "-czf", "-", "."],
                                    stdout=stream, stderr=subprocess.PIPE, timeout=self.remaining(300), check=False)
        (self.root / "retrieve.stderr").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError("remote artifact retrieval failed")
        snapshot = self.root / "retrieved"
        snapshot.mkdir(exist_ok=True)
        unpack = subprocess.run(["tar", "-xzf", str(archive), "-C", str(snapshot)],
                                capture_output=True, text=True, timeout=self.remaining(120), check=False)
        (self.root / "unpack.stderr").write_text(unpack.stderr)
        if unpack.returncode:
            raise RuntimeError("retrieved archive corrupt")
        for name in ("IDENTITY.json", "SCIENTIFIC_STARTED", "local_decode_c32.json",
                     "global_decode_c32.json", "RESULT.json", "TERMINAL.json"):
            if not (snapshot / name).is_file():
                raise RuntimeError(f"required artifact missing: {name}")
        self.record("retrieval_complete", archive_sha256=digest(archive))

    def construct_terminal(self) -> dict[str, Any]:
        snapshot = self.root / "retrieved"
        result = json.loads((snapshot / "RESULT.json").read_text())
        if not self.science_started or not result.get("science_consumed"):
            raise RuntimeError("scientific consumption evidence incomplete")
        h200 = json.loads((ROOT / "inputs/bound/H200_RESULT.json").read_text())
        hrows = {row["name"]: row for row in h200["rows"]}
        normalized = []
        for row in result["rows"]:
            candidate = row["timing"]["candidate"]["median_ms"] if row["timing"] else None
            hcandidate = hrows[row["name"]]["timing"]["candidate"]["median_ms"]
            normalized.append({
                "name": row["name"], "candidate_median_ms": candidate,
                "h200_candidate_median_ms": hcandidate,
                "latency_ratio_b200_over_h200": candidate / hcandidate if candidate else None,
                "actual_rate_normalized_cost_ratio_b200_over_h200": candidate * 3.95 / (hcandidate * 2.45) if candidate else None,
                "correctness_pass": row["correctness"]["pass"], "path_proof": row.get("path_proof"),
            })
        complete = bool(result.get("all_correct") and result.get("all_timed") and len(normalized) == 2)
        positive = complete and all(row["actual_rate_normalized_cost_ratio_b200_over_h200"] < 1 for row in normalized)
        provider_seconds = max(0.0, (utcnow() - when(self.binding["spend"]["provider_started_at_utc"])).total_seconds())
        spend = provider_seconds * 3.95 / 3600
        if spend > 5.0:
            raise RuntimeError(f"cumulative provider exposure exceeds $5: {spend}")
        timing = {
            "provider_started_at_utc": self.binding["spend"]["provider_started_at_utc"],
            "terminal_observed_at_utc": iso(), "provider_exposure_seconds_through_terminal": provider_seconds,
            "hourly_cost_usd": 3.95, "actual_spend_usd_through_terminal": spend, "phase_times": self.phase_times,
        }
        atomic_json(snapshot / "provider_and_phase_timing.json", timing)
        terminal = {
            "schema_version": 1, "binding_sha256": digest(self.binding_path),
            "classification": "placement_positive" if positive else "placement_negative" if complete else "numerical_or_structural_invalid",
            "science_consumed": True, "endpoint_submissions": 0, "profiler_enabled": False,
            "complete_evidence": complete, "actual_rate_normalized": normalized,
            "actual_spend_usd": spend, "useful_gpu_seconds": result.get("useful_gpu_seconds"),
            "result_sha256": digest(snapshot / "RESULT.json"),
            "provider_and_phase_timing_sha256": digest(snapshot / "provider_and_phase_timing.json"),
        }
        atomic_json(self.root / "B200_PLACEMENT_TERMINAL.json", terminal)
        return terminal

    def release(self, condition: str, contents: dict[str, Any]) -> None:
        if self.claimed_at is None:
            return
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=5)
        self.pool.release(PROJECT, bench_id=BENCH, expected_claimed_at=self.claimed_at,
                          condition=condition, contents=contents)
        self.record("bench_released", condition=condition)

    def update_status(self, terminal: dict[str, Any]) -> None:
        path = ROOT / "STATUS.json"
        status = json.loads(path.read_text())
        status.update({
            "status": "complete", "actual_spend_usd": terminal["actual_spend_usd"],
            "science_consumed": True, "active_session": None, "decision": terminal["classification"],
            "terminal": str(self.root / "B200_PLACEMENT_TERMINAL.json"),
            "summary": "One B200 exact-consumer local/global ledger completed and was actual-rate normalized against H200.",
        })
        atomic_json(path, status)

    def hold_repair(self, error: Exception) -> None:
        self.record("recoverable_pre_science_failure", error=repr(error))
        helper = ROOT.parents[5] / "factory/tools/repair-handshake"
        subprocess.run([str(helper), "hold", "--root", str(self.root), "--repair-id", "b200-qkv-component-20260729t1802z-r1",
                        "--deadline", RELEASE_FENCE, "--failure-kind", "integration", "--diagnostic", str(self.progress),
                        "--retry-scope", "pre_science"],
                       timeout=max(1, int((self.release_fence - utcnow()).total_seconds())), check=False)

    def run(self) -> int:
        try:
            self.validate()
            row = self.claim()
            self.execute(row)
            terminal = self.construct_terminal()
            self.record("scientific_terminal_complete", classification=terminal["classification"])
            self.update_status(terminal)
            self.release("ready", {
                "state": "B200 component ledger complete; no resident server or checkpoint.",
                "scientific_terminal": str(self.root / "B200_PLACEMENT_TERMINAL.json"),
                "caches": "Pinned image may remain cached; no server or CUDA science remains resident.",
            })
            return 0
        except Exception as error:
            if self.claimed_at and not self.science_started and utcnow() < self.release_fence:
                self.hold_repair(error)
            else:
                self.record("owner_failure", error=repr(error))
            if self.claimed_at:
                self.release("maintenance", {
                    "state": "B200 component owner needs director inspection.",
                    "diagnostic": str(self.progress), "science_started": self.science_started,
                })
            return 1

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binding", type=pathlib.Path, required=True)
    args = parser.parse_args()
    return Owner(args.binding).run()

if __name__ == "__main__":
    raise SystemExit(main())
