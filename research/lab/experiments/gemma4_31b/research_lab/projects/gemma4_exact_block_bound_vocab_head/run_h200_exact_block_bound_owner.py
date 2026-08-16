#!/usr/bin/env python3
"""Durable retained-claim owner for the exact block-bound H200 discriminator."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import threading
import time
from typing import Any

PROJECT = Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
FACTORY = PROJECT.parents[5] / "factory"
POOL = [sys.executable, "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
REPAIR = FACTORY / "tools" / "repair-handshake"
PROJECT_ID = "gemma4_exact_block_bound_vocab_head"
BENCH_ID = "h200-causal-head-e00b9qw8d6qd7wrjj1"
ADMISSION = PROJECT / "DIRECTOR_EXACT_BLOCK_BOUND_VOCAB_HEAD_ADMISSION_20260727T0055Z.json"
SCORER = PROJECT / "exact_block_bound_vocab_head.py"
INPUTS = PROJECT / "inputs"
EXPECTED = {
    "hidden_states.pt": "ce7095836aea47701fc34ebacb2f0754c9066066062500a05fbd6136c59b4d54",
    "EXACT_CAPTURE_TERMINAL.json": "fc7297d3bf51e9118e0cf5bde4eec7c2bd22dc2d07a6608c3b19f8b55d55a9bc",
}
PINNED_IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(16 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise RuntimeError(f"json_object_required:{path}")
    return value


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    temporary.replace(path)


def utc(epoch: float | None = None) -> str:
    epoch = time.time() if epoch is None else epoch
    return (
        dt.datetime.fromtimestamp(epoch, dt.timezone.utc)
        .isoformat()
        .replace("+00:00", "Z")
    )


def run(
    command: list[str], timeout: float, evidence: Path, stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        input=stdin,
        text=True,
        capture_output=True,
        timeout=max(1, timeout),
        check=False,
    )
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text(result.stdout)
    evidence.with_suffix(evidence.suffix + ".stderr").write_text(result.stderr)
    return result


def bench() -> dict[str, Any]:
    inventory = load(LAB / "runtime" / "gpus.json")
    benches = inventory.get("benches", [])
    if isinstance(benches, dict):
        benches = list(benches.values())
    for value in benches:
        if value.get("id") == BENCH_ID:
            return value
    raise RuntimeError("bound_bench_missing")


def binding(path: Path) -> dict[str, Any]:
    value = load(path)
    gpu = value.get("gpu_authority", {})
    bound_bench = value.get("bench", {})
    claim_allowed = value.get("gpu_claim_allowed", gpu.get("claim_allowed"))
    if claim_allowed is None:
        claim_allowed = (
            value.get("decision") == "open_warm_h200_implementation_and_component_claim"
        )
    bench_id = bound_bench.get("id", gpu.get("bench_id"))
    admission_digest = value.get("admission", {}).get(
        "sha256", value.get("admission_sha256")
    )
    reservation = value.get("reservation", value.get("spend_reservation", {}))
    if not (
        value.get("project") == PROJECT_ID
        and claim_allowed is True
        and bench_id == BENCH_ID
        and admission_digest == sha256_file(ADMISSION)
        and float(reservation.get("authorized_usd", 0)) == 2.0
    ):
        raise RuntimeError("later_exact_director_claim_binding_required")
    return value


def ssh_parts(value: dict[str, Any]) -> tuple[list[str], str, str]:
    resource = value.get("resource", {})
    host = resource.get("public_ipv4")
    user = resource.get("ssh_user")
    known_hosts = resource.get("known_hosts_namespace")
    identity = Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
    if not (
        all(isinstance(item, str) and item for item in (host, user, known_hosts))
        and identity.is_file()
        and Path(str(known_hosts)).is_file()
    ):
        raise RuntimeError("established_nebius_ssh_identity_missing")
    return (
        [
            "ssh",
            "-i",
            str(identity),
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=yes",
            "-o",
            f"UserKnownHostsFile={known_hosts}",
        ],
        str(user),
        str(host),
    )


def remote(
    ssh: list[str],
    user: str,
    host: str,
    shell: str,
    timeout: float,
    evidence: Path,
) -> subprocess.CompletedProcess[str]:
    return run([*ssh, f"{user}@{host}", shell], timeout, evidence)


def copy_to(
    ssh: list[str],
    user: str,
    host: str,
    source: Path,
    target: str,
    timeout: float,
    evidence: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        ["scp", *ssh[1:], str(source), f"{user}@{host}:{target}"],
        timeout,
        evidence,
    )


def copy_from(
    ssh: list[str],
    user: str,
    host: str,
    source: str,
    target: Path,
    timeout: float,
    evidence: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        ["scp", *ssh[1:], f"{user}@{host}:{source}", str(target)],
        timeout,
        evidence,
    )


def stage_file(
    ssh: list[str],
    user: str,
    host: str,
    source: Path,
    target: str,
    evidence: Path,
    deadline: float,
) -> None:
    digest = sha256_file(source)
    matched = (
        f"test -f {shlex.quote(target)} && "
        f"test \"$(stat -c %s {shlex.quote(target)})\" = {source.stat().st_size} && "
        f"test \"$(sha256sum {shlex.quote(target)} | cut -d' ' -f1)\" = {digest}"
    )
    if (
        remote(
            ssh,
            user,
            host,
            matched,
            min(120, deadline - time.time()),
            evidence.with_name(evidence.name + ".match"),
        ).returncode
        == 0
    ):
        return
    temporary = f"{target}.{digest}.part"
    if copy_to(
        ssh,
        user,
        host,
        source,
        temporary,
        min(300, deadline - time.time()),
        evidence.with_name(evidence.name + ".copy"),
    ).returncode:
        raise RuntimeError(f"immutable_stage_copy_failed:{source.name}")
    finalize = (
        f"test \"$(stat -c %s {shlex.quote(temporary)})\" = {source.stat().st_size} && "
        f"test \"$(sha256sum {shlex.quote(temporary)} | cut -d' ' -f1)\" = {digest} && "
        f"chmod 0444 {shlex.quote(temporary)} && mv {shlex.quote(temporary)} {shlex.quote(target)}"
    )
    if remote(
        ssh,
        user,
        host,
        finalize,
        min(180, deadline - time.time()),
        evidence.with_name(evidence.name + ".finalize"),
    ).returncode:
        raise RuntimeError(f"immutable_stage_finalize_failed:{source.name}")


def validate_terminal(path: Path, owner_hash: str, scorer_hash: str) -> dict[str, Any]:
    terminal = load(path)
    source_hashes = terminal.get("source_hashes", {})
    if not (
        terminal.get("classification") == "exact_block_bound_vocab_head_terminal"
        and source_hashes.get("owner") == owner_hash
        and source_hashes.get("scorer") == scorer_hash
        and terminal.get("execution", {}).get("cuda") is True
        and terminal.get("execution", {}).get("submission_count") == 1
        and terminal.get("complete_output_consumption", {}).get("top1_rows_consumed")
        == 1536
    ):
        raise RuntimeError("retrieved_terminal_contract_invalid")
    return terminal


def execute_attempt(
    value: dict[str, Any],
    output: Path,
    generation: int,
    deadline: float,
    claimed_at: float,
) -> dict[str, Any]:
    current = bench()
    ssh, user, host = ssh_parts(current)
    owner_hash = sha256_file(Path(__file__).resolve())
    scorer_hash = sha256_file(SCORER)
    remote_root = (
        f"/home/glmrunner/exact-block-bound-vocab-head/"
        f"{sha256_file(ADMISSION)[:16]}/attempt-{generation}"
    )
    remote_input = remote_root + "/input"
    remote_output = remote_root + "/output"
    if remote(
        ssh,
        user,
        host,
        f"mkdir -p {shlex.quote(remote_input)} {shlex.quote(remote_output)}",
        min(60, deadline - time.time()),
        output / f"attempt-{generation}.remote-prepare",
    ).returncode:
        raise RuntimeError("remote_attempt_root_prepare_failed")
    sources = [
        (SCORER, SCORER.name),
        (ADMISSION, ADMISSION.name),
        (INPUTS / "hidden_states.pt", "hidden_states.pt"),
        (INPUTS / "EXACT_CAPTURE_TERMINAL.json", "EXACT_CAPTURE_TERMINAL.json"),
    ]
    for source, name in sources:
        stage_file(
            ssh,
            user,
            host,
            source,
            remote_input + "/" + name,
            output / f"attempt-{generation}.stage-{name}",
            deadline,
        )
    checkpoint = value.get("bench", {}).get(
        "resident_checkpoint",
        current.get("contents", {})
        .get("resident_checkpoint", {})
        .get("absolute_remote_path"),
    )
    image = value.get("bench", {}).get("image")
    if image is None:
        resident_image = str(current.get("contents", {}).get("image", ""))
        image = PINNED_IMAGE if "6113665a292b50f" in resident_image else None
    if not isinstance(checkpoint, str) or not isinstance(image, str):
        raise RuntimeError("binding_missing_resident_checkpoint_or_image")
    command = [
        "sudo",
        "-n",
        "docker",
        "run",
        "--rm",
        "--gpus",
        "all",
        "--ipc=host",
        "-v",
        f"{remote_input}:/work/input:ro",
        "-v",
        f"{remote_output}:/work/output",
        "-v",
        f"{checkpoint}:/work/checkpoint:ro",
        image,
        "python3",
        f"/work/input/{SCORER.name}",
        "--weight",
        "/work/checkpoint/model-00001-of-00002.safetensors",
        "--capture",
        "/work/input/hidden_states.pt",
        "--capture-terminal",
        "/work/input/EXACT_CAPTURE_TERMINAL.json",
        "--admission",
        f"/work/input/{ADMISSION.name}",
        "--output",
        "/work/output/EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json",
        "--science-marker",
        "/work/output/science_started.json",
        "--arm-marker-root",
        "/work/output/arm-markers",
        "--owner-sha256",
        owner_hash,
    ]
    atomic_json(
        output / f"attempt-{generation}.launch_attempted.json",
        {
            "launch_attempted": True,
            "candidate_invocation_started": False,
            "command_sha256": hashlib.sha256(
                "\0".join(command).encode()
            ).hexdigest(),
        },
    )
    result = remote(
        ssh,
        user,
        host,
        " ".join(shlex.quote(token) for token in command),
        max(1, deadline - time.time()),
        output / f"attempt-{generation}.worker.stdout",
    )
    evidence_names = (
        "EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json",
        "science_started.json",
        "arm-markers/dense_first_call.json",
        "arm-markers/candidate_first_call.json",
    )
    retrieved: dict[str, str] = {}
    for name in evidence_names:
        local = output / f"attempt-{generation}.{name.replace('/', '-')}"
        copied = copy_from(
            ssh,
            user,
            host,
            remote_output + "/" + name,
            local,
            min(120, deadline - time.time()),
            output / f"attempt-{generation}.retrieve-{name.replace('/', '-')}",
        )
        if copied.returncode == 0:
            retrieved[name] = str(local)
    terminal_path = output / f"attempt-{generation}.EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json"
    if terminal_path.is_file():
        terminal = validate_terminal(terminal_path, owner_hash, scorer_hash)
        claim_seconds = time.time() - claimed_at
        actual_spend = claim_seconds * float(current["hourly_cost_usd"]) / 3600
        terminal["spend"].update(
            {
                "claim_seconds_at_terminal_retrieval": claim_seconds,
                "actual_spend_usd_at_terminal_retrieval": actual_spend,
                "hourly_cost_usd": float(current["hourly_cost_usd"]),
            }
        )
        canonical = output / "EXACT_BLOCK_BOUND_VOCAB_HEAD_TERMINAL.json"
        atomic_json(canonical, terminal)
        return {
            "terminal": terminal,
            "canonical": canonical,
            "worker_exit": result.returncode,
            "retrieved": retrieved,
        }
    raise RuntimeError(
        f"component_terminal_absent:worker_exit={result.returncode}:"
        f"science_started={'science_started.json' in retrieved}:"
        f"dense_started={'arm-markers/dense_first_call.json' in retrieved}:"
        f"candidate_started={'arm-markers/candidate_first_call.json' in retrieved}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--authority", "--claim-authority", dest="claim_authority", type=Path, required=True
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    value = binding(args.claim_authority.resolve())
    for name, digest in EXPECTED.items():
        path = INPUTS / name
        if not path.is_file() or sha256_file(path) != digest:
            raise RuntimeError(f"project_local_immutable_input_mismatch:{name}")
    current = bench()
    lifecycle = dt.datetime.fromisoformat(
        current["lifecycle"]["deadline_utc"].replace("Z", "+00:00")
    ).timestamp()
    binding_deadline = dt.datetime.fromisoformat(
        value.get("release_not_after_utc", current["lifecycle"]["deadline_utc"]).replace(
            "Z", "+00:00"
        )
    ).timestamp()
    deadline = min(time.time() + 15 * 60, lifecycle - 60, binding_deadline - 60)
    if deadline <= time.time() + 120:
        raise RuntimeError("insufficient_bound_lifecycle_for_claim")
    atomic_json(
        output / "OWNER_SOURCE.json",
        {
            "owner_sha256": sha256_file(Path(__file__).resolve()),
            "scorer_sha256": sha256_file(SCORER),
            "admission_sha256": sha256_file(ADMISSION),
            "claim_authority_sha256": sha256_file(args.claim_authority),
            "deadline_utc": utc(deadline),
            "checkpoint_transfer_bytes": 0,
        },
    )
    claimed = run(
        [*POOL, "claim", "--project", PROJECT_ID, "--bench", BENCH_ID],
        30,
        output / "claim.stdout",
    )
    if claimed.returncode:
        raise RuntimeError("atomic_bench_claim_failed")
    claimed_state = bench()["claim"]
    claimed_at_text = claimed_state["claimed_at"]
    claimed_at = dt.datetime.fromisoformat(
        claimed_at_text.replace("Z", "+00:00")
    ).timestamp()
    stop = threading.Event()

    def heartbeat() -> None:
        while not stop.wait(30):
            run(
                [
                    *POOL,
                    "heartbeat",
                    "--project",
                    PROJECT_ID,
                    "--bench",
                    BENCH_ID,
                ],
                25,
                output / f"heartbeat-{time.time_ns()}.stdout",
            )

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    generation = 0
    terminal_result: dict[str, Any] | None = None
    contents_path: Path | None = None
    try:
        while time.time() < deadline:
            try:
                result = execute_attempt(
                    value, output, generation, deadline, claimed_at
                )
                terminal = result["terminal"]
                contents = {
                    "schema_version": 1,
                    "project": PROJECT_ID,
                    "scientific_terminal": terminal["decision"]["classification"],
                    "artifacts": str(output),
                    "checkpoint": "Bench-owned exact checkpoint retained unchanged.",
                    "image": "Pinned SGLang image retained.",
                    "server_state": "No live server or GPU process.",
                    "runtime": (
                        "Exact block-envelope vocabulary-head component completed; "
                        "checkpoint, image, and caches remain resident."
                    ),
                }
                contents_path = output / "RESIDENT_CONTENTS.json"
                atomic_json(contents_path, contents)
                terminal_result = result
                break
            except Exception as error:
                diagnostic = f"{type(error).__name__}:{error}"
                if time.time() >= deadline:
                    break
                repair_id = f"exact-block-bound-repair-{generation}-{time.time_ns()}"
                ready = run(
                    [
                        str(REPAIR),
                        "ready",
                        "--root",
                        str(output),
                        "--repair-id",
                        repair_id,
                        "--deadline",
                        utc(deadline),
                        "--failure-kind",
                        "component_integration_or_retrieval_failure",
                        "--diagnostic",
                        diagnostic,
                        "--retry-scope",
                        "exact_block_bound_component_consumer_only",
                    ],
                    30,
                    output / f"{repair_id}.ready",
                )
                if ready.returncode:
                    raise RuntimeError(
                        f"repair_handshake_creation_failed:{diagnostic}"
                    )
                waited = run(
                    [
                        str(REPAIR),
                        "wait",
                        "--root",
                        str(output),
                        "--repair-id",
                        repair_id,
                        "--poll-seconds",
                        "2",
                    ],
                    max(1, deadline - time.time()),
                    output / f"{repair_id}.wait",
                )
                if waited.returncode:
                    break
                generation += 1

        if terminal_result is not None and contents_path is not None:
            release_generation = 0
            while time.time() < deadline:
                release = run(
                    [
                        *POOL,
                        "release",
                        "--project",
                        PROJECT_ID,
                        "--bench",
                        BENCH_ID,
                        "--expected-claimed-at",
                        claimed_at_text,
                        "--contents",
                        str(contents_path),
                        "--condition",
                        "ready",
                    ],
                    min(45, deadline - time.time()),
                    output / f"release-{release_generation}.stdout",
                )
                if release.returncode == 0:
                    break
                repair_id = (
                    f"exact-block-bound-release-repair-{release_generation}-"
                    f"{time.time_ns()}"
                )
                ready = run(
                    [
                        str(REPAIR),
                        "ready",
                        "--root",
                        str(output),
                        "--repair-id",
                        repair_id,
                        "--deadline",
                        utc(deadline),
                        "--failure-kind",
                        "terminal_adoption_or_release_failure",
                        "--diagnostic",
                        f"gpu_pool_release_exit={release.returncode}",
                        "--retry-scope",
                        "terminal_adoption_and_release_only",
                    ],
                    30,
                    output / f"{repair_id}.ready",
                )
                if ready.returncode:
                    break
                waited = run(
                    [
                        str(REPAIR),
                        "wait",
                        "--root",
                        str(output),
                        "--repair-id",
                        repair_id,
                        "--poll-seconds",
                        "2",
                    ],
                    max(1, deadline - time.time()),
                    output / f"{repair_id}.wait",
                )
                if waited.returncode:
                    break
                release_generation += 1
            if bench().get("claim") is None:
                actual_spend = (
                    (time.time() - claimed_at)
                    * float(current["hourly_cost_usd"])
                    / 3600
                )
                result = terminal_result
                atomic_json(
                    output / "OWNER_TERMINAL.json",
                    {
                        "pass": True,
                        "terminal_sha256": sha256_file(result["canonical"]),
                        "claim_started_at_utc": claimed_at_text,
                        "claim_released_at_utc": utc(),
                        "claim_seconds": time.time() - claimed_at,
                        "actual_spend_usd": actual_spend,
                        "checkpoint_transfer_bytes": 0,
                    },
                )
                return 0
            atomic_json(
                output / "TERMINAL_RELEASE_FAILURE.json",
                {
                    "classification": "valid_terminal_retained_release_failure",
                    "terminal_sha256": sha256_file(terminal_result["canonical"]),
                    "deadline_utc": utc(deadline),
                },
            )
        diagnostic = {
            "classification": "absolute_deadline_repair_handoff",
            "claim_started_at_utc": claimed_at_text,
            "deadline_utc": utc(deadline),
            "science_markers": sorted(
                str(path) for path in output.glob("attempt-*.science_started.json")
            ),
            "candidate_markers": sorted(
                str(path)
                for path in output.glob(
                    "attempt-*.arm-markers-candidate_first_call.json"
                )
            ),
        }
        atomic_json(output / "DEADLINE_TERMINAL.json", diagnostic)
        contents_path = output / "RESIDENT_CONTENTS.json"
        atomic_json(
            contents_path,
            {
                "schema_version": 1,
                "project": PROJECT_ID,
                "scientific_terminal": "unknown_at_absolute_deadline",
                "artifacts": str(output),
                "checkpoint": "Bench-owned exact checkpoint retained unchanged.",
                "image": "Pinned SGLang image retained.",
                "server_state": "No owner-launched persistent server.",
                "runtime": "Compact failure and submission markers retrieved; director disposition required.",
            },
        )
        run(
            [
                *POOL,
                "release",
                "--project",
                PROJECT_ID,
                "--bench",
                BENCH_ID,
                "--expected-claimed-at",
                claimed_at_text,
                "--contents",
                str(contents_path),
                "--condition",
                "maintenance",
            ],
            45,
            output / "deadline-release.stdout",
        )
        return 2
    finally:
        stop.set()
        thread.join(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
