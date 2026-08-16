from __future__ import annotations

import os
import re
import subprocess
import hashlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .schema import IsolationSpec


@dataclass(frozen=True)
class ProcessRecord:
    pid: int
    parent_pid: int
    cpu_percent: float
    rss_bytes: int
    command: str


@dataclass(frozen=True)
class HostSnapshot:
    captured_at: str
    ac_power: bool
    thermal_warning: bool
    available_memory_bytes: int
    load_average: tuple[float, float, float]
    processes: tuple[ProcessRecord, ...]
    raw_commands: dict[str, Any]

    def to_mapping(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IsolationDecision:
    accepted: bool
    rejection_reasons: tuple[str, ...]
    blocking_processes: tuple[ProcessRecord, ...]

    def to_mapping(self) -> dict:
        return asdict(self)


def parse_vm_stat(raw: str) -> int:
    page_match = re.search(r"page size of (\d+) bytes", raw)
    if page_match is None:
        raise ValueError("vm_stat page size missing")
    page_size = int(page_match.group(1))
    available_names = {
        "Pages free",
        "Pages inactive",
        "Pages speculative",
        "Pages purgeable",
    }
    page_count = 0
    observed: set[str] = set()
    for line in raw.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        if name in available_names:
            digits = re.sub(r"[^0-9]", "", value)
            if digits:
                page_count += int(digits)
                observed.add(name)
    if observed != available_names:
        raise ValueError("vm_stat available page counters missing")
    return page_count * page_size


def parse_processes(raw: str) -> tuple[ProcessRecord, ...]:
    records: list[ProcessRecord] = []
    for line in raw.splitlines():
        fields = line.strip().split(maxsplit=4)
        if len(fields) != 5:
            continue
        try:
            records.append(
                ProcessRecord(
                    pid=int(fields[0]),
                    parent_pid=int(fields[1]),
                    cpu_percent=float(fields[2]),
                    rss_bytes=int(fields[3]) * 1024,
                    command=_redact_command(fields[4]),
                )
            )
        except ValueError:
            continue
    return tuple(records)


def _redact_command(command: str) -> str:
    patterns = (
        r"(?i)(--(?:api[-_]?key|token|password|secret)(?:=|\s+))\S+",
        r"(?i)(authorization:\s*bearer\s+)\S+",
    )
    redacted = command
    for pattern in patterns:
        redacted = re.sub(pattern, r"\1<redacted>", redacted)
    return redacted


def process_ancestry(
    processes: tuple[ProcessRecord, ...], pid: int | None = None
) -> set[int]:
    by_pid = {process.pid: process for process in processes}
    current = os.getpid() if pid is None else pid
    ancestry: set[int] = set()
    while current > 0 and current not in ancestry:
        ancestry.add(current)
        process = by_pid.get(current)
        if process is None:
            break
        current = process.parent_pid
    return ancestry


def process_descendants(
    processes: tuple[ProcessRecord, ...], root_pids: set[int]
) -> set[int]:
    descendants = set(root_pids)
    changed = True
    while changed:
        changed = False
        for process in processes:
            if process.parent_pid in descendants and process.pid not in descendants:
                descendants.add(process.pid)
                changed = True
    return descendants


def _capture(command: tuple[str, ...]) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    return {
        "command": list(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def capture_host_state() -> HostSnapshot:
    commands = {
        "uname": ("uname", "-a"),
        "sw_vers": ("sw_vers",),
        "hardware": (
            "sysctl",
            "hw.model",
            "hw.memsize",
            "hw.ncpu",
            "hw.perflevel0.logicalcpu",
            "hw.perflevel1.logicalcpu",
            "machdep.cpu.brand_string",
        ),
        "power": ("pmset", "-g", "batt"),
        "power_policy": ("pmset", "-g", "custom"),
        "thermal": ("pmset", "-g", "therm"),
        "vm_stat": ("vm_stat",),
        "swap": ("sysctl", "vm.swapusage"),
        "processes": ("ps", "-axo", "pid=,ppid=,%cpu=,rss=,command="),
    }
    raw = {name: _capture(command) for name, command in commands.items()}
    required = ("power", "thermal", "vm_stat", "processes")
    if any(raw[name]["returncode"] != 0 for name in required):
        raise RuntimeError("required host-state command failed")
    process_stdout = raw["processes"].pop("stdout")
    raw["processes"]["stdout_sha256"] = hashlib.sha256(
        process_stdout.encode("utf-8")
    ).hexdigest()
    power = raw["power"]["stdout"]
    thermal = raw["thermal"]["stdout"]
    return HostSnapshot(
        captured_at=datetime.now(timezone.utc).isoformat(),
        ac_power="AC Power" in power,
        thermal_warning=(
            "No thermal warning level has been recorded" not in thermal
            or "No performance warning level has been recorded" not in thermal
        ),
        available_memory_bytes=parse_vm_stat(raw["vm_stat"]["stdout"]),
        load_average=tuple(float(value) for value in os.getloadavg()),
        processes=parse_processes(process_stdout),
        raw_commands=raw,
    )


def evaluate_isolation(
    snapshot: HostSnapshot, isolation: IsolationSpec, excluded_pids: set[int]
) -> IsolationDecision:
    reasons: list[str] = []
    if isolation.require_ac_power and not snapshot.ac_power:
        reasons.append("host is not on AC power")
    if isolation.require_no_thermal_warning and snapshot.thermal_warning:
        reasons.append("host reports thermal warning or unavailable thermal state")
    if snapshot.available_memory_bytes < isolation.minimum_available_memory_bytes:
        reasons.append("available memory is below the campaign floor")
    blockers = tuple(
        process
        for process in snapshot.processes
        if process.pid not in excluded_pids
        and process.cpu_percent >= isolation.quiet_process_cpu_percent
    )
    if blockers:
        reasons.append("external CPU-heavy processes are active")
    return IsolationDecision(
        accepted=not reasons,
        rejection_reasons=tuple(reasons),
        blocking_processes=blockers,
    )
