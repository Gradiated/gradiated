#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime
import json
import os
import pathlib
import subprocess
import sys
import time


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bench", required=True)
    parser.add_argument("--attention-pair", action="store_true")
    args = parser.parse_args()
    inventory = json.loads((LAB / "runtime/gpus.json").read_text())
    benches = inventory["benches"]
    bench = benches[args.bench] if isinstance(benches, dict) else next(row for row in benches if row["id"] == args.bench)
    if bench["status"] != "available" or bench["accelerator"] != "nvidia-h200-sxm":
        raise RuntimeError("typed_pool_boundary:requested_h200_not_available")
    now = datetime.datetime.now(datetime.timezone.utc)
    stamp = now.strftime("%Y%m%dt%H%Mz")
    artifact_root = PROJECT / "artifacts" / (f"attention-pair-{stamp}" if args.attention_pair else f"residual-profile-{stamp}")
    deadline_epoch = int(time.time()) + (75 if args.attention_pair else 150) * 60
    if args.attention_pair:
        release_deadline = datetime.datetime(2026, 7, 20, 11, 10, tzinfo=datetime.timezone.utc)
        deadline_epoch = min(deadline_epoch, int(release_deadline.timestamp()))
    deadline = datetime.datetime.fromtimestamp(deadline_epoch, datetime.timezone.utc).isoformat().replace("+00:00", "Z")
    unit = f"gemma4-h200-v0513-fp8-qkv-residual-{stamp}.service"
    command = [
        "systemd-run",
        "--user",
        f"--unit={unit.removesuffix('.service')}",
        "--property=Restart=no",
        "--property=TimeoutStopSec=120",
        "--collect",
        sys.executable,
        str(PROJECT / "run_profile_intervention_owner.py"),
        "--bench",
        args.bench,
        "--artifact-root",
        str(artifact_root),
        "--absolute-deadline-epoch",
        str(deadline_epoch),
    ]
    if args.attention_pair:
        command.extend(
            [
                "--pair-only",
                "--intervention-request",
                str(PROJECT / "ATTENTION_INTERVENTION_REQUEST.json"),
            ]
        )
    launched = subprocess.run(command, capture_output=True, text=True, check=False)
    if launched.returncode:
        raise RuntimeError(f"durable_owner_launch_failed:{launched.stderr[-1000:]}")
    time.sleep(1)
    shown = subprocess.run(
        ["systemctl", "--user", "show", unit, "--property=MainPID", "--value"],
        capture_output=True,
        text=True,
        check=False,
    )
    pid = int(shown.stdout.strip() or 0)
    status_path = PROJECT / "STATUS.json"
    status = json.loads(status_path.read_text())
    status["active_session"] = {
        "unit": unit,
        "unit_manager": "user",
        "pid": pid,
        "bench": args.bench,
        "deadline_utc": deadline,
        "artifact_root": str(artifact_root),
        "expected_terminal": str(artifact_root / "TERMINAL.json"),
        "phase": "attention_pair_claim_and_reconcile" if args.attention_pair else "claim_and_cold_stage",
    }
    atomic(status_path, status)
    print(json.dumps(status["active_session"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
