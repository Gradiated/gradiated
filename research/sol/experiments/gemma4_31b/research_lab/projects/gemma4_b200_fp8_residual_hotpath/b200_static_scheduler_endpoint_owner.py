#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import traceback


PROJECT = "gemma4_b200_fp8_residual_hotpath"
BENCH = "b200-m32-static-computeinstance-i00z1c1rm2yatraaed"
IMAGE = "docker.io/vllm/vllm-openai:gemma4@sha256:952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
VLLM = "6d4a8e6d204a9b2827544003b26321fff62923da"
CUTLASS = "v4.2.1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.name}.", delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def load(path: Path) -> dict:
    return json.loads(path.read_text())


class Owner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.project = args.project_root.resolve()
        self.out = args.output.resolve()
        self.binding = load(args.binding)
        self.manifest = load(args.runtime_manifest)
        self.preclaim = load(args.preclaim)
        self.deadline = dt.datetime.fromisoformat(self.binding["lifecycle"]["owner_deadline_utc"].replace("Z", "+00:00"))
        self.remote = self.binding["launch"]["remote_root"]
        self.claimed = False
        self.stop = threading.Event()
        self.ssh: list[str] = []
        self.ssh_stdin: list[str] = []
        self.scp: list[str] = []
        self.ssh_path = ""
        self.scp_path = ""
        self.tail_path = ""
        self.last_command: list[str] = []
        self.phase = "preclaim"
        self.repair_generation = 0

    def left(self, reserve: int = 0) -> float:
        return max(0.0, (self.deadline - dt.datetime.now(dt.UTC)).total_seconds() - reserve)

    def progress(self, phase: str, **extra: object) -> None:
        entry = {"at_utc": dt.datetime.now(dt.UTC).isoformat(), "phase": phase, **extra}
        with (self.out / "OWNER_PROGRESS.jsonl").open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        atomic_json(self.out / "OWNER_STATE.json", {"schema_version": 1, "state": "running", "phase": phase, "bench": BENCH, "claimed": self.claimed, "remote_root": self.remote, "deadline_utc": self.deadline.isoformat(), **extra})

    def run(self, command: list[str], *, check: bool = True, stdout: Path | None = None, stderr: Path | None = None, timeout: float | None = None) -> subprocess.CompletedProcess:
        self.last_command = command
        with (stdout.open("a") if stdout else open(os.devnull, "w")) as out, (stderr.open("a") if stderr else open(os.devnull, "w")) as err:
            result = subprocess.run(command, stdout=out, stderr=err, text=True, timeout=min(timeout or self.left(90), self.left(60)))
        if check and result.returncode:
            raise RuntimeError(f"command_failed:{command[0]}:{result.returncode}")
        return result

    def pool(self, *items: str, check: bool = True) -> subprocess.CompletedProcess:
        env = dict(os.environ, PYTHONPATH=str(self.args.repo_root / "research/factory/src"))
        return subprocess.run(["python3", "-m", "grad_research.gpu_pool", "--lab", str(self.args.lab), *items], capture_output=True, text=True, check=check, env=env)

    def validate(self) -> None:
        for attribute, executable in (("ssh_path", "ssh"), ("scp_path", "scp"), ("tail_path", "tail")):
            resolved = shutil.which(executable)
            if resolved is None or not Path(resolved).is_file():
                raise RuntimeError(f"controller_executable_missing:{executable}")
            setattr(self, attribute, str(Path(resolved).resolve()))
        required = self.binding["preclaim_preparation"]["required"]
        if not required or sha256(self.args.binding) != self.manifest["binding_sha256"]:
            raise RuntimeError("binding_manifest_mismatch")
        for key, filename in {"owner_sha256": "b200_static_scheduler_endpoint_owner.py", "runner_sha256": "b200_static_scheduler_endpoint_pair.py", "candidate_source_sha256": "m32_static_persistent_geometric_rebind_extension.cu"}.items():
            if self.manifest["hashes"][key] != sha256(self.project / filename):
                raise RuntimeError(f"runtime_hash_mismatch:{key}")
        if self.preclaim["runtime_manifest_sha256"] != sha256(self.args.runtime_manifest):
            raise RuntimeError("preclaim_manifest_mismatch")
        if dt.datetime.now(dt.UTC) > dt.datetime.fromisoformat(self.binding["lifecycle"]["claim_start_by_utc"].replace("Z", "+00:00")):
            raise RuntimeError("claim_fence_expired")

    def heartbeat(self) -> None:
        while not self.stop.wait(30):
            self.pool("heartbeat", "--project", PROJECT, "--bench", BENCH, check=False)

    def establish_ssh(self) -> None:
        row = json.loads(self.pool("show", "--bench", BENCH).stdout)
        resource = row["resource"]
        key, known = Path(resource["identity_file"]), Path(resource["known_hosts_namespace"])
        if not key.is_file() or not known.is_file():
            raise RuntimeError("ssh_identity_missing")
        options = ["-i", str(key), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known}"]
        target = f"{resource['ssh_user']}@{resource['public_ipv4']}"
        self.ssh = [self.ssh_path, "-n", *options, target]
        self.ssh_stdin = [self.ssh_path, *options, target]
        self.scp = [self.scp_path, *options]

    def claim(self) -> None:
        self.pool("claim", "--project", PROJECT, "--bench", BENCH)
        self.claimed = True
        threading.Thread(target=self.heartbeat, daemon=True).start()

    def stage(self) -> None:
        self.phase = "checkpoint_stage"
        self.progress("checkpoint_stage")
        checkpoint = self.project / "inputs/static-scheduler-endpoint-checkpoint"
        manifest_digest = self.binding["scientific_contract"]["checkpoint_manifest_sha256"]
        if sha256(checkpoint / "model-files.sha256") != manifest_digest:
            raise RuntimeError("checkpoint_manifest_mismatch")
        packet = self.remote + "/packet"
        logs = self.out / "stage.stdout"
        self.run([*self.ssh, f"set -Eeuo pipefail; mkdir -p {self.remote}/checkpoint {packet}; test -f /home/glmrunner/gemma4-b200-m32-geometric-rebind-20260728t2356z/vllm-src/IMMUTABLE.json"], stdout=logs, stderr=self.out / "stage.stderr")
        for line in (checkpoint / "model-files.sha256").read_text().splitlines():
            expected, name = line.split(maxsplit=1)
            source = checkpoint / name
            final = f"{self.remote}/checkpoint/{name}"
            part = final + ".part"
            size_command = [*self.ssh, f"test -f {shlex.quote(final)} && stat -c%s {shlex.quote(final)} || true"]
            self.last_command = size_command
            size = int(subprocess.run(size_command, capture_output=True, text=True).stdout.strip() or "0")
            if size == source.stat().st_size:
                self.run([*self.ssh, f"test \"$(sha256sum {shlex.quote(final)} | awk '{{print $1}}')\" = {shlex.quote(expected)}"], stdout=logs, stderr=self.out / "stage.stderr")
                continue
            resume_command = [*self.ssh, f"test -f {shlex.quote(part)} && stat -c%s {shlex.quote(part)} || echo 0"]
            self.last_command = resume_command
            resume = subprocess.run(resume_command, capture_output=True, text=True).stdout.strip()
            offset = int(resume or "0")
            if offset > source.stat().st_size:
                self.run([*self.ssh, f"rm -f {shlex.quote(part)}"], stdout=logs, stderr=self.out / "stage.stderr")
                offset = 0
            producer_command = [self.tail_path, "-c", f"+{offset + 1}", str(source)]
            self.last_command = producer_command
            producer = subprocess.Popen(producer_command, stdout=subprocess.PIPE)
            assert producer.stdout is not None
            consumer_command = [*self.ssh_stdin, f"cat >> {shlex.quote(part)}"]
            self.last_command = consumer_command
            consumer = subprocess.run(consumer_command, stdin=producer.stdout, timeout=self.left(240))
            producer.stdout.close()
            if producer.wait() or consumer.returncode:
                raise RuntimeError(f"checkpoint_transfer_failed:{name}")
            self.run([*self.ssh, f"set -Eeuo pipefail; test \"$(sha256sum {shlex.quote(part)} | awk '{{print $1}}')\" = {shlex.quote(expected)}; mv {shlex.quote(part)} {shlex.quote(final)}"], stdout=logs, stderr=self.out / "stage.stderr")
        manifest_target = f"{self.remote}/checkpoint/model-files.sha256"
        self.run([*self.scp, str(checkpoint / "model-files.sha256"), f"{self.ssh[-1]}:{manifest_target}.part"], stdout=logs, stderr=self.out / "stage.stderr")
        self.run([*self.ssh, f"set -Eeuo pipefail; test \"$(sha256sum {shlex.quote(manifest_target + '.part')} | awk '{{print $1}}')\" = {shlex.quote(manifest_digest)}; mv {shlex.quote(manifest_target + '.part')} {shlex.quote(manifest_target)}; chmod -R a-w {self.remote}/checkpoint"], stdout=logs, stderr=self.out / "stage.stderr")
        for name in ("m32_static_persistent_geometric_rebind_extension.cu", "m32_static_scheduler_build.py", "b200_static_scheduler_endpoint_pair.py"):
            self.run([*self.scp, str(self.project / name), f"{self.ssh[-1]}:{packet}/.{name}.part"], stdout=logs, stderr=self.out / "stage.stderr")
            self.run([*self.ssh, f"mv {packet}/.{name}.part {packet}/{name}; chmod 400 {packet}/{name}"], stdout=logs, stderr=self.out / "stage.stderr")

    def build(self) -> None:
        self.phase = "production_dispatch_build"
        self.progress("production_dispatch_build")
        build = self.remote + "/build-1"
        old = "/home/glmrunner/gemma4-b200-m32-geometric-rebind-20260728t2356z"
        script = f"""set -Eeuo pipefail
test ! -e {build}; mkdir -p {build}
uid=$(id -u); gid=$(id -g)
sudo -n docker run --rm --user "$uid:$gid" --entrypoint python3 -e TORCH_CUDA_ARCH_LIST=10.0f -v {self.remote}/packet:/packet:ro -v {old}/vllm-src:/vllm:ro -v {old}/cutlass-src:/cutlass:ro -v {build}:/output {IMAGE} /packet/m32_static_scheduler_build.py --source /packet/m32_static_persistent_geometric_rebind_extension.cu --vllm-source /vllm --cutlass-source /cutlass --output /output/artifact --expected-source-sha256 {self.manifest["hashes"]["candidate_source_sha256"]}
"""
        self.run([*self.ssh, script], stdout=self.out / "build.stdout", stderr=self.out / "build.stderr", timeout=self.left(180))

    def run_pair(self) -> None:
        self.phase = "endpoint_pair_submission"
        self.progress("endpoint_pair_submission", science_started=False)
        build = self.remote + "/build-1"
        command = f"set -Eeuo pipefail; python3 {self.remote}/packet/b200_static_scheduler_endpoint_pair.py --remote --root {self.remote} --image {IMAGE} --checkpoint {self.remote}/checkpoint --build {build}/artifact --module $(python3 -c 'import json;print(json.load(open(\"{build}/artifact/BUILD_MANIFEST.json\"))[\"module_path\"])')"
        self.run([*self.ssh, command], stdout=self.out / "worker.stdout", stderr=self.out / "worker.stderr", timeout=self.left(180))

    def retrieve_release(self) -> None:
        self.phase = "artifact_retrieval"
        self.progress("artifact_retrieval")
        destination = self.out / "retrieved"
        destination.mkdir()
        self.run([*self.scp, "-r", f"{self.ssh[-1]}:{self.remote}/artifacts/.", str(destination)], stdout=self.out / "retrieve.stdout", stderr=self.out / "retrieve.stderr", timeout=self.left(90))
        terminal = load(destination / "PAIR_TERMINAL.json")
        if terminal["classification"] not in ("static_scheduler_endpoint_pair", "endpoint_pair_invalid"):
            raise RuntimeError("pair_terminal_invalid")
        self.pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "ready", "--contents", json.dumps({"state": "static_scheduler_endpoint_complete", "terminal": str(destination / "PAIR_TERMINAL.json"), "candidate_build": self.remote + "/build-1"}))
        self.claimed = False
        atomic_json(self.out / "OWNER_TERMINAL.json", {"classification": terminal["classification"], "terminal": str(destination / "PAIR_TERMINAL.json"), "terminal_sha256": sha256(destination / "PAIR_TERMINAL.json"), "bench_released": True})

    def repair_wait(self, exc: Exception) -> bool:
        self.repair_generation += 1
        repair_id = f"endpoint-pre-science-{int(time.time())}-{self.repair_generation}"
        diagnostic = self.out / f"REPAIR_DIAGNOSTIC_{repair_id}.json"
        atomic_json(diagnostic, {
            "schema_version": 1,
            "classification": "recoverable_pre_science_owner_defect",
            "phase": self.phase,
            "error": repr(exc),
            "traceback": traceback.format_exc(),
            "last_command": self.last_command,
            "claimed": self.claimed,
            "candidate_cuda_invocation_started": False,
            "science_started": False,
        })
        repair = self.args.repo_root / "research/factory/tools/repair-handshake"
        deadline = self.deadline.isoformat().replace("+00:00", "Z")
        self.run([str(repair), "ready", "--root", str(self.out), "--repair-id", repair_id, "--deadline", deadline, "--failure-kind", "pre_science_owner_or_integration_defect", "--diagnostic", str(diagnostic), "--retry-scope", "checkpoint_stage_then_production_endpoint"], stdout=self.out / "repair.stdout", stderr=self.out / "repair.stderr", check=False)
        self.progress("repair_wait", repair_id=repair_id, diagnostic=str(diagnostic), retry_scope="checkpoint_stage_then_production_endpoint")
        result = self.run([str(repair), "wait", "--root", str(self.out), "--repair-id", repair_id, "--deadline", deadline, "--poll-seconds", "15"], stdout=self.out / "repair.stdout", stderr=self.out / "repair.stderr", check=False, timeout=self.left(0))
        return result.returncode == 0 and self.left(300) > 0

    def execute(self) -> int:
        self.out.mkdir(parents=True, exist_ok=True)
        try:
            self.validate()
            self.establish_ssh()
            self.claim()
            self.progress("bench_claimed")
            while True:
                try:
                    self.stage()
                    self.build()
                    break
                except Exception as exc:
                    if not self.claimed or self.left(300) <= 0:
                        raise
                    if not self.repair_wait(exc):
                        raise RuntimeError("repair_wait_unresolved") from exc
            while True:
                try:
                    self.run_pair()
                    break
                except Exception as exc:
                    if not self.claimed or self.left(300) <= 0:
                        raise
                    if not self.repair_wait(exc):
                        raise RuntimeError("pair_repair_wait_unresolved") from exc
                    self.phase = "artifact_retrieval"
                    break
            while True:
                try:
                    self.retrieve_release()
                    return 0
                except Exception as exc:
                    if not self.claimed or self.left(300) <= 0:
                        raise
                    if not self.repair_wait(exc):
                        raise RuntimeError("retrieval_repair_wait_unresolved") from exc
        except Exception as exc:
            atomic_json(self.out / "OWNER_INCOMPLETE.json", {"classification": "recoverable_or_deadline_endpoint_boundary", "phase": self.phase, "error": repr(exc), "traceback": traceback.format_exc(), "last_command": self.last_command, "claimed": self.claimed})
            if self.claimed:
                if self.left(0) <= 0:
                    self.pool("release", "--project", PROJECT, "--bench", BENCH, "--condition", "maintenance", "--contents", json.dumps({"state": "endpoint_incomplete_deadline", "diagnostic": str(self.out / "OWNER_INCOMPLETE.json")}), check=False)
            return 1
        finally:
            self.stop.set()


def emit(args: argparse.Namespace) -> int:
    hashes = {name: sha256(args.project_root / file) for name, file in {
        "owner_sha256": "b200_static_scheduler_endpoint_owner.py",
        "runner_sha256": "b200_static_scheduler_endpoint_pair.py",
        "candidate_source_sha256": "m32_static_persistent_geometric_rebind_extension.cu",
        "checkpoint_manifest_sha256": "inputs/static-scheduler-endpoint-checkpoint/model-files.sha256",
        "endpoint_driver_sha256": "b200_static_scheduler_endpoint_pair.py",
    }.items()}
    binding = load(args.binding)
    manifest = {"schema_version": 1, "classification": "static_scheduler_endpoint_runtime_manifest", "binding_sha256": sha256(args.binding), "binding": args.binding.name, "hashes": hashes, "runtime_image": IMAGE, "vllm_commit": VLLM, "cutlass_tag": CUTLASS, "checkpoint_bytes": binding["scientific_contract"]["checkpoint_bytes"]}
    atomic_json(args.runtime_manifest, manifest)
    preclaim = {"schema_version": 1, "classification": "static_scheduler_endpoint_preclaim", "binding_sha256": sha256(args.binding), "runtime_manifest_sha256": sha256(args.runtime_manifest), "hashes": hashes, "checkpoint_manifest_sha256": hashes["checkpoint_manifest_sha256"], "exact_detached_launch_command": binding["launch"]["command_template"], "claim_started": False, "science_consumed": False}
    atomic_json(args.preclaim, preclaim)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("/root/workspace"))
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--lab", type=Path)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--preclaim", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--emit-preclaim", action="store_true")
    args = parser.parse_args()
    if args.emit_preclaim:
        return emit(args)
    if args.lab is None or args.output is None:
        parser.error("--lab and --output required for execution")
    return Owner(args).execute()


if __name__ == "__main__":
    raise SystemExit(main())
