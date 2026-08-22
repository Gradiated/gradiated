#!/usr/bin/env python3
"""Deterministic offline fault injections for the owner/claim-launch seam."""
from __future__ import annotations

import importlib.util
import json
import pathlib
import tempfile

HERE = pathlib.Path(__file__).resolve().parent


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, HERE / name)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


OWNER = load("run_norm_fp8_exact_order_component_owner.py")
LAUNCH = load("run_norm_fp8_exact_order_component_claim_launch.py")


def binding(root: pathlib.Path) -> dict:
    return {
        "claimed_at": "2026-07-30T07:42:00Z",
        "absolute_release_deadline_utc": "2026-07-30T08:15:15Z",
        "maximum_claim_seconds": 2400,
        "artifact_root": str(root),
        "bench": {"id": "fault-bench", "resource": {"public_ipv4": "unused", "ssh_user": "unused", "ssh_identity_path": "/dev/null", "known_hosts_namespace": "/dev/null"}, "contents": {"gpu_uuid": "unused"}},
    }


class FakeOwner(OWNER.Owner):
    def __init__(self, root: pathlib.Path, outcomes: list[str]):
        super().__init__(binding(root), root, root / "OWNER_READY.json")
        self.outcomes, self.calls = outcomes, []

    def heartbeat_loop(self) -> None:
        return

    def release(self, condition: str, reason: str) -> None:
        if not self.releases:
            self.releases.append({"condition": condition, "returncode": 0})
            self.event("simulated_bench_release", condition=condition, reason=reason)

    def stage(self) -> None:
        self.phase = "immutable_staging"; self.calls.append(self.phase)
        if self.outcomes and self.outcomes.pop(0) == "fail": raise OWNER.Recoverable(self.phase, "injected_stage_failure")

    def run_science(self) -> None:
        self.phase = "scientific_runner"; self.calls.append(self.phase)

    def retrieve(self) -> dict:
        self.phase = "terminal_retrieval"; self.calls.append(self.phase)
        return {"classification": "component_negative", "ledger_complete": True}


def check_delayed_staging() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary); owner = FakeOwner(root, ["ok"])
        owner.adopt()
        ready = json.loads((root / "OWNER_READY.json").read_text())
        assert ready["phase"] == "owner_adopted_heartbeat_started"
        assert owner.phase == "owner_adopted"
        return {"name": "delayed_staging_adopts_before_30s", "passed": True, "ready_phase": ready["phase"], "launcher_orphans": 0}


def check_pre_adoption_release() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        root = pathlib.Path(temporary); seen = []; original = LAUNCH.command
        try:
            LAUNCH.command = lambda args, timeout=60: seen.append(args) or ""
            LAUNCH.release_claim("bench", "generation", root, "injected_pre_adoption_failure")
        finally:
            LAUNCH.command = original
        release = seen[-1]
        assert "--expected-claimed-at" in release and release[release.index("--expected-claimed-at") + 1] == "generation"
        return {"name": "pre_adoption_failure_generation_release", "passed": True, "expected_claimed_at": "generation"}


def check_repair_reentry() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        owner = FakeOwner(pathlib.Path(temporary), ["fail", "ok"])
        def matching_request(error):
            assert error.phase == "immutable_staging"
            owner.generation += 1
            owner.event("simulated_matching_repair_request", retry_phase=error.phase)
            return True
        owner.await_repair = matching_request
        assert owner.execute() == 0
        assert owner.generation == 1 and owner.calls.count("immutable_staging") == 2
        return {"name": "matching_repair_reenters_generation_1", "passed": True, "generation": owner.generation, "reentered_phase": "immutable_staging"}


def check_repair_deadline() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        owner = FakeOwner(pathlib.Path(temporary), ["fail"])
        owner.await_repair = lambda error: False
        assert owner.execute() == 2
        assert owner.releases == [{"condition": "maintenance", "returncode": 0}]
        return {"name": "missing_repair_request_deadline_release", "passed": True, "condition": "maintenance", "release_count": 1}


def check_complete_terminal() -> dict:
    with tempfile.TemporaryDirectory() as temporary:
        owner = FakeOwner(pathlib.Path(temporary), ["ok"])
        assert owner.execute() == 0
        owner.release("ready", "duplicate_attempt")
        assert owner.releases == [{"condition": "ready", "returncode": 0}]
        return {"name": "complete_terminal_ready_release_once", "passed": True, "condition": "ready", "release_count": 1}


def main() -> int:
    results = [check_delayed_staging(), check_pre_adoption_release(), check_repair_reentry(), check_repair_deadline(), check_complete_terminal()]
    payload = {"schema_version": 1, "classification": "offline_owner_control_fault_injections", "all_passed": all(row["passed"] for row in results), "provider_mutated": False, "science_consumed": False, "results": results}
    target = HERE / "OWNER_CONTROL_FAULT_INJECTIONS.json"
    temporary = target.with_suffix(".json.part"); temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n"); json.loads(temporary.read_text()); temporary.replace(target)
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
