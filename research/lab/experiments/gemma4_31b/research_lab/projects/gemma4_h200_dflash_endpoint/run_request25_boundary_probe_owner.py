#!/usr/bin/env python3
"""Bounded one-shot request-25 probe owner."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import threading

PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
POOL_ENV = {**os.environ, "PYTHONPATH": "/root/workspace/research/factory/src"}
POOL = ["python3", "-m", "grad_research.gpu_pool", "--lab", str(LAB)]
BENCH = "h200-dflash-adapter-e00vyqp7gxsr34wrtz"
HOST = "glmrunner@89.169.109.132"
KEY = pathlib.Path("/root/.config/nebius/glm-campaign/ssh_ed25519")
KNOWN = pathlib.Path("/root/.config/nebius/glm-campaign/known_hosts")
HOURLY_USD = 2.45
DEADLINE = datetime.datetime.fromisoformat("2026-07-26T01:47:00+00:00")
PACKET_ID = "4ae9a81bfe3cfcc45a5302662be380e70c2753ef336547445b85aa7ed28f7f4b"
ARCHIVE_SHA256 = "25d8a3cb20806a11560b372a238b8630c64d8035f51c2eb989a10b2070b438a8"
PACKET = PROJECT / "artifacts/request25-boundary-probe-preparation-20260726/packet" / PACKET_ID
ARCHIVE = PROJECT / "artifacts/request25-boundary-probe-preparation-20260726" / f"{PACKET_ID}.tar"
PARSER_SOURCE_SHA256 = "16fbbf3a8b9bc2a8e3925cd092bd0de128d1c8904fdf554e5d3c16b632a64f26"


def now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def iso(value: datetime.datetime | None = None) -> str:
    return (value or now()).isoformat().replace("+00:00", "Z")


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)


def run(
    command: list[str],
    timeout: float,
    *,
    check: bool = False,
    **kwargs,
) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, timeout=max(1, timeout), check=check, **kwargs
    )


def ssh() -> list[str]:
    return [
        "ssh", "-i", str(KEY), "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}",
        "-o", "ConnectTimeout=20", HOST,
    ]


def scp() -> list[str]:
    return [
        "scp", "-i", str(KEY), "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={KNOWN}",
        "-o", "ConnectTimeout=20",
    ]


def left(cap: float) -> float:
    return min(cap, max(1, (DEADLINE - now()).total_seconds()))


class Heartbeat:
    def __init__(self, path: pathlib.Path):
        self.path = path
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.loop, daemon=True)

    def loop(self) -> None:
        while not self.stop.wait(30):
            with self.path.open("ab") as handle:
                run(
                    POOL + ["heartbeat", "--project", PROJECT.name],
                    20,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    env=POOL_ENV,
                )

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)


def update_spend(claimed_at: datetime.datetime, prior: float) -> float:
    spend = prior + (now() - claimed_at).total_seconds() * HOURLY_USD / 3600
    status_path = PROJECT / "STATUS.json"
    status = json.loads(status_path.read_text())
    status["actual_spend_usd"] = spend
    status["continuation_remaining_spend_usd"] = max(
        0.0, float(status["authorized_spend_usd"]) - spend
    )
    atomic(status_path, status)
    return spend


def release(output: pathlib.Path, terminal: pathlib.Path) -> None:
    run(
        POOL + [
            "release", "--project", PROJECT.name, "--condition", "maintenance",
            "--contents", json.dumps({
                "summary": "Request-25 boundary probe terminalized; experiment processes stopped.",
                "terminal": str(terminal),
                "artifact_root": str(output),
                "packet_identity_sha256": PACKET_ID,
            }),
        ],
        30,
        stdout=(output / "release.stdout").open("wb"),
        stderr=(output / "release.stderr").open("wb"),
        env=POOL_ENV,
    )


def classify(record: dict) -> str:
    raw = record.get("raw_first_position_top1")
    post = record.get("post_adjustment_first_position_top1")
    if raw is None or post is None or not record.get("pre_forward_kv_sha256"):
        return "probe_inconclusive"
    if raw == 3496 and post != 3496:
        return "logit_adjustment_divergence"
    if raw != 3496:
        return "target_forward_divergence"
    if post == 3496:
        return "boundary_matches"
    return "probe_inconclusive"


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    status = json.loads((PROJECT / "STATUS.json").read_text())
    prior = float(status["actual_spend_usd"])
    if now() >= DEADLINE:
        atomic(output / "OWNER_TERMINAL.json", {"classification": "absolute_deadline_elapsed"})
        return 75
    if prior + 0.82 > float(status["authorized_spend_usd"]):
        atomic(output / "OWNER_TERMINAL.json", {"classification": "spend_reservation_insufficient"})
        return 76
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        atomic(output / "OWNER_TERMINAL.json", {"classification": "packet_archive_digest_mismatch"})
        return 77
    parser_gate = output / "PARSER_GATE.json"
    parser_source = PROJECT / "remote_request25_boundary_probe.sh"
    if hashlib.sha256(parser_source.read_bytes()).hexdigest() != PARSER_SOURCE_SHA256:
        atomic(output / "OWNER_TERMINAL.json", {"classification": "parser_source_digest_mismatch"})
        return 77
    gate = run(
        [
            "python3", str(PROJECT / "validate_request25_source_identity_parser.py"),
            "--source", str(parser_source),
            "--binding", str(PACKET / "SOURCE_BINDING.json"),
            "--positive", str(PROJECT / "artifacts/request25-boundary-owner-20260726T0112Z/retrieved/installed-source.sha256"),
            "--output", str(parser_gate),
        ],
        20,
        stdout=(output / "parser-gate.stdout").open("wb"),
        stderr=(output / "parser-gate.stderr").open("wb"),
    )
    if gate.returncode or not parser_gate.is_file():
        atomic(output / "OWNER_TERMINAL.json", {"classification": "parser_gate_failed", "exit_code": gate.returncode})
        return 77
    for path in (KEY, KNOWN, PACKET, PROJECT / "remote_request25_boundary_probe.sh", PROJECT / "request25_single_request.py"):
        if not path.exists():
            atomic(output / "OWNER_TERMINAL.json", {"classification": "local_input_missing", "path": str(path)})
            return 78

    claim = run(
        POOL + ["claim", "--project", PROJECT.name, "--bench", BENCH],
        30,
        stdout=(output / "claim.stdout").open("wb"),
        stderr=(output / "claim.stderr").open("wb"),
        env=POOL_ENV,
    )
    if claim.returncode:
        atomic(output / "OWNER_TERMINAL.json", {"classification": "atomic_claim_unavailable", "exit_code": claim.returncode})
        return 79
    claimed_at = now()
    remote = f"/home/glmrunner/gemma4-dflash/request25-boundary/{output.name}"
    terminal = output / "DFLASH_REQUEST25_BOUNDARY_PROBE_H200_RETRY2_TERMINAL.json"
    with Heartbeat(output / "heartbeat.log"):
        worker_rc = 1
        retrieve_rc = 1
        try:
            stage_command = (
                f"mkdir -p '{remote}/packet' '{remote}/run'; "
                f"tar -xf '{remote}/packet.tar' -C '{remote}/packet'"
            )
            run(ssh() + [f"mkdir -p '{remote}'"], left(30), check=True)
            run(scp() + [str(ARCHIVE), f"{HOST}:{remote}/packet.tar"], left(60), check=True)
            run(scp() + [
                str(PROJECT / "remote_request25_boundary_probe.sh"),
                str(PROJECT / "request25_single_request.py"),
                f"{HOST}:{remote}/",
            ], left(60), check=True)
            run(
                ssh() + [
                    f"test \"$(sha256sum '{remote}/packet.tar' | cut -d' ' -f1)\" = '{ARCHIVE_SHA256}' && {stage_command}"
                ],
                left(45),
                check=True,
            )
            atomic(output / "STAGED.json", {
                "packet_identity_sha256": PACKET_ID,
                "archive_sha256": ARCHIVE_SHA256,
                "remote": remote,
                "staged_at_utc": iso(),
            })
            worker = run(
                ssh() + [
                    f"bash '{remote}/remote_request25_boundary_probe.sh' "
                    f"'{remote}/packet' '{remote}/run' '{remote}/request25_single_request.py'"
                ],
                left(600),
                stdout=(output / "remote.stdout").open("wb"),
                stderr=(output / "remote.stderr").open("wb"),
            )
            worker_rc = worker.returncode
        except Exception as exc:
            (output / "owner.error").write_text(f"{type(exc).__name__}: {exc}\n")
        finally:
            retrieved = output / "retrieved"
            retrieved.mkdir(exist_ok=True)
            result = run(
                scp() + ["-r", f"{HOST}:{remote}/run/.", str(retrieved)],
                left(90),
                stdout=(output / "retrieve.stdout").open("wb"),
                stderr=(output / "retrieve.stderr").open("wb"),
            )
            retrieve_rc = result.returncode
            spend = update_spend(claimed_at, prior)
            record_path = retrieved / "request25-boundary.json"
            remote_terminal_path = retrieved / "REMOTE_TERMINAL.json"
            record = json.loads(record_path.read_text()) if record_path.is_file() else {}
            remote_terminal = json.loads(remote_terminal_path.read_text()) if remote_terminal_path.is_file() else {}
            if worker_rc == 0 and retrieve_rc == 0 and record:
                classification = classify(record)
            elif retrieve_rc == 0 and remote_terminal:
                classification = "infrastructure_terminal"
            else:
                classification = "infrastructure_terminal"
            value = {
                "schema_version": 1,
                "classification": classification,
                "packet_identity_sha256": PACKET_ID,
                "archive_sha256": ARCHIVE_SHA256,
                "source_binding_sha256": "cc49aa4192e737c90ddd5871c59efd4fc854c6a0ca094c557a0e78545bdb8c52",
                "parser_source_sha256": PARSER_SOURCE_SHA256,
                "parser_gate": json.loads(parser_gate.read_text()),
                "request_index": 25,
                "request_submission_count": 1 if (retrieved / "REQUEST25_SCIENCE_STARTED.json").is_file() else 0,
                "endpoint_replayed": False,
                "in_run_repair": False,
                "worker_exit_code": worker_rc,
                "retrieve_exit_code": retrieve_rc,
                "remote_terminal": remote_terminal,
                "boundary_record": record or None,
                "actual_spend_usd": spend,
                "incremental_spend_usd": spend - prior,
                "claim_seconds": (now() - claimed_at).total_seconds(),
                "artifact_root": str(output),
                "recorded_at_utc": iso(),
            }
            atomic(terminal, value)
            shutil.copy2(terminal, PROJECT / terminal.name)
            release(output, terminal)
    return 0 if value["classification"] not in {"infrastructure_terminal", "probe_inconclusive"} else 80


if __name__ == "__main__":
    raise SystemExit(main())
