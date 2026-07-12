from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from validation.scalesim_adapter.normalize import (
    REQUEST_SCHEMA_VERSION,
    build_report,
)


PROBE_SCHEMA_VERSION = "inference-foundry.scalesim-v3-probe.v1"
CASE_TIMEOUT_SECONDS = 300


def render_topology(workload: dict[str, object]) -> str:
    identifier = _safe_id(workload.get("id"), "workload id")
    dimensions = _object(workload, "dimensions")
    batch = _positive_integer(dimensions.get("batch"), "batch")
    if batch != 1:
        raise ValueError("SCALE-Sim smoke topology requires batch equal to one")
    m = _positive_integer(dimensions.get("m"), "m")
    n = _positive_integer(dimensions.get("n"), "n")
    k = _positive_integer(dimensions.get("k"), "k")
    return f"Layer Name, M, N, K,\n{identifier}, {m}, {n}, {k},\n"


def render_layout(workload_id: str) -> str:
    identifier = _safe_id(workload_id, "workload id")
    header = (
        "Layer name, IFMAP Height Intraline Factor, IFMAP Width Intraline Factor, "
        "Filter Height Intraline Factor, Filter Width Intraline Factor, "
        "Channel Intraline Factor, Num Filter Intraline Factor, "
        "IFMAP Height Intraline Order, IFMAP Width Intraline Order, "
        "Channel Intraline Order, IFMAP Height Interline Order, "
        "IFMAP Width Interline Order, Channel Interline Order, "
        "Num Filter Intraline Order, Channel Intraline Order, "
        "Filter Height Intraline Order, Filter Width Intraline Order, "
        "Num Filter Interline Order, Channel Interline Order, "
        "Filter Height Interline Order, Filter Width Interline Order,"
    )
    values = "1,1,1,1,1,1,2,1,0,5,4,3,3,0,1,2,7,4,5,6"
    return f"{header}\n{identifier},{values},\n"


def render_config(workload_id: str, architecture: dict[str, object]) -> str:
    workload = _safe_id(workload_id, "workload id")
    architecture_id = _safe_id(architecture.get("id"), "architecture id")
    array_height = _positive_integer(architecture.get("array_height"), "array_height")
    array_width = _positive_integer(architecture.get("array_width"), "array_width")
    ifmap_sram_kb = _positive_integer(
        architecture.get("ifmap_sram_kb"), "ifmap_sram_kb"
    )
    filter_sram_kb = _positive_integer(
        architecture.get("filter_sram_kb"), "filter_sram_kb"
    )
    ofmap_sram_kb = _positive_integer(
        architecture.get("ofmap_sram_kb"), "ofmap_sram_kb"
    )
    dataflow = _string(architecture.get("dataflow"), "dataflow")
    if dataflow not in {"ws", "is", "os"}:
        raise ValueError(f"unsupported dataflow: {dataflow}")
    interface_bandwidth = _string(
        architecture.get("interface_bandwidth"), "interface_bandwidth"
    )
    if interface_bandwidth != "CALC":
        raise ValueError("SCALE-Sim smoke runner only permits CALC bandwidth mode")
    return (
        "[general]\n"
        f"run_name = {workload}__{architecture_id}\n\n"
        "[architecture_presets]\n"
        f"ArrayHeight = {array_height}\n"
        f"ArrayWidth = {array_width}\n"
        f"IfmapSramSzkB = {ifmap_sram_kb}\n"
        f"FilterSramSzkB = {filter_sram_kb}\n"
        f"OfmapSramSzkB = {ofmap_sram_kb}\n"
        "IfmapOffset = 0\n"
        "FilterOffset = 100000000\n"
        "OfmapOffset = 200000000\n"
        "Bandwidth = 10\n"
        f"Dataflow = {dataflow}\n"
        "MemoryBanks = 1\n"
        "ReadRequestBuffer = 32\n"
        "WriteRequestBuffer = 32\n\n"
        "[layout]\n"
        "IfmapCustomLayout = False\n"
        "IfmapSRAMBankBandwidth = 10\n"
        "IfmapSRAMBankNum = 10\n"
        "IfmapSRAMBankPort = 2\n"
        "FilterCustomLayout = False\n"
        "FilterSRAMBankBandwidth = 10\n"
        "FilterSRAMBankNum = 10\n"
        "FilterSRAMBankPort = 2\n\n"
        "[sparsity]\n"
        "SparsitySupport = false\n"
        "SparseRep = ellpack_block\n"
        "OptimizedMapping = false\n"
        "BlockSize = 8\n"
        "RandomNumberGeneratorSeed = 40\n\n"
        "[run_presets]\n"
        f"InterfaceBandwidth = {interface_bandwidth}\n"
        "UseRamulatorTrace = False\n"
    )


def run_sweep(
    request_path: Path,
    source_root: Path,
    raw_root: Path,
    output_path: Path,
) -> dict[str, object]:
    request = _load_object(request_path)
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        raise ValueError(f"unsupported request schema: {request.get('schema_version')}")
    tool = _object(request, "tool")
    probe = _probe_source(source_root, tool)
    if raw_root.exists():
        shutil.rmtree(raw_root)
    raw_root.mkdir(parents=True)
    _write_json(raw_root / "probe.json", probe)
    workloads = _object_array(request, "workloads")
    architectures = _object_array(request, "architectures")
    for workload in workloads:
        for architecture in architectures:
            _run_case(source_root, raw_root, workload, architecture)
    report = build_report(request_path, raw_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(output_path, report)
    return report


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run a pinned SCALE-Sim v3 GEMM sweep."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(arguments)
    try:
        report = run_sweep(args.request, args.source_root, args.raw_root, args.output)
    except (
        FileNotFoundError,
        KeyError,
        OSError,
        subprocess.SubprocessError,
        TypeError,
        ValueError,
    ) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "content_id": report["content_identity_sha256"],
                "output": str(args.output),
                "status": report["status"],
            },
            sort_keys=True,
        )
    )
    return 0


def _run_case(
    source_root: Path,
    raw_root: Path,
    workload: dict[str, object],
    architecture: dict[str, object],
) -> None:
    workload_id = _safe_id(workload.get("id"), "workload id")
    architecture_id = _safe_id(architecture.get("id"), "architecture id")
    case_root = raw_root / workload_id / architecture_id
    input_root = case_root / "input"
    output_root = case_root / "output"
    input_root.mkdir(parents=True)
    output_root.mkdir()
    config_path = input_root / "config.cfg"
    topology_path = input_root / "topology.csv"
    layout_path = input_root / "layout.csv"
    config_path.write_text(render_config(workload_id, architecture), encoding="utf-8")
    topology_path.write_text(render_topology(workload), encoding="utf-8")
    layout_path.write_text(render_layout(workload_id), encoding="utf-8")
    command = [
        sys.executable,
        "-m",
        "validation.scalesim_adapter.driver",
        "--config",
        str(config_path),
        "--topology",
        str(topology_path),
        "--layout",
        str(layout_path),
        "--output",
        str(output_root),
    ]
    environment = os.environ.copy()
    repository_root = Path(__file__).resolve().parents[2]
    environment["PYTHONPATH"] = os.pathsep.join(
        [
            str(source_root.resolve()),
            str(repository_root),
            environment.get("PYTHONPATH", ""),
        ]
    )
    try:
        process = subprocess.run(
            command,
            cwd=repository_root,
            env=environment,
            capture_output=True,
            timeout=CASE_TIMEOUT_SECONDS,
            check=False,
        )
        exit_code = process.returncode
        stdout = process.stdout
        stderr = process.stderr
        status = "succeeded" if exit_code == 0 else "nonzero_exit"
    except subprocess.TimeoutExpired as error:
        exit_code = 124
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        status = "timed_out"
    (case_root / "stdout.txt").write_bytes(stdout)
    (case_root / "stderr.txt").write_bytes(stderr)
    _write_json(
        case_root / "process.json",
        {
            "schema_version": "inference-foundry.scalesim-v3-process.v1",
            "status": status,
            "exit_code": exit_code,
            "timeout_seconds": CASE_TIMEOUT_SECONDS,
            "command": [
                "python",
                "-m",
                "validation.scalesim_adapter.driver",
                "--config",
                "input/config.cfg",
                "--topology",
                "input/topology.csv",
                "--layout",
                "input/layout.csv",
                "--output",
                "output",
            ],
        },
    )
    if exit_code != 0:
        raise ValueError(
            f"SCALE-Sim process failed for {workload_id}/{architecture_id} with status {status}"
        )


def _probe_source(source_root: Path, tool: dict[str, object]) -> dict[str, object]:
    revision = subprocess.run(
        ["git", "-C", str(source_root), "rev-parse", "HEAD"],
        capture_output=True,
        check=True,
        text=True,
        timeout=30,
    ).stdout.strip()
    expected_revision = _string(tool.get("revision"), "tool revision")
    if revision != expected_revision:
        raise ValueError(
            f"SCALE-Sim revision mismatch: expected {expected_revision}, found {revision}"
        )
    setup_path = source_root / "setup.py"
    setup_source = setup_path.read_text(encoding="utf-8")
    match = re.search(r"version=['\"]([^'\"]+)['\"]", setup_source)
    version = match.group(1) if match else ""
    expected_version = _string(tool.get("version"), "tool version")
    if version != expected_version:
        raise ValueError(
            f"SCALE-Sim version mismatch: expected {expected_version}, found {version}"
        )
    license_sha256 = _sha256_file(source_root / "LICENSE")
    expected_license = _string(tool.get("license_sha256"), "tool license_sha256")
    if license_sha256 != expected_license:
        raise ValueError("SCALE-Sim license hash mismatch")
    return {
        "schema_version": PROBE_SCHEMA_VERSION,
        "revision": revision,
        "version": version,
        "license_sha256": license_sha256,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "scale_sim_source_sha256": _sha256_file(source_root / "scalesim/scale_sim.py"),
        "setup_sha256": _sha256_file(setup_path),
    }


def _load_object(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON document must be an object: {path}")
    return value


def _object(document: dict[str, object], key: str) -> dict[str, object]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be an object")
    return value


def _object_array(document: dict[str, object], key: str) -> list[dict[str, object]]:
    value = document.get(key)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{key} must be a non-empty array")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError(f"{key} entries must be objects")
    return value


def _write_json(path: Path, value: object) -> None:
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def _positive_integer(value: object, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _safe_id(value: object, label: str) -> str:
    result = _string(value, label)
    if any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_."
        for character in result
    ):
        raise ValueError(f"{label} contains unsupported characters: {result}")
    if result in {".", ".."}:
        raise ValueError(f"{label} is not safe: {result}")
    return result


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
