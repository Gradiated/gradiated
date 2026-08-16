#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[8]
sys.path.insert(0, str(ROOT / "research/factory/src"))

from grad_research.labd import Fenced, LabDatabase, LeaseBusy
from grad_research.util import content_hash


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def read_json(path: Path, default: Any) -> Any:
    return json.loads(path.read_text()) if path.is_file() else default


def now() -> float:
    return time.time()


class FakeAdapter:
    def __init__(self, root: Path):
        self.path = root / "fake-provider.json"

    def delete(self, resource_id: str) -> None:
        state = read_json(self.path, {"resources": []})
        state["resources"] = [item for item in state["resources"] if item != resource_id]
        write_json(self.path, state)

    def exists(self, resource_id: str) -> bool:
        return resource_id in read_json(self.path, {"resources": []})["resources"]

    def inventory_contains(self, resource_id: str) -> bool:
        return resource_id in read_json(self.path, {"resources": []})["resources"]


def state_path(root: Path) -> Path:
    return root / "controller-state.json"


def terminal_path(root: Path) -> Path:
    return root / "terminal-result.json"


def terminal_is_complete(path: Path) -> bool:
    terminal = read_json(path, {})
    return all(
        terminal.get(name) is True
        for name in (
            "direct_resource_absent",
            "inventory_absent",
            "duplicate_ownership_rejected",
            "identity_mismatch_rejected",
        )
    ) and terminal.get("allocation_state") == "cleaned"


def controller(root: Path, scenario: str) -> int:
    db = LabDatabase(root / "lab.sqlite3")
    owner = f"controller-{scenario}"
    started = now()
    lease = db.acquire_coordinator("durable-control", owner, ttl_seconds=1, now=started)
    db.ensure_budget("zero-provider", authorized_usd=1)
    admission_sha = content_hash({"scenario": scenario, "kind": "zero-provider"})
    reservation_id = f"reservation-{scenario}"
    allocation_id = f"allocation-{scenario}"
    resource_id = f"fake-{scenario}"
    db.reserve(
        reservation_id=reservation_id,
        campaign_id="zero-provider",
        program_id="durable-control",
        owner=owner,
        epoch=lease["epoch"],
        amount_usd=1,
        cleanup_reserve_usd=0.1,
        expires_at=started + 8,
        admission_sha256=admission_sha,
        now=started,
    )
    db.register_allocation(
        allocation_id=allocation_id,
        reservation_id=reservation_id,
        provider="fake",
        provider_resource_id=resource_id,
        setup_key="zero-provider",
        owner=owner,
        epoch=lease["epoch"],
        absolute_deadline=started + (1.2 if scenario == "deadline" else 7),
        now=started,
    )
    write_json(root / "fake-provider.json", {"resources": [resource_id]})
    write_json(
        state_path(root),
        {
            "schema_version": 1,
            "scenario": scenario,
            "owner": owner,
            "epoch": lease["epoch"],
            "allocation_id": allocation_id,
            "resource_id": resource_id,
            "controller_pid": os.getpid(),
            "started_at": started,
            "heartbeat_at": started,
            "state": "running",
            "identity_sha256": admission_sha,
        },
    )
    try:
        duplicate_rejected = False
        try:
            db.acquire_coordinator("durable-control", "duplicate-owner", ttl_seconds=1, now=now())
        except LeaseBusy:
            duplicate_rejected = True
        mismatch_rejected = False
        try:
            db.heartbeat_allocation(allocation_id, owner="wrong-owner", epoch=lease["epoch"], now=now())
        except Fenced:
            mismatch_rejected = True
        state = read_json(state_path(root), {})
        state["duplicate_ownership_rejected"] = duplicate_rejected
        state["identity_mismatch_rejected"] = mismatch_rejected
        write_json(state_path(root), state)
        failure_at = started + 1.0
        while now() < started + 5:
            if (root / "watchdog-stop").exists():
                state = read_json(state_path(root), {})
                state.update({"state": "stopped_by_watchdog", "heartbeat_at": now()})
                write_json(state_path(root), state)
                return 0
            if scenario == "failure" and now() >= failure_at:
                state = read_json(state_path(root), {})
                state.update({"state": "failure_injected", "heartbeat_at": now()})
                write_json(state_path(root), state)
                return 23
            db.heartbeat_coordinator("durable-control", owner, lease["epoch"], ttl_seconds=1, now=now())
            db.heartbeat_allocation(allocation_id, owner=owner, epoch=lease["epoch"], now=now())
            state = read_json(state_path(root), {})
            state["heartbeat_at"] = now()
            write_json(state_path(root), state)
            time.sleep(0.15)
        return 0
    finally:
        db.close()


def watchdog(root: Path, scenario: str) -> int:
    deadline = now() + 7
    stale_after = 0.9
    watchdog_path = root / "watchdog-state.json"
    while now() < deadline:
        state = read_json(state_path(root), {})
        if state:
            write_json(
                watchdog_path,
                {
                    "schema_version": 1,
                    "scenario": scenario,
                    "watchdog_pid": os.getpid(),
                    "controller_identity_sha256": state["identity_sha256"],
                    "heartbeat_at": now(),
                    "state": "watching",
                },
            )
        state_deadline = 0.0
        if state:
            db_probe = LabDatabase(root / "lab.sqlite3")
            snapshot_probe = db_probe.snapshot()
            db_probe.close()
            if snapshot_probe["allocations"]:
                state_deadline = snapshot_probe["allocations"][0]["absolute_deadline"]
        triggered = state and (
            (scenario == "deadline" and now() >= state_deadline)
            or (scenario == "failure" and now() - state.get("heartbeat_at", 0) > stale_after)
        )
        if triggered:
            db = LabDatabase(root / "lab.sqlite3")
            cleanup = db.sweep_due({"fake": FakeAdapter(root)}, now=now())
            snapshot = db.snapshot()
            allocation = snapshot["allocations"][0] if snapshot["allocations"] else {}
            resource_id = state["resource_id"]
            direct_absent = not FakeAdapter(root).exists(resource_id)
            inventory_absent = not FakeAdapter(root).inventory_contains(resource_id)
            result = {
                "schema_version": 1,
                "kind": "zero_provider_terminal_result",
                "scenario": scenario,
                "trigger": "absolute_deadline" if scenario == "deadline" else "stale_controller_heartbeat",
                "controller_state": state.get("state"),
                "cleanup": cleanup,
                "direct_resource_absent": direct_absent,
                "inventory_absent": inventory_absent,
                "allocation_state": allocation.get("state"),
                "duplicate_ownership_rejected": state.get("duplicate_ownership_rejected") is True,
                "identity_mismatch_rejected": state.get("identity_mismatch_rejected") is True,
                "missing_terminal_artifact_rejected": not terminal_is_complete(terminal_path(root)),
                "watchdog_pid": os.getpid(),
                "finished_at": now(),
            }
            passed = all(
                [
                    direct_absent,
                    inventory_absent,
                    allocation.get("state") == "cleaned",
                    result["duplicate_ownership_rejected"],
                    result["identity_mismatch_rejected"],
                    result["missing_terminal_artifact_rejected"],
                ]
            )
            if passed:
                write_json(terminal_path(root), result)
                watchdog_state = read_json(watchdog_path, {})
                watchdog_state.update({"heartbeat_at": now(), "state": "terminal_written"})
                write_json(watchdog_path, watchdog_state)
                (root / "watchdog-stop").touch()
                db.close()
                return 0
            db.close()
        time.sleep(0.1)
    return 3


def unit_status(unit: str) -> dict[str, str]:
    output = subprocess.check_output(
        ["systemctl", "--user", "show", unit, "--property=MainPID,ControlGroup,ActiveState"], text=True
    )
    return dict(line.split("=", 1) for line in output.splitlines() if "=" in line)


def run(root: Path) -> int:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    evidence: dict[str, Any] = {"schema_version": 1, "kind": "durable_zero_provider_proof", "runs": []}
    script = str(Path(__file__).resolve())
    for scenario in ("failure", "deadline"):
        scenario_root = root / scenario
        scenario_root.mkdir()
        token = hashlib.sha256(f"{scenario}-{time.time_ns()}".encode()).hexdigest()[:12]
        controller_unit = f"durable-control-controller-{token}"
        watchdog_unit = f"durable-control-watchdog-{token}"
        launcher = subprocess.run(
            [
                "bash", "-c",
                "systemd-run --user --no-block --collect --unit \"$1\" --setenv=PYTHONPATH=/root/workspace/research/factory/src /usr/bin/python3 \"$2\" controller \"$3\" \"$4\" >/dev/null && systemd-run --user --no-block --collect --unit \"$5\" --setenv=PYTHONPATH=/root/workspace/research/factory/src /usr/bin/python3 \"$2\" watchdog \"$3\" \"$4\" >/dev/null",
                "launcher",
                controller_unit,
                script,
                str(scenario_root),
                scenario,
                watchdog_unit,
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        time.sleep(0.35)
        controller_status = unit_status(f"{controller_unit}.service")
        watchdog_status = unit_status(f"{watchdog_unit}.service")
        end = now() + 10
        while not terminal_path(scenario_root).exists() and now() < end:
            time.sleep(0.1)
        terminal = read_json(terminal_path(scenario_root), {})
        evidence["runs"].append(
            {
                "scenario": scenario,
                "launcher_returncode": launcher.returncode,
                "launcher_exited_before_terminal": launcher.returncode == 0 and bool(terminal),
                "controller_unit": controller_status,
                "watchdog_unit": watchdog_status,
                "terminal": terminal,
                "pass": launcher.returncode == 0
                and controller_status.get("ControlGroup", "").startswith("/user.slice/")
                and watchdog_status.get("ControlGroup", "").startswith("/user.slice/")
                and terminal.get("allocation_state") == "cleaned"
                and terminal.get("direct_resource_absent") is True
                and terminal.get("inventory_absent") is True,
            }
        )
    evidence["pass"] = all(item["pass"] for item in evidence["runs"])
    write_json(root / "DURABLE_PROVIDER_CONTROL_PROOF.json", evidence)
    return 0 if evidence["pass"] else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("run", "controller", "watchdog"))
    parser.add_argument("root", type=Path)
    parser.add_argument("scenario", nargs="?", choices=("failure", "deadline"))
    args = parser.parse_args()
    if args.mode == "run":
        return run(args.root)
    if args.scenario is None:
        parser.error("controller and watchdog need a scenario")
    return controller(args.root, args.scenario) if args.mode == "controller" else watchdog(args.root, args.scenario)


if __name__ == "__main__":
    raise SystemExit(main())
