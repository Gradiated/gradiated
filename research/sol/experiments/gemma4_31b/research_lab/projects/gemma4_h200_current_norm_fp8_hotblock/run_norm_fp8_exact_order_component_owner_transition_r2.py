#!/usr/bin/env python3
"""Start R2 standby, fence the exact predecessor, and authorize takeover."""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE / "artifacts/norm-fp8-exact-order-h200-component-20260730t0754z/owner-r2"
TRANSITION = HERE / "DIRECTOR_NORM_FP8_SAME_CLAIM_OWNER_TRANSITION_20260730T0807Z.json"
PREDECESSOR_STATE = HERE / "artifacts/norm-fp8-exact-order-h200-component-20260730t0754z/DETACHED_OWNER.json"
R2_STATE = ROOT / "DETACHED_OWNER_R2.json"
DETACHED = "/root/workspace/research/factory/tools/detached-owner"


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(path.suffix + ".part")
    part.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(part.read_text())
    os.replace(part, path)


def ticks(pid: int) -> int | None:
    try:
        fields = pathlib.Path(f"/proc/{pid}/stat").read_text().split()
        return int(fields[21])
    except FileNotFoundError:
        return None


def main() -> int:
    transition = json.loads(TRANSITION.read_text())
    claim = transition["claim"]
    predecessor = transition["predecessor_owner"]
    deadline = dt.datetime.fromisoformat(claim["effective_claim_deadline_utc"].replace("Z", "+00:00")).timestamp()
    if time.time() >= deadline - 300:
        raise RuntimeError("remaining_window_cannot_fit_execution_and_release")
    retry = R2_STATE.exists()
    prior = json.loads(PREDECESSOR_STATE.read_text())
    if prior.get("pid") != predecessor["pid"] or prior.get("start_ticks") != predecessor["start_ticks"]:
        raise RuntimeError("predecessor_identity_changed")
    root = HERE / transition["predecessor_owner"]["artifact_root"]
    if (root / "TERMINAL.json").exists() or (root / "SCIENCE_STARTED.json").exists():
        raise RuntimeError("terminal_or_science_evidence_appeared")
    if retry:
        failure = json.loads((ROOT / "R2_PROGRESS.json").read_text())
        if failure.get("event") != "r2_failure" or failure.get("diagnostic") != "competing_remote_executor" or ticks(predecessor["pid"]) is not None:
            raise RuntimeError("r2_retry_not_localized_or_predecessor_not_absent")
        if (ROOT / "TAKEOVER.json").exists():
            os.replace(ROOT / "TAKEOVER.json", ROOT / "TAKEOVER.pre_census_fix.json")
        if (ROOT / "R2_STANDBY_READY.json").exists():
            os.replace(ROOT / "R2_STANDBY_READY.json", ROOT / "R2_STANDBY_READY.pre_census_fix.json")
    elif ticks(predecessor["pid"]) != predecessor["start_ticks"]:
        raise RuntimeError("predecessor_identity_changed")
    command = [DETACHED, "start", "--unit-manager", "pid", "--state", str(R2_STATE), "--log", str(ROOT / "OWNER_R2.log"),
               "--cwd", str(HERE), "--ready-file", str(ROOT / "R2_STANDBY_READY.json"), "--stabilize-seconds", "90", "--",
               sys.executable, str(HERE / "run_norm_fp8_exact_order_component_owner_r2.py"), "--transition", str(TRANSITION), "--state-path", str(R2_STATE)]
    started = subprocess.run(command, text=True, capture_output=True, timeout=120)
    if started.returncode:
        raise RuntimeError("r2_standby_failed:" + started.stderr[-1000:] + started.stdout[-1000:])
    standby = json.loads((ROOT / "R2_STANDBY_READY.json").read_text())
    if standby.get("claim_generation") != claim["claimed_at"]:
        raise RuntimeError("r2_standby_claim_mismatch")
    if not retry:
        if ticks(predecessor["pid"]) != predecessor["start_ticks"]:
            raise RuntimeError("predecessor_changed_before_fence")
        os.kill(predecessor["pid"], 15)
        until = time.monotonic() + 20
        while time.monotonic() < until and ticks(predecessor["pid"]) is not None:
            time.sleep(0.1)
        if ticks(predecessor["pid"]) is not None:
            raise RuntimeError("predecessor_did_not_exit_after_sigterm")
    atomic(ROOT / "TAKEOVER.json", {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                                     "claim_generation": claim["claimed_at"], "predecessor_pid": predecessor["pid"],
                                     "predecessor_start_ticks": predecessor["start_ticks"], "r2_state": str(R2_STATE)})
    print(json.dumps({"r2_state": str(R2_STATE), "standby": str(ROOT / "R2_STANDBY_READY.json"), "takeover": str(ROOT / "TAKEOVER.json")}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
