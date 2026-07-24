#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import pathlib
import tarfile
from typing import Any


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def deterministic_archive(path: pathlib.Path, files: list[tuple[pathlib.Path, str]]) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    with temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode="w:") as archive:
                for source, name in sorted(files, key=lambda item: item[1]):
                    data = source.read_bytes()
                    info = tarfile.TarInfo(name)
                    info.size = len(data)
                    info.mode = 0o444
                    info.mtime = 0
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    archive.addfile(info, io.BytesIO(data))
    os.replace(temporary, path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=pathlib.Path, required=True)
    parser.add_argument("--artifact-root", type=pathlib.Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    artifact_root = args.artifact_root.resolve()
    terminal_path = artifact_root / "ROUND_TRIP_TERMINAL.json"
    terminal = json.loads(terminal_path.read_text())
    external = {
        "awq_binding": project / "AWQ_QSERVE_BINDING.json",
        "awq_source_binding": project
        / "../gemma4_h200_mlp_w4_fp8_hybrid/MIXED_W4_FP8_BINDING.json",
        "awq_source_manifest": project
        / "../gemma4_h200_mlp_w4_fp8_hybrid/GPU_INPUT_MANIFEST.json",
        "awq_layer0_snapshot": project
        / "../gemma4_h200_mlp_w4_fp8_hybrid/inputs/layer0_mlp_awq.safetensors",
        "qserve_director_binding": project
        / "../gemma4_l40s_qserve_w4a8_mlp_component/DIRECTOR_BINDING.json",
        "qserve_mechanism_binding": project
        / "../gemma4_l40s_qserve_w4a8_mlp_component/MECHANISM_BINDING.json",
        "qserve_layout_reference": project
        / "../gemma4_l40s_qserve_w4a8_mlp_component/inputs/qserve_upstream_reference/w4a8_linear.py",
        "qserve_sm89_kernel": project
        / "../gemma4_l40s_qserve_w4a8_mlp_component/inputs/qserve_sm89/qserve_w4a8_gemm.cu",
    }
    programs = {
        "converter": project / "awq_to_qserve.py",
        "tests": project / "test_awq_to_qserve.py",
        "freezer": project / "freeze_packet.py",
    }
    manifest = {
        "schema_version": 1,
        "classification": terminal["classification"],
        "pass": terminal["pass"],
        "gpu_admission": terminal["gpu_admission"],
        "external_files": {
            name: {
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in external.items()
        },
        "programs": {
            name: {
                "path": str(path.relative_to(project)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
            for name, path in programs.items()
        },
        "result": {
            "path": str(terminal_path.relative_to(project)),
            "bytes": terminal_path.stat().st_size,
            "sha256": sha256(terminal_path),
        },
        "scope": {
            "calibration": False,
            "requantization": False,
            "gpu_invocation": False,
            "provider_mutation": False,
        },
    }
    manifest_path = artifact_root / "SOURCE_MANIFEST.json"
    atomic_json(manifest_path, manifest)
    packet_path = artifact_root / "OFFLINE_REJECTION_PACKET.tar.gz"
    archive_files = [
        (programs["converter"], "program/awq_to_qserve.py"),
        (programs["tests"], "program/test_awq_to_qserve.py"),
        (project / "AWQ_QSERVE_BINDING.json", "binding/AWQ_QSERVE_BINDING.json"),
        (terminal_path, "result/ROUND_TRIP_TERMINAL.json"),
        (manifest_path, "result/SOURCE_MANIFEST.json"),
    ]
    deterministic_archive(packet_path, archive_files)
    packet_record = {
        "schema_version": 1,
        "classification": "immutable_offline_rejection_packet",
        "gpu_admission": False,
        "path": str(packet_path.relative_to(project)),
        "bytes": packet_path.stat().st_size,
        "sha256": sha256(packet_path),
        "reason": terminal["classification"],
    }
    atomic_json(artifact_root / "IMMUTABLE_PACKET.json", packet_record)
    for path in (
        terminal_path,
        manifest_path,
        packet_path,
        artifact_root / "IMMUTABLE_PACKET.json",
    ):
        path.chmod(0o444)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
