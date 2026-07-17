from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


class ProfilingError(ValueError):
    pass


SECRET_FLAGS = {
    "--api-key",
    "--apikey",
    "--auth-token",
    "--password",
    "--secret",
    "--token",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def _redact_command(command: list[str]) -> list[str]:
    redacted: list[str] = []
    hide_next = False
    for argument in command:
        if hide_next:
            redacted.append("<redacted>")
            hide_next = False
            continue
        lowered = argument.casefold()
        if lowered in SECRET_FLAGS:
            redacted.append(argument)
            hide_next = True
            continue
        if "=" in argument:
            name, _ = argument.split("=", 1)
            if name.casefold() in SECRET_FLAGS or any(word in name.casefold() for word in ("token", "password", "secret", "api_key")):
                redacted.append(f"{name}=<redacted>")
                continue
        redacted.append(argument)
    return redacted


def build_capture_command(
    tier: str,
    command: list[str],
    run_dir: Path,
    *,
    kernel_name: str | None = None,
    nvtx_include: str | None = None,
    launch_skip: int | None = None,
    launch_count: int | None = None,
    sections: list[str] | None = None,
    backend: str = "nvidia",
) -> list[str]:
    if tier not in {"baseline", "timeline", "compute"}:
        raise ProfilingError("tier must be baseline, timeline, or compute")
    if not command:
        raise ProfilingError("capture command cannot be empty")
    if backend not in {"nvidia", "amd"}:
        raise ProfilingError("backend must be nvidia or amd")
    if tier == "baseline":
        return list(command)
    if backend == "amd" and tier == "timeline":
        return [
            "rocprofv3",
            "--runtime-trace",
            "--output-format",
            "csv",
            "--output-directory",
            str(run_dir / "timeline"),
            "--",
            *command,
        ]
    if backend == "amd" and tier == "compute":
        wrapped = [
            "rocprof-compute",
            "profile",
            "--output-directory",
            str(run_dir / "compute"),
            "--no-roof",
        ]
        if kernel_name:
            wrapped.extend(["--kernel", kernel_name])
        return [*wrapped, "--", *command]
    if tier == "timeline":
        return [
            "nsys",
            "profile",
            "--trace=cuda,nvtx,osrt",
            "--cuda-graph-trace=node",
            "--force-overwrite=true",
            f"--output={run_dir / 'timeline'}",
            *command,
        ]

    wrapped = [
        "ncu",
        "--target-processes",
        "all",
        "--force-overwrite",
        "--export",
        str(run_dir / "compute"),
    ]
    for section in sections or ["SpeedOfLight", "MemoryWorkloadAnalysis", "LaunchStats", "Occupancy"]:
        wrapped.extend(["--section", section])
    if kernel_name:
        wrapped.extend(["--kernel-name", kernel_name])
    if nvtx_include:
        wrapped.extend(["--nvtx", "--nvtx-include", nvtx_include])
    if launch_skip is not None:
        wrapped.extend(["--launch-skip", str(launch_skip)])
    if launch_count is not None:
        wrapped.extend(["--launch-count", str(launch_count)])
    return [*wrapped, *command]


def _tool_version(tool: str) -> str | None:
    if not shutil.which(tool):
        return None
    for arguments in ([tool, "--version"], [tool, "version"]):
        try:
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=5, check=False)
        except (OSError, subprocess.TimeoutExpired):
            continue
        text = (result.stdout or result.stderr).strip()
        if text:
            return text.splitlines()[0][:500]
    return "available"


def _sample_gpu(stop: threading.Event, path: Path, command: list[str], interval: float) -> None:
    fields = [
        "timestamp_seconds",
        "gpu_index",
        "utilization_gpu_percent",
        "memory_used_mib",
        "power_w",
        "sm_clock_mhz",
        "memory_clock_mhz",
        "temperature_c",
    ]
    started = time.monotonic()
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        while not stop.is_set():
            try:
                result = subprocess.run(command, capture_output=True, text=True, timeout=max(2.0, interval), check=False)
            except (OSError, subprocess.TimeoutExpired):
                return
            if result.returncode != 0:
                return
            for index, line in enumerate(result.stdout.splitlines()):
                values = [part.strip() for part in line.split(",")]
                if len(values) < 7:
                    continue
                writer.writerow(dict(zip(fields, [time.monotonic() - started, index, *values[:7]], strict=True)))
            handle.flush()
            stop.wait(interval)


def default_sampler_command() -> list[str] | None:
    if not shutil.which("nvidia-smi"):
        return None
    return [
        "nvidia-smi",
        "--query-gpu=utilization.gpu,memory.used,power.draw,clocks.sm,clocks.mem,temperature.gpu",
        "--format=csv,noheader,nounits",
    ]


def run_capture(
    *,
    tier: str,
    command: list[str],
    output_root: Path,
    timeout_seconds: float,
    sample_interval_seconds: float = 1.0,
    sampler_command: list[str] | None = None,
    kernel_name: str | None = None,
    nvtx_include: str | None = None,
    launch_skip: int | None = None,
    launch_count: int | None = None,
    sections: list[str] | None = None,
    backend: str = "nvidia",
    artifact_paths: list[Path] | None = None,
) -> dict[str, Any]:
    if timeout_seconds <= 0 or sample_interval_seconds <= 0:
        raise ProfilingError("timeouts and sample intervals must be positive")
    required_tool = {
        ("nvidia", "timeline"): "nsys",
        ("nvidia", "compute"): "ncu",
        ("amd", "timeline"): "rocprofv3",
        ("amd", "compute"): "rocprof-compute",
    }.get((backend, tier))
    if required_tool and not shutil.which(required_tool):
        raise ProfilingError(f"{required_tool} is required for the {tier} tier")
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}-{uuid.uuid4().hex[:8]}"
    run_dir = output_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    wrapped = build_capture_command(
        tier,
        command,
        run_dir,
        kernel_name=kernel_name,
        nvtx_include=nvtx_include,
        launch_skip=launch_skip,
        launch_count=launch_count,
        sections=sections,
        backend=backend,
    )
    stop = threading.Event()
    sampler = None
    samples_path = run_dir / "gpu_samples.csv"
    if sampler_command:
        sampler = threading.Thread(
            target=_sample_gpu,
            args=(stop, samples_path, sampler_command, sample_interval_seconds),
            daemon=True,
        )
        sampler.start()

    started_at = _utc_now()
    started_monotonic = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(wrapped, capture_output=True, text=True, timeout=timeout_seconds, check=False)
        exit_code = result.returncode
        stdout = result.stdout
        stderr = result.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        exit_code = 124
        stdout = error.stdout.decode() if isinstance(error.stdout, bytes) else (error.stdout or "")
        stderr = error.stderr.decode() if isinstance(error.stderr, bytes) else (error.stderr or "")
    finally:
        stop.set()
        if sampler:
            sampler.join(timeout=max(2.0, sample_interval_seconds * 2))
    duration = time.monotonic() - started_monotonic
    (run_dir / "command.stdout.log").write_text(stdout)
    (run_dir / "command.stderr.log").write_text(stderr)
    artifacts = []
    for path in artifact_paths or []:
        if not path.is_file():
            continue
        artifacts.append({
            "path": str(path),
            "size_bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        })
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "tier": tier,
        "backend": backend,
        "started_at_utc": started_at,
        "finished_at_utc": _utc_now(),
        "duration_seconds": round(duration, 6),
        "timeout_seconds": timeout_seconds,
        "timed_out": timed_out,
        "exit_code": exit_code,
        "command": _redact_command(command),
        "wrapped_command": _redact_command(wrapped),
        "sampler": "enabled" if sampler_command else "unavailable_or_disabled",
        "tools": {
            tool: _tool_version(tool)
            for tool in ("nvidia-smi", "nsys", "ncu", "amd-smi", "rocprofv3", "rocprof-compute")
        },
        "artifacts": artifacts,
        "interpretation": "baseline is scoreable; timeline and compute tiers are diagnostic and may perturb performance",
    }
    _write_json(run_dir / "profile_manifest.json", manifest)
    return {"run_dir": str(run_dir), "manifest": manifest}


def _interval_union(intervals: Iterable[tuple[float, float]]) -> float:
    ordered = sorted((start, end) for start, end in intervals if end > start)
    if not ordered:
        return 0.0
    total = 0.0
    current_start, current_end = ordered[0]
    for start, end in ordered[1:]:
        if start <= current_end:
            current_end = max(current_end, end)
        else:
            total += current_end - current_start
            current_start, current_end = start, end
    return total + current_end - current_start


def _kernel_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"calls": 0, "sum_us": 0.0})
    for event in events:
        item = totals[event["name"]]
        item["calls"] += 1
        item["sum_us"] += event["end_us"] - event["start_us"]
    top = [
        {"name": name, "calls": int(values["calls"]), "sum_us": round(values["sum_us"], 6)}
        for name, values in totals.items()
    ]
    top.sort(key=lambda row: row["sum_us"], reverse=True)
    intervals = [(event["start_us"], event["end_us"]) for event in events]
    return {
        "kernel_count": len(events),
        "kernel_sum_us": round(sum(end - start for start, end in intervals), 6),
        "kernel_union_us": round(_interval_union(intervals), 6),
        "top_kernels": top[:25],
    }


def _load_json(path: Path) -> Any:
    if path.suffix == ".gz":
        with gzip.open(path, "rt") as handle:
            return json.load(handle)
    return json.loads(path.read_text())


def _parse_torch_trace(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    value = _load_json(path)
    rows = value.get("traceEvents", []) if isinstance(value, dict) else []
    kernels: list[dict[str, Any]] = []
    cpu_events = 0
    for row in rows:
        if row.get("ph") != "X" or not isinstance(row.get("dur"), (int, float)):
            continue
        category = str(row.get("cat", "")).casefold()
        name = str(row.get("name", "unknown"))
        if "kernel" in category or category in {"gpu", "cuda_kernel"}:
            start = float(row.get("ts", 0.0))
            kernels.append({"name": name, "start_us": start, "end_us": start + float(row["dur"])})
        elif "cpu" in category or "operator" in category:
            cpu_events += 1
    return _kernel_summary(kernels) | {"source": "pytorch_chrome_trace", "cpu_event_count": cpu_events}, kernels


def _sqlite_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    escaped = table.replace("'", "''")
    return {row[1] for row in connection.execute(f"PRAGMA table_info('{escaped}')")}


def _parse_nsys_sqlite(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    kernels: list[dict[str, Any]] = []
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        kernel_tables = [name for name in tables if "KERNEL" in name.upper()]
        strings: dict[int, str] = {}
        if "StringIds" in tables:
            strings = {int(row[0]): str(row[1]) for row in connection.execute("SELECT id, value FROM StringIds")}
        for table in kernel_tables:
            columns = _sqlite_columns(connection, table)
            if not {"start", "end"}.issubset(columns):
                continue
            name_column = next((name for name in ("demangledName", "shortName", "name") if name in columns), None)
            selection = ["start", "end"] + ([name_column] if name_column else [])
            quoted_table = table.replace('"', '""')
            for row in connection.execute(f'SELECT {", ".join(selection)} FROM "{quoted_table}"'):
                raw_name = row[2] if name_column else table
                name = strings.get(raw_name, str(raw_name)) if isinstance(raw_name, int) else str(raw_name)
                kernels.append({
                    "name": name,
                    "start_us": float(row[0]) / 1000.0,
                    "end_us": float(row[1]) / 1000.0,
                })
    return _kernel_summary(kernels) | {"source": "nsight_systems_sqlite"}, kernels


def _number(value: str) -> float | str:
    cleaned = value.strip().replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return value


def _parse_ncu_csv(path: Path) -> dict[str, Any]:
    grouped: dict[str, dict[str, Any]] = {}
    with path.open(newline="") as handle:
        for row in csv.DictReader(line for line in handle if not line.startswith("==")):
            kernel = row.get("Kernel Name") or row.get("Kernel") or "unknown"
            metric = row.get("Metric Name") or row.get("Metric")
            if not metric:
                continue
            grouped.setdefault(kernel, {})[metric] = {
                "value": _number(row.get("Metric Value") or row.get("Value") or ""),
                "unit": row.get("Metric Unit") or row.get("Unit") or "",
            }
    return {
        "source": "nsight_compute_csv",
        "kernels": [{"name": name, "metrics": metrics} for name, metrics in grouped.items()],
    }


def _parse_rocprof_kernel_csv(path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    kernels: list[dict[str, Any]] = []
    with path.open(newline="") as handle:
        for row in csv.DictReader(handle):
            try:
                start = float(row["Start_Timestamp"]) / 1000.0
                end = float(row["End_Timestamp"]) / 1000.0
            except (KeyError, TypeError, ValueError):
                continue
            kernels.append({
                "name": row.get("Kernel_Name") or "unknown",
                "start_us": start,
                "end_us": end,
            })
    return _kernel_summary(kernels) | {"source": "rocprofv3_kernel_csv"}, kernels


def _parse_gpu_samples(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"sample_count": 0}
    rows: list[dict[str, float]] = []
    with path.open(newline="") as handle:
        for raw in csv.DictReader(handle):
            try:
                rows.append({key: float(value) for key, value in raw.items() if value not in {None, "", "N/A"}})
            except ValueError:
                continue
    if not rows:
        return {"sample_count": 0}
    result: dict[str, Any] = {"sample_count": len(rows)}
    for field in ("utilization_gpu_percent", "memory_used_mib", "power_w", "sm_clock_mhz", "memory_clock_mhz", "temperature_c"):
        values = [row[field] for row in rows if field in row]
        if values:
            result[field] = {"mean": round(sum(values) / len(values), 6), "max": max(values)}
    energy = 0.0
    samples_by_gpu: dict[float, list[tuple[float, float]]] = defaultdict(list)
    for row in rows:
        if "timestamp_seconds" in row and "power_w" in row:
            samples_by_gpu[row.get("gpu_index", 0.0)].append((row["timestamp_seconds"], row["power_w"]))
    for gpu_samples in samples_by_gpu.values():
        ordered = sorted(gpu_samples)
        energy += sum((b[0] - a[0]) * (a[1] + b[1]) / 2 for a, b in zip(ordered, ordered[1:]))
    result["energy_joules"] = round(energy, 6)
    return result


def _attribution(semantics: dict[str, Any] | None, kernels: list[dict[str, Any]]) -> dict[str, Any]:
    total = _interval_union((event["start_us"], event["end_us"]) for event in kernels)
    if not semantics or not total:
        return {"kernel_union_coverage": 0.0, "matched_operations": []}
    matched_events: list[dict[str, Any]] = []
    matched_operations: list[str] = []
    for operation in semantics.get("operations", []):
        patterns = operation.get("kernel_patterns", [])
        operation_events = [event for event in kernels if any(pattern.casefold() in event["name"].casefold() for pattern in patterns)]
        if operation_events:
            matched_operations.append(operation.get("id", "unknown"))
            matched_events.extend(operation_events)
    covered = _interval_union((event["start_us"], event["end_us"]) for event in matched_events)
    return {"kernel_union_coverage": round(min(1.0, covered / total), 6), "matched_operations": matched_operations}


def _perturbation(benchmark: dict[str, Any] | None) -> dict[str, Any] | None:
    if not benchmark or not isinstance(benchmark.get("profiler_off"), dict) or not isinstance(benchmark.get("profiler_on"), dict):
        return None
    ratios = {}
    for metric, off_value in benchmark["profiler_off"].items():
        on_value = benchmark["profiler_on"].get(metric)
        if isinstance(off_value, (int, float)) and isinstance(on_value, (int, float)) and off_value:
            ratios[metric] = round(on_value / off_value, 6)
    return {"profiler_on_over_off": ratios}


def _benchmark_economics(benchmark: dict[str, Any] | None, gpu: dict[str, Any]) -> dict[str, Any] | None:
    if not benchmark:
        return None
    result = dict(benchmark)
    throughput = result.get("output_tokens_per_second")
    hourly_rate = result.get("gpu_hourly_usd")
    if isinstance(throughput, (int, float)) and throughput > 0 and isinstance(hourly_rate, (int, float)) and hourly_rate > 0:
        result["usd_per_million_output_tokens"] = round(hourly_rate / 3600 / throughput * 1_000_000, 6)
    output_tokens = result.get("output_tokens_total")
    energy = gpu.get("energy_joules")
    if isinstance(output_tokens, (int, float)) and output_tokens > 0 and isinstance(energy, (int, float)):
        result["joules_per_output_token"] = round(energy / output_tokens, 9)
    return result


def _summary_markdown(summary: dict[str, Any]) -> str:
    timeline = summary.get("timeline", {})
    gpu = summary.get("gpu", {})
    lines = [
        "# Profile summary",
        "",
        f"Evidence: {summary['evidence_label']}",
        f"Kernel time: {timeline.get('kernel_union_us', 0)} us union; {timeline.get('kernel_sum_us', 0)} us summed.",
        f"GPU samples: {gpu.get('sample_count', 0)}; energy: {gpu.get('energy_joules', 0)} J.",
        f"Semantic attribution coverage: {summary.get('attribution', {}).get('kernel_union_coverage', 0):.1%}.",
        "",
        "Summed kernel time is work, not wall time; overlapping streams are counted once in the union.",
    ]
    return "\n".join(lines) + "\n"


def analyze_profile(
    *,
    run_dir: Path,
    torch_trace: Path | None = None,
    nsys_sqlite: Path | None = None,
    ncu_csv: Path | None = None,
    rocprof_kernel_csv: Path | None = None,
    benchmark_path: Path | None = None,
    semantics_path: Path | None = None,
) -> dict[str, Any]:
    run_dir.mkdir(parents=True, exist_ok=True)
    timeline: dict[str, Any] = {"kernel_count": 0, "kernel_sum_us": 0.0, "kernel_union_us": 0.0, "top_kernels": []}
    kernels: list[dict[str, Any]] = []
    if torch_trace:
        timeline, kernels = _parse_torch_trace(torch_trace)
    elif nsys_sqlite:
        timeline, kernels = _parse_nsys_sqlite(nsys_sqlite)
    elif rocprof_kernel_csv:
        timeline, kernels = _parse_rocprof_kernel_csv(rocprof_kernel_csv)
    compute = _parse_ncu_csv(ncu_csv) if ncu_csv else None
    semantics = _load_json(semantics_path) if semantics_path else None
    benchmark = _load_json(benchmark_path) if benchmark_path else None
    gpu = _parse_gpu_samples(run_dir / "gpu_samples.csv")
    enriched_benchmark = _benchmark_economics(benchmark, gpu)
    summary = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "evidence_label": "measured profiler evidence; performance is scoreable only from a profiler-off benchmark",
        "timeline": timeline,
        "compute": compute,
        "gpu": gpu,
        "semantics": semantics,
        "attribution": _attribution(semantics, kernels),
        "benchmark": enriched_benchmark,
        "profiler_perturbation": _perturbation(benchmark),
    }
    _write_json(run_dir / "profile_summary.json", summary)
    (run_dir / "profile_summary.md").write_text(_summary_markdown(summary))
    return summary


def compare_profiles(control_path: Path, candidate_path: Path, output: Path | None = None) -> dict[str, Any]:
    control_summary = _load_json(control_path)
    candidate_summary = _load_json(candidate_path)
    if not isinstance(control_summary, dict) or not isinstance(candidate_summary, dict):
        raise ProfilingError("profile summaries must be JSON objects")
    control_benchmark = control_summary.get("benchmark") or {}
    candidate_benchmark = candidate_summary.get("benchmark") or {}
    control = {
        "output_tokens_per_second": control_benchmark.get("output_tokens_per_second"),
        "usd_per_million_output_tokens": control_benchmark.get("usd_per_million_output_tokens"),
        "kernel_union_us": control_summary.get("timeline", {}).get("kernel_union_us"),
        "energy_joules": control_summary.get("gpu", {}).get("energy_joules"),
    }
    candidate = {
        "output_tokens_per_second": candidate_benchmark.get("output_tokens_per_second"),
        "usd_per_million_output_tokens": candidate_benchmark.get("usd_per_million_output_tokens"),
        "kernel_union_us": candidate_summary.get("timeline", {}).get("kernel_union_us"),
        "energy_joules": candidate_summary.get("gpu", {}).get("energy_joules"),
    }
    metrics: dict[str, Any] = {}
    for name, control_value in control.items():
        candidate_value = candidate[name]
        if (
            isinstance(control_value, (int, float))
            and isinstance(candidate_value, (int, float))
            and control_value != 0
        ):
            metrics[name] = {
                "control": control_value,
                "candidate": candidate_value,
                "fraction_change": round(candidate_value / control_value - 1, 6),
            }
    result = {
        "schema_version": 1,
        "generated_at_utc": _utc_now(),
        "control_path": str(control_path),
        "candidate_path": str(candidate_path),
        "control": control,
        "candidate": candidate,
        "metrics": metrics,
        "interpretation": "Negative cost and energy changes are improvements; positive throughput changes are improvements.",
    }
    if output:
        _write_json(output, result)
    return result


def append_shape_record(atlas_path: Path, record: dict[str, Any]) -> dict[str, Any]:
    required = {"id", "captured_at_utc", "evidence_type", "model", "operation", "hardware", "software", "metrics", "artifacts"}
    missing = required - set(record)
    if missing:
        raise ProfilingError(f"shape record is missing: {', '.join(sorted(missing))}")
    if record["evidence_type"] not in {"measured", "analytical", "derived", "synthetic", "vendor_reported"}:
        raise ProfilingError("shape record evidence_type is unsupported")
    operation = record.get("operation", {})
    if not isinstance(operation.get("shapes"), dict) or not operation.get("dtype"):
        raise ProfilingError("shape record requires exact operation shapes and dtype")
    try:
        atlas = json.loads(atlas_path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ProfilingError(f"cannot read shape atlas: {error}") from error
    if atlas.get("schema_version") != 1 or not isinstance(atlas.get("records"), list):
        raise ProfilingError("shape atlas must use schema_version 1")
    if any(existing.get("id") == record["id"] for existing in atlas["records"]):
        return {"added": False, "record_id": record["id"], "record_count": len(atlas["records"])}
    normalized = dict(record)
    normalized["record_sha256"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    atlas["records"].append(normalized)
    _write_json(atlas_path, atlas)
    return {"added": True, "record_id": record["id"], "record_count": len(atlas["records"])}


def probe_host(output: Path) -> dict[str, Any]:
    commands = {
        "nvidia_smi": ["nvidia-smi", "-q"],
        "nvidia_topology": ["nvidia-smi", "topo", "-m"],
        "cpu": ["lscpu"],
        "amd_gpu": ["rocminfo"],
    }
    captures: dict[str, Any] = {}
    for name, command in commands.items():
        if not shutil.which(command[0]):
            captures[name] = {"available": False}
            continue
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
            captures[name] = {"available": True, "exit_code": result.returncode, "output": result.stdout[:200_000]}
        except (OSError, subprocess.TimeoutExpired) as error:
            captures[name] = {"available": True, "error": type(error).__name__}
    report = {
        "schema_version": 1,
        "captured_at_utc": _utc_now(),
        "tools": {
            tool: _tool_version(tool)
            for tool in (
                "nvidia-smi",
                "nsys",
                "ncu",
                "nvcc",
                "rocminfo",
                "amd-smi",
                "rocprofv3",
                "rocprof-compute",
                "cutlass_profiler",
                "nvbandwidth",
                "all_reduce_perf",
            )
        },
        "captures": captures,
        "environment_names": sorted(name for name in os.environ if name.startswith(("CUDA_", "NVIDIA_", "NCCL_"))),
    }
    _write_json(output, report)
    return report
