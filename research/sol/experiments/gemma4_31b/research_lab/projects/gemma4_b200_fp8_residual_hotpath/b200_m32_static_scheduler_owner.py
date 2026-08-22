#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import threading
import time
from typing import Any


PROJECT = "gemma4_b200_fp8_residual_hotpath"
VLLM_COMMIT = "6d4a8e6d204a9b2827544003b26321fff62923da"
CUTLASS_TAG = "v4.2.1"
IMAGE = (
    "docker.io/vllm/vllm-openai:gemma4@sha256:"
    "952594c2e6ded02be6e3f195eb95d5a50c5f2a44a879427b2f77c32e0a732a79"
)
DERIVED_IMAGE = "gemma4-m32-static-scheduler:20260729"
PACKET_FILES = (
    "m32_static_persistent_geometric_rebind_extension.cu",
    "m32_static_scheduler_build.py",
    "b200_m32_static_scheduler_component.py",
    "m32_static_scheduler.Dockerfile",
    "B200_M32_GEOMETRIC_REBIND_RUNTIME_MANIFEST.json",
)


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def parse_time(value: str) -> dt.datetime:
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp requires timezone")
    return parsed.astimezone(dt.UTC)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
        temporary = Path(handle.name)
    os.replace(temporary, path)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def run(
    command: list[str],
    *,
    stdout: Path | None = None,
    stderr: Path | None = None,
    check: bool = True,
    timeout: float | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    stdout_handle = stdout.open("a") if stdout else subprocess.PIPE
    stderr_handle = stderr.open("a") if stderr else subprocess.PIPE
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=stdout_handle,
            stderr=stderr_handle,
            check=False,
            timeout=timeout,
            env=env,
        )
    finally:
        if stdout:
            stdout_handle.close()
        if stderr:
            stderr_handle.close()
    if check and result.returncode:
        detail = result.stderr if result.stderr is not None else ""
        raise RuntimeError(
            f"command_failed:{command[0]}:{result.returncode}:{detail[-1000:]}"
        )
    return result


class Owner:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.project_root = args.project_root.resolve()
        self.output = args.output.resolve()
        self.output.mkdir(parents=True, exist_ok=False)
        self.mechanism = load_json(args.mechanism)
        self.runtime_manifest = load_json(args.runtime_manifest)
        self.execution = load_json(args.execution_binding)
        self.deadline = parse_time(self.execution["lifecycle"]["deadline_utc"])
        self.release_by = parse_time(
            self.execution["lifecycle"]["release_by_utc"]
        )
        self.repo_root = args.repo_root.resolve()
        self.pool_env = dict(os.environ)
        self.pool_env["PYTHONPATH"] = str(
            self.repo_root / "research/factory/src"
        )
        self.repair_tool = (
            self.repo_root / "research/factory/tools/repair-handshake"
        )
        self.bench = self.execution["bench"]
        self.remote_root = self.execution["remote_root"]
        self.claimed = False
        self.heartbeat_stop = threading.Event()
        self.heartbeat_thread: threading.Thread | None = None
        self.repair_generation = 0
        self.build_generation = 0
        self.retrieval_generation = 0
        self.current_build_remote = ""
        self.current_stage = "preflight"
        self.ssh_base: list[str] = []
        self.scp_base: list[str] = []

    def remaining(self, reserve_seconds: float = 0.0) -> float:
        return max(
            0.0,
            (self.deadline - utc_now()).total_seconds() - reserve_seconds,
        )

    def progress(self, phase: str, **extra: Any) -> None:
        self.current_stage = phase
        entry = {"at_utc": utc_now().isoformat(), "phase": phase, **extra}
        with (self.output / "OWNER_PROGRESS.jsonl").open("a") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        atomic_json(
            self.output / "OWNER_STATE.json",
            {
                "schema_version": 1,
                "state": "running",
                "phase": phase,
                "bench": self.bench,
                "claimed": self.claimed,
                "deadline_utc": self.deadline.isoformat(),
                "release_by_utc": self.release_by.isoformat(),
                "remote_root": self.remote_root,
                "current_build_remote": self.current_build_remote,
                **extra,
            },
        )

    def pool(self, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        return run(
            [
                "python3",
                "-m",
                "grad_research.gpu_pool",
                "--lab",
                str(self.args.lab),
                *arguments,
            ],
            check=check,
            env=self.pool_env,
        )

    def validate_hashes(self) -> None:
        hashes = self.runtime_manifest["artifact_hashes"]
        mapping = {
            "candidate_source_sha256":
                "m32_static_persistent_geometric_rebind_extension.cu",
            "build_script_sha256": "m32_static_scheduler_build.py",
            "runner_sha256": "b200_m32_static_scheduler_component.py",
            "owner_sha256": "b200_m32_static_scheduler_owner.py",
            "dockerfile_sha256": "m32_static_scheduler.Dockerfile",
        }
        for field, filename in mapping.items():
            observed = sha256(self.project_root / filename)
            if hashes[field] != observed:
                raise RuntimeError(f"mechanism_hash_mismatch:{field}")
        if sha256(self.args.mechanism) != self.execution["mechanism"]["artifact_sha256"]:
            raise RuntimeError("execution_mechanism_hash_mismatch")
        if hashes["candidate_source_sha256"] != self.execution["mechanism"]["candidate_source_sha256"]:
            raise RuntimeError("execution_candidate_source_mismatch")

    def preflight(self) -> None:
        if not self.execution.get("claim_allowed"):
            raise RuntimeError("director_claim_gate_closed")
        if self.execution.get("project") != PROJECT:
            raise RuntimeError("execution_project_mismatch")
        claim_start_by = parse_time(
            self.execution["lifecycle"]["claim_start_by_utc"]
        )
        if utc_now() > claim_start_by:
            raise RuntimeError("claim_start_fence_expired")
        if self.release_by > self.deadline:
            raise RuntimeError("release_after_deadline")
        if not self.args.ssh_key.is_file():
            raise RuntimeError("ssh_key_missing")
        if not self.args.known_hosts.is_file():
            raise RuntimeError("known_hosts_missing")
        if not self.repair_tool.is_file():
            raise RuntimeError("repair_handshake_missing")
        self.validate_hashes()
        row_result = self.pool("show", "--bench", self.bench)
        row = json.loads(row_result.stdout)
        resource = row.get("resource", {})
        host = resource.get("public_ipv4")
        user = resource.get("ssh_user")
        known = resource.get("known_hosts_namespace")
        if not host or not user:
            raise RuntimeError("bench_ssh_identity_missing")
        if known and Path(known).resolve() != self.args.known_hosts.resolve():
            raise RuntimeError("known_hosts_namespace_mismatch")
        target = f"{user}@{host}"
        ssh_options = [
            "-i",
            str(self.args.ssh_key),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={self.args.known_hosts}",
            "-o",
            "ConnectTimeout=15",
        ]
        self.ssh_base = ["ssh", "-n", *ssh_options, target]
        self.scp_base = ["scp", "-p", *ssh_options]
        self.progress("preflight_complete", host=host, ssh_user=user)

    def heartbeat_loop(self) -> None:
        while not self.heartbeat_stop.wait(30):
            self.pool(
                "heartbeat",
                "--project",
                PROJECT,
                "--bench",
                self.bench,
                check=False,
            )

    def claim(self) -> None:
        self.pool("claim", "--project", PROJECT, "--bench", self.bench)
        self.claimed = True
        self.heartbeat_thread = threading.Thread(
            target=self.heartbeat_loop, daemon=True
        )
        self.heartbeat_thread.start()
        self.progress("bench_claimed")

    def ssh(
        self,
        script: str,
        *,
        stdout: Path,
        stderr: Path,
        check: bool = True,
        timeout: float | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return run(
            [*self.ssh_base, script],
            stdout=stdout,
            stderr=stderr,
            check=check,
            timeout=min(timeout or self.remaining(180), self.remaining(120)),
        )

    def stage_packet(self) -> None:
        self.progress("packet_stage")
        packet_remote = f"{self.remote_root}/packet"
        stage_stdout = self.output / "packet-stage.stdout"
        stage_stderr = self.output / "packet-stage.stderr"
        self.ssh(
            (
                f"set -Eeuo pipefail; mkdir -p {shlex.quote(packet_remote)}; "
                f"chmod 700 {shlex.quote(packet_remote)}"
            ),
            stdout=stage_stdout,
            stderr=stage_stderr,
        )
        for filename in PACKET_FILES:
            source = self.project_root / filename
            expected = sha256(source)
            remote_part = f"{packet_remote}/.{filename}.part"
            remote_final = f"{packet_remote}/{filename}"
            result = run(
                [
                    *self.scp_base,
                    str(source),
                    f"{self.ssh_base[-1]}:{remote_part}",
                ],
                stdout=stage_stdout,
                stderr=stage_stderr,
                check=False,
                timeout=min(120, self.remaining(180)),
            )
            if result.returncode:
                raise RuntimeError(f"packet_scp_failed:{filename}")
            self.ssh(
                (
                    "set -Eeuo pipefail; "
                    f"test \"$(sha256sum {shlex.quote(remote_part)} | "
                    f"awk '{{print $1}}')\" = {shlex.quote(expected)}; "
                    f"mv {shlex.quote(remote_part)} {shlex.quote(remote_final)}; "
                    f"chmod 400 {shlex.quote(remote_final)}"
                ),
                stdout=stage_stdout,
                stderr=stage_stderr,
            )

    def prepare_image_and_sources(self) -> None:
        self.progress("resident_source_reconciliation")
        packet = f"{self.remote_root}/packet"
        stdout = self.output / "cold-source.stdout"
        stderr = self.output / "cold-source.stderr"
        uid_command = "uid=$(id -u); gid=$(id -g)"
        script = f"""
set -Eeuo pipefail
{uid_command}
root={shlex.quote(self.remote_root)}
resident={shlex.quote(self.execution["mutable_integration"]["resident_source_reuse_from"])}
packet={shlex.quote(packet)}
mkdir -p "$root"
if ! sudo -n docker image inspect {shlex.quote(DERIVED_IMAGE)} >/dev/null 2>&1; then
  sudo -n docker build --pull=false -f "$packet/m32_static_scheduler.Dockerfile" -t {shlex.quote(DERIVED_IMAGE)} "$packet"
fi
test -f "$resident/vllm-src/IMMUTABLE.json" && grep -q {shlex.quote(VLLM_COMMIT)} "$resident/vllm-src/IMMUTABLE.json"
test -f "$resident/cutlass-src/IMMUTABLE.json" && grep -q {shlex.quote(CUTLASS_TAG)} "$resident/cutlass-src/IMMUTABLE.json"
test ! -e "$root/vllm-src" && test ! -e "$root/cutlass-src"
ln -s "$resident/vllm-src" "$root/vllm-src"
ln -s "$resident/cutlass-src" "$root/cutlass-src"
if [[ ! -f "$root/vllm-src/IMMUTABLE.json" ]] || ! grep -q {shlex.quote(VLLM_COMMIT)} "$root/vllm-src/IMMUTABLE.json"; then
  test ! -e "$root/vllm-src"
  if [[ -e "$root/vllm-src.part" ]]; then rm -rf -- "$root/vllm-src.part"; fi
  sudo -n docker run --rm --user "$uid:$gid" --entrypoint bash -v "$root:/state" {shlex.quote(DERIVED_IMAGE)} -lc \
    'git clone --filter=blob:none https://github.com/vllm-project/vllm.git /state/vllm-src.part && cd /state/vllm-src.part && git checkout {VLLM_COMMIT} && test "$(git rev-parse HEAD)" = "{VLLM_COMMIT}" && printf "%s\\n" "{{\\"commit\\":\\"{VLLM_COMMIT}\\"}}" > IMMUTABLE.json'
  mv "$root/vllm-src.part" "$root/vllm-src"
fi
if [[ ! -f "$root/cutlass-src/IMMUTABLE.json" ]] || ! grep -q {shlex.quote(CUTLASS_TAG)} "$root/cutlass-src/IMMUTABLE.json"; then
  test ! -e "$root/cutlass-src"
  if [[ -e "$root/cutlass-src.part" ]]; then rm -rf -- "$root/cutlass-src.part"; fi
  sudo -n docker run --rm --user "$uid:$gid" --entrypoint bash -v "$root:/state" {shlex.quote(DERIVED_IMAGE)} -lc \
    'git clone --depth 1 --branch {CUTLASS_TAG} https://github.com/NVIDIA/cutlass.git /state/cutlass-src.part && cd /state/cutlass-src.part && printf "%s\\n" "{{\\"tag\\":\\"{CUTLASS_TAG}\\",\\"commit\\":\\"$(git rev-parse HEAD)\\"}}" > IMMUTABLE.json'
  mv "$root/cutlass-src.part" "$root/cutlass-src"
fi
"""
        self.ssh(
            script,
            stdout=stdout,
            stderr=stderr,
            timeout=min(1800, self.remaining(300)),
        )

    def build_candidate(self) -> None:
        self.build_generation += 1
        self.current_build_remote = (
            f"{self.remote_root}/build-{self.build_generation}"
        )
        self.progress(
            "candidate_build", build_generation=self.build_generation
        )
        packet = f"{self.remote_root}/packet"
        stdout = self.output / f"build-{self.build_generation}.stdout"
        stderr = self.output / f"build-{self.build_generation}.stderr"
        source_hash = self.runtime_manifest["artifact_hashes"][
            "candidate_source_sha256"
        ]
        script = f"""
set -Eeuo pipefail
uid=$(id -u); gid=$(id -g)
test ! -e {shlex.quote(self.current_build_remote)}
mkdir -p {shlex.quote(self.current_build_remote)}
sudo -n docker run --rm --user "$uid:$gid" --entrypoint python3 \
  -e TORCH_CUDA_ARCH_LIST=10.0f \
  -v {shlex.quote(packet)}:/packet:ro \
  -v {shlex.quote(self.remote_root + "/vllm-src")}:/vllm:ro \
  -v {shlex.quote(self.remote_root + "/cutlass-src")}:/cutlass:ro \
  -v {shlex.quote(self.current_build_remote)}:/output \
  {shlex.quote(DERIVED_IMAGE)} \
  /packet/m32_static_scheduler_build.py \
  --source /packet/m32_static_persistent_geometric_rebind_extension.cu \
  --vllm-source /vllm --cutlass-source /cutlass \
  --output /output/artifact \
  --expected-source-sha256 {shlex.quote(source_hash)}
test -r {shlex.quote(self.current_build_remote + "/artifact/BUILD_MANIFEST.json")}
"""
        self.ssh(
            script,
            stdout=stdout,
            stderr=stderr,
            timeout=min(2400, self.remaining(300)),
        )

    def run_consumer(self, resume: bool) -> None:
        self.progress("component_consumer", resume=resume)
        packet = f"{self.remote_root}/packet"
        remote_parent = f"{self.remote_root}/science"
        remote_output = f"{remote_parent}/component"
        stdout = self.output / "component.stdout"
        stderr = self.output / "component.stderr"
        resume_flag = "--resume" if resume else ""
        create_guard = (
            f"test -d {shlex.quote(remote_output)}"
            if resume
            else (
                f"mkdir -p {shlex.quote(remote_parent)}; "
                f"test ! -e {shlex.quote(remote_output)}"
            )
        )
        script = f"""
set -Eeuo pipefail
uid=$(id -u); gid=$(id -g)
{create_guard}
sudo -n docker run --rm --gpus all --ipc=host --network=host \
  --user "$uid:$gid" --entrypoint python3 \
  -v {shlex.quote(packet)}:/packet:ro \
  -v {shlex.quote(self.current_build_remote + "/artifact")}:/build:ro \
  -v {shlex.quote(remote_parent)}:/results \
  {shlex.quote(DERIVED_IMAGE)} \
  /packet/b200_m32_static_scheduler_component.py \
  --binding /packet/B200_M32_GEOMETRIC_REBIND_RUNTIME_MANIFEST.json \
  --candidate-source /packet/m32_static_persistent_geometric_rebind_extension.cu \
  --build-manifest /build/BUILD_MANIFEST.json \
  --output /results/component {resume_flag}
"""
        result = self.ssh(
            script,
            stdout=stdout,
            stderr=stderr,
            check=False,
            timeout=min(1800, self.remaining(300)),
        )
        if result.returncode:
            raise RuntimeError(f"component_consumer_exit:{result.returncode}")

    def retrieve(self) -> None:
        self.progress("artifact_retrieval")
        destination = self.output / "retrieved"
        self.retrieval_generation += 1
        temporary = self.output / (
            f".retrieved.part-{self.retrieval_generation}"
        )
        if destination.exists():
            terminal = load_json(destination / "TERMINAL.json")
            self.validate_terminal(terminal)
            return
        temporary.mkdir()
        result = run(
            [
                *self.scp_base,
                "-r",
                f"{self.ssh_base[-1]}:{self.remote_root}/science/component/.",
                str(temporary),
            ],
            stdout=self.output / "retrieve.stdout",
            stderr=self.output / "retrieve.stderr",
            check=False,
            timeout=min(300, self.remaining(120)),
        )
        if result.returncode:
            raise RuntimeError(f"artifact_retrieval_exit:{result.returncode}")
        terminal = load_json(temporary / "TERMINAL.json")
        self.validate_terminal(terminal)
        os.replace(temporary, destination)

    def validate_terminal(self, terminal: dict[str, Any]) -> None:
        classifications = {
            "component_positive_for_director_endpoint_disposition",
            "component_negative_stop",
            "component_exactness_stop",
        }
        if terminal.get("classification") not in classifications:
            raise RuntimeError("terminal_classification_not_releasable")
        if not terminal.get("science_consumed"):
            raise RuntimeError("terminal_science_not_consumed")
        expected = self.runtime_manifest["oracle"]["expected_families"]
        if terminal["classification"] == "component_exactness_stop":
            if not terminal.get("failed_family"):
                raise RuntimeError("exactness_terminal_missing_family")
            rows = terminal.get("rows", [])
            if not rows or rows[-1].get("correctness", {}).get(
                "bitwise_equal"
            ) is not False:
                raise RuntimeError("exactness_terminal_missing_oracle")
            return
        if terminal.get("expected_rows") != expected:
            raise RuntimeError("terminal_expected_ledger_mismatch")
        if terminal.get("completed_rows") != expected:
            raise RuntimeError("terminal_incomplete_ledger")
        rows = terminal.get("rows", [])
        if len(rows) != 6:
            raise RuntimeError("terminal_row_count")
        for required in expected:
            row = next((value for value in rows if value.get("name") == required), None)
            if row is None:
                raise RuntimeError(f"terminal_family_missing:{required}")
            if not row.get("correctness", {}).get("bitwise_equal"):
                raise RuntimeError(f"terminal_family_incorrect:{required}")
            if not row.get("operand_hashes") or not row.get(
                "tensor_contracts"
            ):
                raise RuntimeError(f"terminal_provenance_missing:{required}")
        if terminal.get("candidate_source_sha256") != self.runtime_manifest[
            "artifact_hashes"
        ]["candidate_source_sha256"]:
            raise RuntimeError("terminal_candidate_source_mismatch")

    def diagnostic(self, error: Exception) -> Path:
        invocation_remote = (
            f"{self.remote_root}/science/component/INVOCATION_STATE.json"
        )
        repairable_remote = (
            f"{self.remote_root}/science/component/REPAIRABLE.json"
        )
        diagnostic = self.output / (
            f"DIAGNOSTIC_REPAIR_{self.repair_generation + 1}.json"
        )
        remote_snapshot = self.output / (
            f"remote-snapshot-{self.repair_generation + 1}.stdout"
        )
        self.ssh(
            (
                "set +e; "
                f"for p in {shlex.quote(invocation_remote)} "
                f"{shlex.quote(repairable_remote)}; do "
                "if test -r \"$p\"; then echo \"PATH=$p\"; cat \"$p\"; fi; done"
            ),
            stdout=remote_snapshot,
            stderr=self.output
            / f"remote-snapshot-{self.repair_generation + 1}.stderr",
            check=False,
            timeout=min(60, self.remaining(120)),
        )
        retry_scope = (
            "retrieve"
            if self.current_stage == "artifact_retrieval"
            else "build"
            if self.current_stage == "candidate_build"
            else "source_stage"
            if self.current_stage == "cold_source_reconciliation"
            else "consumer:resume"
        )
        atomic_json(
            diagnostic,
            {
                "schema_version": 1,
                "classification": "recoverable_owner_stage_failure",
                "stage": self.current_stage,
                "retry_scope": retry_scope,
                "error_type": type(error).__name__,
                "error": str(error),
                "remote_snapshot": str(remote_snapshot),
                "remote_snapshot_sha256":
                    sha256(remote_snapshot) if remote_snapshot.exists() else None,
            },
        )
        return diagnostic

    def wait_for_repair(self, diagnostic: Path) -> str:
        self.repair_generation += 1
        repair_id = f"m32-static-{self.repair_generation}"
        repair_deadline = min(
            self.deadline - dt.timedelta(minutes=3),
            utc_now() + dt.timedelta(minutes=20),
        )
        if repair_deadline <= utc_now():
            raise RuntimeError("repair_window_exhausted")
        diagnostic_value = load_json(diagnostic)
        retry_scope = diagnostic_value["retry_scope"]
        run(
            [
                str(self.repair_tool),
                "ready",
                "--root",
                str(self.output),
                "--repair-id",
                repair_id,
                "--deadline",
                repair_deadline.isoformat(),
                "--failure-kind",
                diagnostic_value["classification"],
                "--diagnostic",
                str(diagnostic),
                "--retry-scope",
                retry_scope,
            ]
        )
        self.progress(
            "repair_wait",
            repair_id=repair_id,
            retry_scope=retry_scope,
            repair_deadline_utc=repair_deadline.isoformat(),
        )
        status = run(
            [
                str(self.repair_tool),
                "wait",
                "--root",
                str(self.output),
                "--repair-id",
                repair_id,
                "--deadline",
                repair_deadline.isoformat(),
                "--poll-seconds",
                "10",
            ],
            check=False,
            timeout=max(1.0, (repair_deadline - utc_now()).total_seconds() + 5),
        )
        if status.returncode:
            raise RuntimeError("repair_request_deadline")
        value = json.loads(status.stdout)
        if value.get("state") not in ("requested", "repair_terminal"):
            raise RuntimeError(f"repair_request_state:{value.get('state')}")
        request_path = (
            self.output
            / ".repair-handshakes"
            / repair_id
            / "REPAIR_REQUEST.json"
        )
        request = load_json(request_path)
        patch = request.get("patch_artifact")
        if patch:
            self.consume_patch(Path(patch), request.get("retry_scope"))
        return str(request.get("retry_scope") or retry_scope)

    def consume_patch(self, patch_path: Path, retry_scope: str | None) -> None:
        patch = load_json(patch_path)
        if patch.get("project") != PROJECT:
            raise RuntimeError("repair_patch_project_mismatch")
        if patch.get("retry_scope") != retry_scope:
            raise RuntimeError("repair_patch_scope_mismatch")
        for replacement in patch.get("replacements", []):
            source = Path(replacement["source"]).resolve()
            filename = replacement["destination"]
            if filename not in PACKET_FILES:
                raise RuntimeError(f"repair_destination_forbidden:{filename}")
            if sha256(source) != replacement["sha256"]:
                raise RuntimeError(f"repair_source_hash_mismatch:{filename}")
            remote = f"{self.remote_root}/packet/{filename}"
            part = f"{remote}.repair-{self.repair_generation}.part"
            run(
                [
                    *self.scp_base,
                    str(source),
                    f"{self.ssh_base[-1]}:{part}",
                ],
                timeout=min(120, self.remaining(180)),
            )
            self.ssh(
                (
                    f"set -Eeuo pipefail; chmod 600 {shlex.quote(remote)}; "
                    f"test \"$(sha256sum {shlex.quote(part)} | awk "
                    f"'{{print $1}}')\" = {shlex.quote(replacement['sha256'])}; "
                    f"mv {shlex.quote(part)} {shlex.quote(remote)}; "
                    f"chmod 400 {shlex.quote(remote)}"
                ),
                stdout=self.output / "repair-stage.stdout",
                stderr=self.output / "repair-stage.stderr",
            )

    def execute_scope(self, scope: str) -> None:
        if scope == "source_stage":
            self.prepare_image_and_sources()
            self.build_candidate()
            self.run_consumer(resume=False)
            self.retrieve()
        elif scope == "build":
            self.build_candidate()
            self.run_consumer(
                resume=self.remote_component_exists()
            )
            self.retrieve()
        elif scope.startswith("consumer:"):
            self.run_consumer(resume=True)
            self.retrieve()
        elif scope == "retrieve":
            self.retrieve()
        else:
            raise RuntimeError(f"unsupported_repair_scope:{scope}")

    def remote_component_exists(self) -> bool:
        result = self.ssh(
            f"test -d {shlex.quote(self.remote_root + '/science/component')}",
            stdout=self.output / "component-exists.stdout",
            stderr=self.output / "component-exists.stderr",
            check=False,
            timeout=min(30, self.remaining(120)),
        )
        return result.returncode == 0

    def release(self, condition: str, terminal: Path | None) -> None:
        if not self.claimed:
            return
        contents = {
            "state": "m32_static_scheduler_component_complete"
            if terminal
            else "m32_static_scheduler_incomplete_retained_artifacts",
            "remote_root": self.remote_root,
            "derived_image": DERIVED_IMAGE,
            "vllm_commit": VLLM_COMMIT,
            "cutlass_tag": CUTLASS_TAG,
            "candidate_build": self.current_build_remote,
            "terminal": str(terminal) if terminal else None,
        }
        self.pool(
            "release",
            "--project",
            PROJECT,
            "--bench",
            self.bench,
            "--condition",
            condition,
            "--contents",
            json.dumps(contents, sort_keys=True),
        )
        self.claimed = False
        self.progress("bench_released", condition=condition)

    def run(self) -> int:
        terminal: Path | None = None
        try:
            self.preflight()
            self.claim()
            self.stage_packet()
            scope = "source_stage"
            while True:
                try:
                    self.execute_scope(scope)
                    terminal = self.output / "retrieved/TERMINAL.json"
                    break
                except Exception as error:
                    diagnostic = self.diagnostic(error)
                    scope = self.wait_for_repair(diagnostic)
            terminal_value = load_json(terminal)
            self.release("available", terminal)
            atomic_json(
                self.output / "OWNER_TERMINAL.json",
                {
                    "schema_version": 1,
                    "classification": terminal_value["classification"],
                    "scientific_terminal": str(terminal),
                    "scientific_terminal_sha256": sha256(terminal),
                    "bench_released": True,
                    "release_condition": "available",
                    "remote_resident_state": self.remote_root,
                },
            )
            return 0
        except Exception as error:
            if self.claimed:
                try:
                    self.release("maintenance", terminal)
                except Exception as release_error:
                    atomic_json(
                        self.output / "RELEASE_FAILURE.json",
                        {
                            "error": str(release_error),
                            "original_error": str(error),
                        },
                    )
            atomic_json(
                self.output / "OWNER_INCOMPLETE.json",
                {
                    "schema_version": 1,
                    "classification": "owner_deadline_or_nonrecoverable_boundary",
                    "stage": self.current_stage,
                    "error_type": type(error).__name__,
                    "error": str(error),
                    "bench_released": not self.claimed,
                    "release_condition": "maintenance",
                },
            )
            return 1
        finally:
            self.heartbeat_stop.set()
            if self.heartbeat_thread is not None:
                self.heartbeat_thread.join(timeout=5)


def validate_only(args: argparse.Namespace) -> int:
    mechanism = load_json(args.runtime_manifest)
    expected = {
        "candidate_source_sha256": "m32_static_persistent_geometric_rebind_extension.cu",
        "build_script_sha256": "m32_static_scheduler_build.py",
        "runner_sha256": "b200_m32_static_scheduler_component.py",
        "owner_sha256": "b200_m32_static_scheduler_owner.py",
        "dockerfile_sha256": "m32_static_scheduler.Dockerfile",
    }
    for field, filename in expected.items():
        if mechanism["artifact_hashes"][field] != sha256(
            args.project_root / filename
        ):
            raise RuntimeError(f"validate_hash_mismatch:{field}")
    if mechanism["lifecycle"]["claim_allowed_now"]:
        raise RuntimeError("offline_binding_must_close_claim")
    atomic_json(
        args.validate_only,
        {
            "schema_version": 1,
            "classification": "owner_local_contract_validation",
            "provider_mutated": False,
            "gpu_claimed": False,
            "repair_handshake": str(
                args.repo_root / "research/factory/tools/repair-handshake"
            ),
            "detached_launch_contract": mechanism["lifecycle"][
                "detached_launch"
            ],
            "supported_retry_scopes": [
                "source_stage",
                "build",
                "consumer:<family>",
                "retrieve",
            ],
        },
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--mechanism", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path)
    parser.add_argument("--execution-binding", type=Path)
    parser.add_argument("--lab", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ssh-key", type=Path)
    parser.add_argument("--known-hosts", type=Path)
    parser.add_argument("--validate-only", type=Path)
    parser.add_argument("--emit-runtime-manifest", type=Path)
    args = parser.parse_args()
    if args.emit_runtime_manifest is not None:
        manifest = load_json(
            args.project_root / "B200_FP8_M32_NEXT_MECHANISM.json"
        )
        manifest["artifact_hashes"] = {
            "candidate_source_sha256": sha256(
                args.project_root
                / "m32_static_persistent_geometric_rebind_extension.cu"
            ),
            "build_script_sha256": sha256(
                args.project_root / "m32_static_scheduler_build.py"
            ),
            "runner_sha256": sha256(
                args.project_root / "b200_m32_static_scheduler_component.py"
            ),
            "owner_sha256": sha256(
                args.project_root / "b200_m32_static_scheduler_owner.py"
            ),
            "dockerfile_sha256": sha256(
                args.project_root / "m32_static_scheduler.Dockerfile"
            ),
        }
        manifest["mechanism"].update(
            {
                "name": "m32_static_persistent_runtime_sm_count_geometric_rebind",
                "candidate_source": "m32_static_persistent_geometric_rebind_extension.cu",
                "candidate_symbol": "M32StaticPersistentGeometricRebindGemm::GemmKernel",
            }
        )
        manifest["lifecycle"]["claim_allowed_now"] = False
        atomic_json(args.emit_runtime_manifest, manifest)
        return 0
    if args.validate_only is not None:
        if args.runtime_manifest is None:
            parser.error("--runtime-manifest is required for validation")
        return validate_only(args)
    required = (
        args.execution_binding,
        args.runtime_manifest,
        args.lab,
        args.output,
        args.ssh_key,
        args.known_hosts,
    )
    if any(value is None for value in required):
        parser.error(
            "--execution-binding, --lab, --output, --ssh-key, and "
            "--known-hosts are required for execution"
        )
    return Owner(args).run()


if __name__ == "__main__":
    raise SystemExit(main())
