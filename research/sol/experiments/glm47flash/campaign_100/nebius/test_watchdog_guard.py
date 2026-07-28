from __future__ import annotations

from pathlib import Path

import pytest

import vllm_smoke_control


def write_cmdline(proc_root: Path, pid: int, argv: list[str]) -> None:
    process_dir = proc_root / str(pid)
    process_dir.mkdir()
    (process_dir / "cmdline").write_bytes(b"\0".join(value.encode() for value in argv) + b"\0")


def test_active_watchdogs_for_resource_matches_exact_resource(tmp_path: Path) -> None:
    write_cmdline(
        tmp_path,
        101,
        [
            "/usr/bin/python3",
            "/shared/placement_control.py",
            "watchdog",
            "computeinstance-target",
            "target-boot",
            "1234",
        ],
    )
    write_cmdline(
        tmp_path,
        202,
        [
            "/usr/bin/python3",
            "/shared/placement_control.py",
            "watchdog",
            "computeinstance-other",
            "other-boot",
            "1234",
        ],
    )

    assert vllm_smoke_control.active_watchdogs_for_resource(
        "computeinstance-target", "target-boot", proc_root=tmp_path
    ) == [101]


def test_start_watchdog_refuses_duplicate_resource(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        vllm_smoke_control,
        "active_watchdogs_for_resource",
        lambda instance_id, disk_name: [101],
    )

    with pytest.raises(vllm_smoke_control.VllmSmokeError, match="already has an active"):
        vllm_smoke_control.start_independent_watchdog(
            "computeinstance-target",
            "target-boot",
            1234,
            "replacement-watchdog",
            unit_manager="user",
        )
