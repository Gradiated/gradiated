#!/usr/bin/env python3
"""Durable controller-host owner for one continuous exact DFlash H200 claim."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import shlex
import subprocess
import sys
import tarfile
import tempfile
import threading
import time
from typing import Any

PROJECT_NAME = "gemma4_dflash_exact_target_h200_component"
PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parents[1]
FACTORY_SRC = pathlib.Path("/root/workspace/research/factory/src")
REPAIR_TOOL = pathlib.Path("/root/workspace/research/factory/tools/repair-handshake")
RATE_USD_PER_HOUR = 2.45
AUTHORIZED_USD = 6.0


class Boundary(RuntimeError):
    def __init__(self, kind: str, message: str, recoverable: bool = True):
        super().__init__(f"{kind}:{message}")
        self.kind = kind
        self.message = message
        self.recoverable = recoverable


def utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def iso(value: datetime.datetime | None = None) -> str:
    return (value or utc_now()).isoformat().replace("+00:00", "Z")


def parse_time(value: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Boundary("typed_json_boundary", f"{path}_not_object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pool(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "grad_research.gpu_pool",
            "--lab",
            str(LAB),
            *args,
        ],
        env={**os.environ, "PYTHONPATH": str(FACTORY_SRC)},
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if check and result.returncode:
        raise Boundary("gpu_pool_boundary", result.stderr[-1600:], False)
    return result


class Heartbeat:
    def __init__(self, artifact_root: pathlib.Path, claimed_at: str) -> None:
        self.artifact_root = artifact_root
        self.claimed_at = claimed_at
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stop.wait(30):
            result = pool(
                "heartbeat",
                "--project",
                PROJECT_NAME,
                "--expected-claimed-at",
                self.claimed_at,
                check=False,
            )
            with (self.artifact_root / "heartbeat.log").open("a") as handle:
                handle.write(
                    json.dumps(
                        {
                            "at_utc": iso(),
                            "returncode": result.returncode,
                            "stdout": result.stdout,
                            "stderr": result.stderr,
                        },
                        sort_keys=True,
                    )
                    + "\n"
                )

    def __enter__(self) -> "Heartbeat":
        self.thread.start()
        return self

    def __exit__(self, *_: object) -> None:
        self.stop.set()
        self.thread.join(timeout=5)


class Remote:
    def __init__(
        self, bench: dict[str, Any], artifact_root: pathlib.Path, deadline: datetime.datetime
    ) -> None:
        resource = bench["resource"]
        for key in (
            "public_ipv4",
            "ssh_user",
            "ssh_identity_path",
            "known_hosts_namespace",
        ):
            if not resource.get(key):
                raise Boundary("ssh_identity_boundary", f"missing:{key}", False)
        for key in ("ssh_identity_path", "known_hosts_namespace"):
            if not pathlib.Path(resource[key]).exists():
                raise Boundary("ssh_identity_boundary", f"path:{resource[key]}", False)
        common = [
            "-i",
            resource["ssh_identity_path"],
            "-o",
            "BatchMode=yes",
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={resource['known_hosts_namespace']}",
            "-o",
            "ConnectTimeout=20",
        ]
        self.target = f"{resource['ssh_user']}@{resource['public_ipv4']}"
        self.ssh = ["ssh", *common, self.target]
        self.scp = ["scp", *common]
        self.artifact_root = artifact_root
        self.deadline = deadline

    def timeout(self, cap: int, reserve: int = 120) -> int:
        left = int((self.deadline - utc_now()).total_seconds() - reserve)
        if left <= 0:
            raise Boundary("typed_deadline_boundary", "no_operation_time", False)
        return min(cap, left)

    def run(
        self, command: str, label: str, cap: int = 600, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [*self.ssh, command],
            text=True,
            capture_output=True,
            timeout=self.timeout(cap),
            check=False,
        )
        (self.artifact_root / f"{label}.stdout").write_text(result.stdout)
        (self.artifact_root / f"{label}.stderr").write_text(result.stderr)
        if check and result.returncode:
            raise Boundary(
                "remote_command_boundary",
                f"{label}:rc={result.returncode}:{result.stderr[-1600:]}",
            )
        return result

    def put(self, source: pathlib.Path, destination: str, label: str) -> None:
        result = subprocess.run(
            [*self.scp, str(source), f"{self.target}:{destination}"],
            text=True,
            capture_output=True,
            timeout=self.timeout(600),
            check=False,
        )
        (self.artifact_root / f"{label}.stdout").write_text(result.stdout)
        (self.artifact_root / f"{label}.stderr").write_text(result.stderr)
        if result.returncode:
            raise Boundary("remote_transfer_boundary", result.stderr[-1600:])

    def get(self, source: str, destination: pathlib.Path, label: str) -> None:
        result = subprocess.run(
            [*self.scp, f"{self.target}:{source}", str(destination)],
            text=True,
            capture_output=True,
            timeout=self.timeout(600),
            check=False,
        )
        (self.artifact_root / f"{label}.stdout").write_text(result.stdout)
        (self.artifact_root / f"{label}.stderr").write_text(result.stderr)
        if result.returncode:
            raise Boundary("remote_retrieval_boundary", result.stderr[-1600:])


def validate_ready(binding: dict[str, Any]) -> dict[str, Any]:
    ready_path = PROJECT / "DFLASH_H200_COMPONENT_READY.json"
    ready = load(ready_path)
    if sha256(ready_path) != binding["ready_sha256"]:
        raise Boundary("execution_binding_boundary", "ready_digest", False)
    archive = PROJECT / ready["packet"]["archive"]
    if sha256(archive) != ready["packet"]["archive_sha256"]:
        raise Boundary("typed_packet_boundary", "archive_digest", False)
    for row in ready["immutable_files"]:
        path = pathlib.Path(row["absolute_path"])
        if not path.is_file() or path.stat().st_size != row["bytes"]:
            raise Boundary("typed_packet_boundary", f"missing:{path}", False)
        if sha256(path) != row["sha256"]:
            raise Boundary("typed_packet_boundary", f"hash:{path}", False)
    return ready


def validate_claim(binding: dict[str, Any]) -> dict[str, Any]:
    result = pool("show", "--bench", binding["bench_id"])
    bench = json.loads(result.stdout)
    claim = bench.get("claim")
    if not isinstance(claim, dict):
        raise Boundary("claim_generation_boundary", "bench_not_claimed", False)
    if claim.get("project") != PROJECT_NAME:
        raise Boundary("claim_generation_boundary", "wrong_project", False)
    if claim.get("claimed_at") != binding["claimed_at"]:
        raise Boundary("claim_generation_boundary", "claimed_at_mismatch", False)
    if bench.get("resource", {}).get("gpu_uuid") != binding["gpu_uuid"]:
        raise Boundary("hardware_identity_boundary", "gpu_uuid", False)
    return bench


def stage_packet(
    remote: Remote, archive: pathlib.Path, digest: str
) -> tuple[str, str]:
    base = f"/home/glmrunner/dflash-component/packets/{digest}"
    remote_archive = f"{base}.tar"
    check = remote.run(
        f"test -f {shlex.quote(remote_archive)} && "
        f"test \"$(sha256sum {shlex.quote(remote_archive)} | cut -d' ' -f1)\" = {shlex.quote(digest)} && "
        f"test -f {shlex.quote(base + '/PACKET_MANIFEST.json')}",
        "packet-reconcile",
        cap=60,
        check=False,
    )
    if check.returncode == 0:
        return base, remote_archive
    remote.run(
        "mkdir -p /home/glmrunner/dflash-component/packets",
        "packet-parent",
        cap=30,
    )
    temporary = f"{remote_archive}.part"
    remote.put(archive, temporary, "packet-transfer")
    remote.run(
        f"set -e; test \"$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)\" = {shlex.quote(digest)}; "
        f"rm -rf {shlex.quote(base + '.part')}; mkdir -p {shlex.quote(base + '.part')}; "
        f"tar -xf {shlex.quote(temporary)} -C {shlex.quote(base + '.part')}; "
        f"test -f {shlex.quote(base + '.part/PACKET_MANIFEST.json')}; "
        f"test ! -e {shlex.quote(base)}; mv {shlex.quote(base + '.part')} {shlex.quote(base)}; "
        f"mv {shlex.quote(temporary)} {shlex.quote(remote_archive)}",
        "packet-finalize",
        cap=180,
    )
    return base, remote_archive


def package_and_retrieve(
    remote: Remote,
    remote_run: str,
    artifact_root: pathlib.Path,
    generation: int,
) -> pathlib.Path:
    archive_name = f"compact-{generation}.tar.gz"
    remote_archive = f"{remote_run}/{archive_name}"
    remote.run(
        f"set -e; cd {shlex.quote(remote_run)}; "
        f"tar --exclude=immutable --exclude={shlex.quote(archive_name)} "
        f"--exclude={shlex.quote(archive_name + '.sha256')} "
        f"-czf {shlex.quote(archive_name + '.part')} .; "
        f"mv {shlex.quote(archive_name + '.part')} {shlex.quote(archive_name)}; "
        f"sha256sum {shlex.quote(archive_name)} > {shlex.quote(archive_name + '.sha256')}",
        f"package-{generation}",
        cap=180,
    )
    local_archive = artifact_root / archive_name
    sidecar = artifact_root / f"{archive_name}.sha256"
    remote.get(remote_archive, local_archive, f"retrieve-{generation}")
    remote.get(
        f"{remote_archive}.sha256", sidecar, f"retrieve-hash-{generation}"
    )
    expected = sidecar.read_text().split()[0]
    if sha256(local_archive) != expected:
        raise Boundary("remote_retrieval_boundary", "compact_archive_digest")
    destination = artifact_root / f"snapshot-{expected}"
    if not destination.exists():
        destination.mkdir()
        with tarfile.open(local_archive, "r:gz") as bundle:
            bundle.extractall(destination, filter="data")
    return destination


def claim_exposure(binding: dict[str, Any]) -> tuple[float, float]:
    attribution_start = parse_time(binding["attribution_start_utc"])
    seconds = max(0.0, (utc_now() - attribution_start).total_seconds())
    prior = float(binding.get("prior_actual_spend_usd", 0.0))
    spend = prior + seconds * RATE_USD_PER_HOUR / 3600
    return seconds, spend


def update_status(
    *,
    status: str,
    decision: str,
    summary: str,
    actual_spend_usd: float,
    terminal_artifact: str | None,
) -> None:
    value = load(PROJECT / "STATUS.json")
    value.update(
        {
            "status": status,
            "decision": decision,
            "summary": summary,
            "actual_spend_usd": actual_spend_usd,
            "active_session": None,
            "claim_allowed": False,
        }
    )
    if terminal_artifact is not None:
        value["terminal_artifact"] = terminal_artifact
    atomic(PROJECT / "STATUS.json", value)


def release(
    binding: dict[str, Any],
    artifact_root: pathlib.Path,
    *,
    condition: str,
    summary: str,
    state: str,
) -> None:
    seconds, spend = claim_exposure(binding)
    contents = {
        "schema_version": 1,
        "project": PROJECT_NAME,
        "role": "exact_target_dflash_component_complete",
        "state": state,
        "model": "google/gemma-4-31B-it@b9ea41a2887d8607f594846523f94c6cc75ac8a4",
        "draft": "z-lab/gemma-4-31B-it-DFlash@eabd648301ce28583cc14757912e5e0f84e152e1",
        "runtime": "SGLang f63458b5 source packet; exact H200 identity.",
        "checkpoint": (
            "Exact target manifest 6202e8f8... retained at "
            f"{binding['remote_target_path']} and as a same-inode project view."
        ),
        "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        "server_state": "All sequential arm containers stopped; no server retained.",
        "caches": "Preserve image, target, exact draft, source, and compilation caches.",
        "scientific_terminal": summary,
        "artifacts": str(artifact_root),
        "summary": summary,
        "claim_seconds": seconds,
        "actual_spend_usd": spend,
    }
    contents_path = artifact_root / "RELEASE_CONTENTS.json"
    atomic(contents_path, contents)
    result = pool(
        "release",
        "--project",
        PROJECT_NAME,
        "--bench",
        binding["bench_id"],
        "--expected-claimed-at",
        binding["claimed_at"],
        "--condition",
        condition,
        "--contents",
        str(contents_path),
        check=False,
    )
    atomic(
        artifact_root / "RELEASE_EVIDENCE.json",
        {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "condition": condition,
            "claim_seconds": seconds,
            "actual_spend_usd": spend,
        },
    )
    if result.returncode:
        raise Boundary("release_boundary", result.stderr[-1600:], False)


def validate_scientific_terminal(snapshot: pathlib.Path) -> dict[str, Any]:
    remote = load(snapshot / "REMOTE_TERMINAL.json")
    if remote.get("scientific_terminal") is not True:
        raise Boundary("terminal_adoption_boundary", "remote_not_scientific")
    component = load(snapshot / "COMPONENT_TERMINAL.json")
    required = {
        "ar": {"target_decode"},
        "dflash": {"draft", "target_verify", "acceptance", "kv_commit"},
        "ngram": {"ngram_proposal", "target_verify", "acceptance", "kv_commit"},
    }
    if not component.get("evidence_complete"):
        raise Boundary("terminal_adoption_boundary", "evidence_incomplete")
    if not all(component["science_consumed"].get(arm) for arm in required):
        raise Boundary("terminal_adoption_boundary", "arm_consumption_ledger")
    for arm, phases in required.items():
        present = set(component["component"][arm]["phase_interval_counts"])
        if not phases.issubset(present):
            raise Boundary("terminal_adoption_boundary", f"phases:{arm}")
    correctness = component["correctness"]
    if correctness.get("request_pool_ownership_mapping_pass") is not True:
        raise Boundary(
            "terminal_adoption_boundary",
            "correctness:request_pool_ownership_mapping_pass",
        )
    for key in (
        "greedy_output_token_exact_across_ar_dflash_ngram",
        "semantic_pass",
    ):
        if not isinstance(correctness.get(key), bool):
            raise Boundary("terminal_adoption_boundary", f"missing_boolean:{key}")
    if component["historical_request_25"]["replayed"]:
        raise Boundary("terminal_adoption_boundary", "historical_request_25_replayed")
    return component


def repair_wait(
    artifact_root: pathlib.Path,
    diagnostic: pathlib.Path,
    retry_scope: str,
    deadline: datetime.datetime,
    repair_id: str,
) -> dict[str, Any] | None:
    probe = subprocess.run(
        [
            str(REPAIR_TOOL),
            "status",
            "--root",
            str(artifact_root),
            "--repair-id",
            repair_id,
        ],
        text=True,
        capture_output=True,
        timeout=30,
    )
    try:
        probed = json.loads(probe.stdout) if probe.stdout else {}
    except json.JSONDecodeError as error:
        raise Boundary("repair_handshake_boundary", "malformed_status") from error
    state = probed.get("state")
    if state in ("requested", "repair_terminal"):
        status = probed
    elif state not in ("absent", "waiting"):
        raise Boundary("repair_handshake_boundary", f"unexpected_status:{state}")
    else:
        command = [
            str(REPAIR_TOOL), "ready", "--root", str(artifact_root),
            "--repair-id", repair_id, "--deadline", iso(deadline),
            "--failure-kind", "integration", "--diagnostic", str(diagnostic),
            "--retry-scope", retry_scope,
        ]
        result = subprocess.run(command, text=True, capture_output=True, timeout=30)
        if result.returncode:
            raise Boundary("repair_handshake_boundary", result.stderr[-1600:])
        wait = subprocess.run(
            [str(REPAIR_TOOL), "wait", "--root", str(artifact_root),
             "--repair-id", repair_id, "--deadline", iso(deadline),
             "--poll-seconds", "5"],
            text=True, capture_output=True,
            timeout=max(1, (deadline - utc_now()).total_seconds() + 5),
        )
        if wait.returncode:
            return None
        status = json.loads(wait.stdout)
    state = status.get("state")
    if state == "repair_terminal":
        terminal = status.get("repair_terminal")
        if not isinstance(terminal, dict):
            raise Boundary("repair_terminal_boundary", "malformed_terminal")
        if terminal.get("repair_id") != repair_id:
            raise Boundary("repair_terminal_boundary", "repair_id_mismatch")
        return {"_repair_terminal": terminal}
    if state != "requested":
        return None
    request_path = artifact_root / ".repair-handshakes" / repair_id / "REPAIR_REQUEST.json"
    if pathlib.Path(str(status.get("request_path", ""))).resolve() != request_path.resolve():
        raise Boundary("repair_handshake_boundary", "request_path_mismatch")
    request = load(request_path)
    required = {
        "schema_version": 1,
        "state": "repair_requested",
        "repair_id": repair_id,
        "retry_scope": retry_scope,
        "ready_sha256": status.get("ready_sha256"),
    }
    for key, expected in required.items():
        if request.get(key) != expected:
            raise Boundary("repair_handshake_boundary", f"request_{key}_mismatch")
    digest = sha256(request_path)
    consumed = request_path.with_name(f"REPAIR_REQUEST.{digest}.consumed.json")
    os.replace(request_path, consumed)
    request["_consumed_path"] = str(consumed)
    return request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execution-binding", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    binding = load(args.execution_binding.resolve())
    artifact_root = args.artifact_root.resolve()
    artifact_root.mkdir(parents=True, exist_ok=True)
    deadline = parse_time(binding["owner_deadline_utc"])
    ready = validate_ready(binding)
    bench = validate_claim(binding)
    lifecycle_deadline = parse_time(bench["lifecycle"]["deadline_utc"])
    maximum_spend = float(binding.get("prior_actual_spend_usd", 0.0)) + max(
        0.0,
        (deadline - parse_time(binding["attribution_start_utc"])).total_seconds(),
    ) * RATE_USD_PER_HOUR / 3600
    preflight_error = None
    if deadline > lifecycle_deadline:
        preflight_error = "owner_deadline_exceeds_lifecycle"
    elif maximum_spend > AUTHORIZED_USD:
        preflight_error = f"maximum_spend:{maximum_spend}>{AUTHORIZED_USD}"
    elif deadline <= utc_now():
        preflight_error = "owner_deadline_passed"
    if preflight_error is not None:
        _, spend = claim_exposure(binding)
        update_status(
            status="blocked",
            decision="execution_binding_boundary",
            summary=f"Execution binding rejected after claim: {preflight_error}",
            actual_spend_usd=spend,
            terminal_artifact=None,
        )
        release(
            binding,
            artifact_root,
            condition="maintenance",
            summary=f"Execution binding rejected: {preflight_error}",
            state="maintenance_after_execution_binding_boundary",
        )
        return 76
    remote = Remote(bench, artifact_root, deadline)
    archive = PROJECT / ready["packet"]["archive"]
    packet_digest = ready["packet"]["archive_sha256"]
    remote_run = (
        f"/home/glmrunner/dflash-component/runs/"
        f"{binding['claimed_at'].replace(':', '').replace('.', '')}-{packet_digest[:12]}"
    )
    generation = 0
    retry_scope = "all"
    released = False
    with Heartbeat(artifact_root, binding["claimed_at"]):
        packet_root = None
        while packet_root is None and utc_now() < deadline:
            try:
                packet_root, _ = stage_packet(remote, archive, packet_digest)
                remote.run(
                    f"mkdir -p {shlex.quote(remote_run)}",
                    "remote-run-root",
                    cap=30,
                )
            except Boundary as error:
                diagnostic = artifact_root / f"stage-{generation}.json"
                atomic(
                    diagnostic,
                    {
                        "classification": error.kind,
                        "message": error.message,
                        "recoverable": error.recoverable,
                        "science_started": False,
                    },
                )
                if not error.recoverable:
                    _, spend = claim_exposure(binding)
                    update_status(
                        status="blocked",
                        decision=error.kind,
                        summary=f"Nonrecoverable packet staging boundary: {error}",
                        actual_spend_usd=spend,
                        terminal_artifact=None,
                    )
                    release(
                        binding,
                        artifact_root,
                        condition="maintenance",
                        summary=f"Nonrecoverable packet staging boundary: {error}",
                        state="maintenance_after_packet_staging_boundary",
                    )
                    released = True
                    return 76
                request = repair_wait(
                    artifact_root,
                    diagnostic,
                    "stage",
                    deadline,
                    f"{binding['generation']}-repair-stage-{generation}",
                )
                if request is None:
                    break
                patch = load(pathlib.Path(request["patch_artifact"]))
                if patch.get("retry_scope") != "stage":
                    raise Boundary("repair_scope_boundary", "stage_scope_mismatch")
                archive = pathlib.Path(patch["packet_archive"])
                packet_digest = patch["packet_archive_sha256"]
                if sha256(archive) != packet_digest:
                    raise Boundary("repair_packet_boundary", "stage_packet_digest")
                generation += 1
        if packet_root is None:
            _, spend = claim_exposure(binding)
            update_status(
                status="blocked",
                decision="packet_stage_repair_deadline",
                summary=f"Packet staging retained until deadline; artifacts={artifact_root}",
                actual_spend_usd=spend,
                terminal_artifact=None,
            )
            release(
                binding,
                artifact_root,
                condition="maintenance",
                summary="Packet staging reached the absolute owner deadline.",
                state="maintenance_at_packet_stage_deadline",
            )
            released = True
            return 77
        while utc_now() < deadline:
            worker = remote.run(
                f"python3 {shlex.quote(packet_root + '/dflash_component_worker.py')} "
                f"--packet-root {shlex.quote(packet_root)} "
                f"--remote-root {shlex.quote(remote_run)} "
                f"--target-source {shlex.quote(binding['remote_target_path'])} "
                f"--deadline-epoch {deadline.timestamp()} "
                f"--generation {shlex.quote(binding['generation'])} "
                f"--retry-scope {shlex.quote(retry_scope)}",
                f"worker-{generation}",
                cap=max(60, int((deadline - utc_now()).total_seconds() - 120)),
                check=False,
            )
            try:
                snapshot = package_and_retrieve(
                    remote, remote_run, artifact_root, generation
                )
            except Boundary as error:
                diagnostic = artifact_root / f"retrieval-{generation}.json"
                atomic(
                    diagnostic,
                    {
                        "classification": error.kind,
                        "message": error.message,
                        "worker_returncode": worker.returncode,
                        "retry_scope": "retrieve",
                    },
                )
                request = repair_wait(
                    artifact_root,
                    diagnostic,
                    "retrieve",
                    deadline,
                    f"{binding['generation']}-repair-{generation}",
                )
                if request is None:
                    break
                generation += 1
                continue

            if (snapshot / "REMOTE_TERMINAL.json").is_file():
                try:
                    component = validate_scientific_terminal(snapshot)
                except Boundary as error:
                    diagnostic = artifact_root / f"adoption-{generation}.json"
                    atomic(
                        diagnostic,
                        {
                            "classification": error.kind,
                            "message": error.message,
                            "remote_terminal": str(
                                snapshot / "REMOTE_TERMINAL.json"
                            ),
                            "retry_scope": "summarize",
                        },
                    )
                    request = repair_wait(
                        artifact_root,
                        diagnostic,
                        "summarize",
                        deadline,
                        f"{binding['generation']}-repair-adoption-{generation}",
                    )
                    if request is None:
                        break
                    patch = load(pathlib.Path(request["patch_artifact"]))
                    if patch.get("retry_scope") != "summarize":
                        raise Boundary(
                            "repair_scope_boundary", "adoption_scope_mismatch"
                        )
                    replacement = pathlib.Path(patch["packet_archive"])
                    if sha256(replacement) != patch["packet_archive_sha256"]:
                        raise Boundary(
                            "repair_packet_boundary", "adoption_packet_digest"
                        )
                    packet_root, _ = stage_packet(
                        remote, replacement, patch["packet_archive_sha256"]
                    )
                    generation += 1
                    retry_scope = "summarize"
                    continue
                final_name = "DFLASH_H200_COMPONENT_TERMINAL.json"
                final_path = PROJECT / final_name
                atomic(final_path, component)
                _, spend = claim_exposure(binding)
                if spend > AUTHORIZED_USD:
                    raise Boundary("spend_boundary", f"{spend}>{AUTHORIZED_USD}", False)
                summary = (
                    f"{component['classification']}; exact AR/DFLASH/NGRAM c32 "
                    "component and semantic ledgers complete."
                )
                update_status(
                    status="completed",
                    decision=component["classification"],
                    summary=summary,
                    actual_spend_usd=spend,
                    terminal_artifact=final_name,
                )
                release(
                    binding,
                    artifact_root,
                    condition="ready",
                    summary=summary,
                    state="available_quiescent_after_dflash_component",
                )
                released = True
                return 0

            attempt = (
                load(snapshot / "REMOTE_ATTEMPT.json")
                if (snapshot / "REMOTE_ATTEMPT.json").is_file()
                else {
                    "classification": "unknown_remote_attempt",
                    "recoverable": True,
                }
            )
            if not attempt.get("recoverable", True):
                _, spend = claim_exposure(binding)
                update_status(
                    status="blocked",
                    decision=attempt["classification"],
                    summary=f"Nonrecoverable exact component boundary: {attempt}",
                    actual_spend_usd=spend,
                    terminal_artifact=None,
                )
                release(
                    binding,
                    artifact_root,
                    condition="maintenance",
                    summary=f"Nonrecoverable exact component boundary: {attempt}",
                    state="maintenance_after_nonrecoverable_component_boundary",
                )
                released = True
                return 76

            classification = str(attempt.get("classification"))
            science = attempt.get("science_started", {})
            if classification == "consumer_integration_defect":
                retry_scope = "summarize"
            elif not any(science.values()):
                retry_scope = retry_scope if retry_scope != "retrieve" else "all"
            else:
                retry_scope = "summarize"
            diagnostic = snapshot / "REMOTE_ATTEMPT.json"
            request = repair_wait(
                artifact_root,
                diagnostic,
                retry_scope,
                deadline,
                f"{binding['generation']}-repair-{generation}",
            )
            if request is None:
                break
            patch_path = pathlib.Path(request["patch_artifact"])
            patch = load(patch_path)
            if patch.get("retry_scope") != retry_scope:
                raise Boundary("repair_scope_boundary", "scope_mismatch")
            replacement = pathlib.Path(patch["packet_archive"])
            if sha256(replacement) != patch["packet_archive_sha256"]:
                raise Boundary("repair_packet_boundary", "packet_digest")
            packet_root, _ = stage_packet(
                remote, replacement, patch["packet_archive_sha256"]
            )
            generation += 1

        _, spend = claim_exposure(binding)
        update_status(
            status="blocked",
            decision="owner_deadline_repair_handoff",
            summary=f"Exact component retained until absolute deadline; artifacts={artifact_root}",
            actual_spend_usd=spend,
            terminal_artifact=None,
        )
        release(
            binding,
            artifact_root,
            condition="maintenance",
            summary="Exact component reached its absolute owner deadline with no adoptable terminal.",
            state="maintenance_at_absolute_component_deadline",
        )
        released = True
        return 77
    if not released:
        raise Boundary("owner_lifecycle_boundary", "owner_exited_without_release", False)
    return 78


if __name__ == "__main__":
    raise SystemExit(main())
