#!/usr/bin/env python3
"""Guest-side bounded exact-target AR/DFLASH/NGRAM component worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
from typing import Any

IMAGE = "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
SOURCE_COMMIT = "f63458b5beaceabbd9d749b9fc956370e1b649e6"
SOURCE_ARCHIVE_SHA256 = "3b7c1c8a43a179c10020be8621465be9b7d07ff9353164054c77fd7791f3b8c1"
DRAFT_REPO = "z-lab/gemma-4-31B-it-DFlash"
DRAFT_REVISION = "eabd648301ce28583cc14757912e5e0f84e152e1"
DRAFT_CONFIG_SHA256 = "325f2a18894994b19f916e551b6f13a6904e961ae59a818d2b1dec18458e97f8"
DRAFT_WEIGHT_SHA256 = "b3f28580103d6e8a0a1d9389646957b9309df5982558afd754b9810357f425b7"
DRAFT_WEIGHT_BYTES = 3071941240
TARGET_MANIFEST_SHA256 = "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6"
RUNNER_SHA256 = "8672802c73137910c28e3c73be7b7f1c6152acc5899279cd8d36e3fd82783c03"
BLOCK_SIZE = 16


class Boundary(RuntimeError):
    def __init__(self, kind: str, message: str, recoverable: bool = True):
        super().__init__(f"{kind}:{message}")
        self.kind = kind
        self.message = message
        self.recoverable = recoverable


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    os.replace(temporary, path)


def load(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise Boundary("typed_json_boundary", f"{path}_not_object")
    return value


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remaining(deadline_epoch: float, cap: int, reserve: int = 120) -> int:
    value = int(deadline_epoch - time.time() - reserve)
    if value <= 0:
        raise Boundary("typed_deadline_boundary", "no_operation_time", False)
    return min(cap, value)


def run(
    command: list[str],
    *,
    deadline_epoch: float,
    cap: int,
    stdout: pathlib.Path | None = None,
    stderr: pathlib.Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        text=True,
        capture_output=stdout is None and stderr is None,
        stdout=None if stdout is None else stdout.open("a"),
        stderr=None if stderr is None else stderr.open("a"),
        timeout=remaining(deadline_epoch, cap),
        check=False,
    )
    if check and result.returncode:
        message = result.stderr[-2000:] if result.stderr else "see durable stderr"
        raise Boundary("typed_command_boundary", f"rc={result.returncode}:{message}")
    return result


def validate_packet(packet: pathlib.Path) -> None:
    manifest = load(packet / "PACKET_MANIFEST.json")
    for row in manifest["files"]:
        path = packet / row["path"]
        if not path.is_file():
            raise Boundary("typed_packet_boundary", f"missing:{row['path']}", False)
        if path.stat().st_size != row["bytes"] or sha256(path) != row["sha256"]:
            raise Boundary("typed_packet_boundary", f"identity:{row['path']}", False)
    if sha256(packet / "inputs" / "CHECKPOINT_MANIFEST.json") != TARGET_MANIFEST_SHA256:
        raise Boundary("typed_packet_boundary", "target_manifest_digest", False)
    if sha256(packet / "inputs" / "exact_c32_runner.py") != RUNNER_SHA256:
        raise Boundary("typed_packet_boundary", "runner_digest", False)


def hardlink_target_view(
    source: pathlib.Path, destination: pathlib.Path, packet: pathlib.Path
) -> dict[str, Any]:
    manifest = load(packet / "inputs" / "CHECKPOINT_MANIFEST.json")
    if manifest["total_bytes"] != 62578655208:
        raise Boundary("typed_target_boundary", "checkpoint_total_bytes", False)
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for item in manifest["files"]:
        src = source / item["name"]
        dst = destination / item["name"]
        if not src.is_file() or src.stat().st_size != item["bytes"]:
            raise Boundary("typed_target_boundary", f"missing_or_size:{item['name']}", False)
        if not dst.exists():
            os.link(src, dst)
        if not dst.is_file() or dst.stat().st_size != item["bytes"]:
            raise Boundary("typed_target_boundary", f"view_size:{item['name']}", False)
        if src.stat().st_ino != dst.stat().st_ino:
            raise Boundary(
                "typed_target_boundary", f"view_not_same_inode:{item['name']}", False
            )
        rows.append(
            {
                "name": item["name"],
                "bytes": item["bytes"],
                "source_inode": src.stat().st_ino,
                "view_inode": dst.stat().st_ino,
                "same_inode": src.stat().st_ino == dst.stat().st_ino,
            }
        )
    for item in manifest["files"]:
        if item["bytes"] < 100_000_000 and sha256(destination / item["name"]) != item["sha256"]:
            raise Boundary("typed_target_boundary", f"small_file_hash:{item['name']}", False)
    marker = {
        "schema_version": 1,
        "manifest_sha256": TARGET_MANIFEST_SHA256,
        "source": str(source),
        "project_local_read_only_hardlink_view": str(destination),
        "files": rows,
        "full_weight_hash_reuse": (
            "Bench-owned immutable checkpoint was already verified under this exact "
            "manifest; unchanged same-inode hard links preserve that storage identity."
        ),
    }
    atomic(destination.parent / "TARGET_INTEGRITY.json", marker)
    return marker


def materialize_source(packet: pathlib.Path, root: pathlib.Path) -> pathlib.Path:
    archive = packet / "inputs" / "sglang-f63458b5.tar"
    if sha256(archive) != SOURCE_ARCHIVE_SHA256:
        raise Boundary("typed_source_boundary", "archive_digest", False)
    destination = root / f"sglang-{SOURCE_COMMIT}"
    marker = destination / ".PROJECT_SOURCE_IDENTITY.json"
    if marker.is_file() and load(marker).get("archive_sha256") == SOURCE_ARCHIVE_SHA256:
        return destination
    temporary = destination.with_name(destination.name + ".part")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        bundle.extractall(temporary, filter="data")
    extracted = temporary / "sglang-f63458b5"
    expected = {
        "python/sglang/srt/models/dflash.py": "ddbcf49c4e8d93673509d2627d28184c158d47202dc63ef070ae90ec3423829d",
        "python/sglang/srt/speculative/dflash_info.py": "5f65c04014f3ef19605900f14afb555a1dd4286c967f4c54289e2f501a961bed",
        "python/sglang/srt/speculative/dflash_worker_v2.py": "bc3574717734f7c98261e4d1567fae04f3388b45e8e328a49142ae5f4721520d",
    }
    for relative, digest in expected.items():
        if sha256(extracted / relative) != digest:
            raise Boundary("typed_source_boundary", f"source_hash:{relative}", False)
    atomic(
        extracted / ".PROJECT_SOURCE_IDENTITY.json",
        {
            "schema_version": 1,
            "commit": SOURCE_COMMIT,
            "archive_sha256": SOURCE_ARCHIVE_SHA256,
            "source_files": expected,
        },
    )
    if destination.exists():
        raise Boundary("typed_source_boundary", "conflicting_finalized_source", False)
    os.replace(extracted, destination)
    shutil.rmtree(temporary)
    return destination


def validate_draft(path: pathlib.Path) -> bool:
    config = path / "config.json"
    weight = path / "model.safetensors"
    return (
        config.is_file()
        and weight.is_file()
        and weight.stat().st_size == DRAFT_WEIGHT_BYTES
        and sha256(config) == DRAFT_CONFIG_SHA256
        and sha256(weight) == DRAFT_WEIGHT_SHA256
    )


def materialize_draft(
    root: pathlib.Path, deadline_epoch: float, evidence: pathlib.Path
) -> pathlib.Path:
    destination = root / f"draft-{DRAFT_REVISION}"
    if destination.exists():
        if validate_draft(destination):
            return destination
        raise Boundary("typed_draft_boundary", "conflicting_finalized_draft", False)
    temporary = destination.with_name(destination.name + ".part")
    temporary.mkdir(parents=True, exist_ok=True)
    code = (
        "from huggingface_hub import snapshot_download;"
        f"snapshot_download(repo_id={DRAFT_REPO!r},revision={DRAFT_REVISION!r},"
        "local_dir='/out',allow_patterns=['config.json','model.safetensors'])"
    )
    run(
        [
            "sudo",
            "-n",
            "docker",
            "run",
            "--rm",
            "-v",
            f"{temporary}:/out",
            IMAGE,
            "python3",
            "-c",
            code,
        ],
        deadline_epoch=deadline_epoch,
        cap=900,
        stdout=evidence / "draft-stage.stdout",
        stderr=evidence / "draft-stage.stderr",
    )
    if not validate_draft(temporary):
        raise Boundary("typed_draft_boundary", "downloaded_identity_mismatch", False)
    atomic(
        temporary / "PROJECT_DRAFT_IDENTITY.json",
        {
            "schema_version": 1,
            "repo": DRAFT_REPO,
            "revision": DRAFT_REVISION,
            "config_sha256": DRAFT_CONFIG_SHA256,
            "weight_sha256": DRAFT_WEIGHT_SHA256,
            "weight_bytes": DRAFT_WEIGHT_BYTES,
        },
    )
    os.replace(temporary, destination)
    return destination


def server_command(
    arm: str,
    source: pathlib.Path,
    target: pathlib.Path,
    draft: pathlib.Path,
    packet: pathlib.Path,
    arm_root: pathlib.Path,
    generation: str,
) -> list[str]:
    command = [
        "sudo",
        "-n",
        "docker",
        "run",
        "-d",
        "--gpus",
        "all",
        "--ipc=host",
        "--network=host",
        "--name",
        f"dflash-component-{arm}-{generation}",
        "-v",
        f"{source}:/source:ro",
        "-v",
        f"{target}:/models/target:ro",
        "-v",
        f"{packet}:/packet:ro",
        "-v",
        f"{arm_root}:/out",
        "-e",
        "PYTHONPATH=/packet:/source/python",
        "-e",
        f"DFLASH_COMPONENT_OBSERVER_ROOT=/out/observer",
        "-e",
        f"DFLASH_COMPONENT_ARM={arm}",
        "-e",
        f"DFLASH_COMPONENT_GENERATION={generation}",
    ]
    if arm == "dflash":
        command.extend(["-v", f"{draft}:/models/draft:ro"])
    command.extend(
        [
            IMAGE,
            "python3",
            "-m",
            "sglang.launch_server",
            "--model-path",
            "/models/target",
            "--tokenizer-path",
            "/models/target",
            "--served-model-name",
            "google/gemma-4-31B-it",
            "--dtype",
            "bfloat16",
            "--quantization",
            "fp8",
            "--tp-size",
            "1",
            "--kv-cache-dtype",
            "fp8_e5m2",
            "--context-length",
            "5000",
            "--max-running-requests",
            "32",
            "--mem-fraction-static",
            "0.85",
            "--enable-metrics",
            "--skip-server-warmup",
            "--enable-dynamic-chunking",
            "--chunked-prefill-size",
            "2048",
            "--enable-fused-qk-norm-rope",
            "--cuda-graph-max-bs",
            "32",
            "--prefill-attention-backend",
            "triton",
            "--decode-attention-backend",
            "triton",
            "--page-size",
            "16",
            "--host",
            "0.0.0.0",
            "--port",
            "30000",
        ]
    )
    if arm == "dflash":
        command.extend(
            [
                "--speculative-algorithm",
                "DFLASH",
                "--speculative-draft-model-path",
                "/models/draft",
                "--speculative-draft-model-revision",
                DRAFT_REVISION,
                "--speculative-dflash-block-size",
                str(BLOCK_SIZE),
                "--speculative-num-draft-tokens",
                str(BLOCK_SIZE),
                "--speculative-draft-attention-backend",
                "flashinfer",
            ]
        )
    elif arm == "ngram":
        command.extend(
            [
                "--speculative-algorithm",
                "NGRAM",
                "--speculative-num-draft-tokens",
                str(BLOCK_SIZE),
            ]
        )
    return command


def container_live(name: str, deadline_epoch: float) -> bool:
    result = run(
        ["sudo", "-n", "docker", "inspect", "-f", "{{.State.Running}}", name],
        deadline_epoch=deadline_epoch,
        cap=20,
        check=False,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def wait_health(name: str, deadline_epoch: float, arm_root: pathlib.Path) -> None:
    health_deadline = min(deadline_epoch - 180, time.time() + 900)
    last_error = ""
    while time.time() < health_deadline:
        if not container_live(name, deadline_epoch):
            run(
                ["sudo", "-n", "docker", "logs", name],
                deadline_epoch=deadline_epoch,
                cap=30,
                stdout=arm_root / "server.log",
                stderr=arm_root / "server.log",
                check=False,
            )
            raise Boundary("server_startup_defect", f"{name}_exited")
        try:
            payload = urllib.request.urlopen(
                "http://127.0.0.1:30000/v1/models", timeout=5
            ).read()
            (arm_root / "MODELS.json").write_bytes(payload)
            return
        except Exception as error:
            last_error = f"{type(error).__name__}: {error}"
            time.sleep(2)
    raise Boundary("server_readiness_defect", last_error)


def stop_server(name: str, deadline_epoch: float, arm_root: pathlib.Path) -> None:
    run(
        ["sudo", "-n", "docker", "logs", name],
        deadline_epoch=deadline_epoch,
        cap=60,
        stdout=arm_root / "server.log",
        stderr=arm_root / "server.log",
        check=False,
    )
    run(
        ["sudo", "-n", "docker", "stop", "-t", "30", name],
        deadline_epoch=deadline_epoch,
        cap=60,
        check=False,
    )
    run(
        ["sudo", "-n", "docker", "rm", "-f", name],
        deadline_epoch=deadline_epoch,
        cap=30,
        check=False,
    )


def run_arm(
    arm: str,
    *,
    source: pathlib.Path,
    target: pathlib.Path,
    draft: pathlib.Path,
    packet: pathlib.Path,
    root: pathlib.Path,
    generation: str,
    deadline_epoch: float,
) -> None:
    arm_root = root / arm
    terminal = arm_root / "results" / "TERMINAL.json"
    if terminal.is_file():
        value = load(terminal)
        if value.get("complete_requests") == 32:
            return
        raise Boundary("arm_consumption_unknown", f"{arm}_terminal_incomplete")
    if (root / f"{arm}.SCIENCE_STARTED.json").exists():
        raise Boundary("arm_consumption_unknown", f"{arm}_started_without_terminal")
    arm_root.mkdir(parents=True, exist_ok=False)
    (arm_root / "observer").mkdir()
    name = f"dflash-component-{arm}-{generation}"
    start = run(
        server_command(arm, source, target, draft, packet, arm_root, generation),
        deadline_epoch=deadline_epoch,
        cap=60,
    )
    atomic(
        arm_root / "SERVER_SUBMITTED.json",
        {
            "schema_version": 1,
            "arm": arm,
            "container": name,
            "container_id": start.stdout.strip(),
            "image": IMAGE,
            "runtime_commit": SOURCE_COMMIT,
            "block_size": BLOCK_SIZE,
        },
    )
    try:
        wait_health(name, deadline_epoch, arm_root)
        driver_command = [
            "sudo",
            "-n",
            "docker",
            "run",
            "--rm",
            "--network=host",
            "-v",
            f"{packet}:/packet:ro",
            "-v",
            f"{root}:/run",
            IMAGE,
            "python3",
            "/packet/run_bound_c32.py",
            "--runner",
            "/packet/inputs/exact_c32_runner.py",
            "--output",
            f"/run/{arm}/results",
            "--arm",
            arm,
            "--generation",
            generation,
            "--marker-root",
            "/run",
        ]
        with (arm_root / "driver.stdout").open("w") as out, (
            arm_root / "driver.stderr"
        ).open("w") as err:
            process = subprocess.Popen(driver_command, stdout=out, stderr=err, text=True)
            driver_deadline = min(deadline_epoch - 150, time.time() + 1200)
            while process.poll() is None and time.time() < driver_deadline:
                if (arm_root / "observer" / "OBSERVER_DIAGNOSTIC.json").exists():
                    process.terminate()
                    process.wait(timeout=20)
                    raise Boundary("observer_integration_defect", f"{arm}_diagnostic")
                if not container_live(name, deadline_epoch):
                    process.terminate()
                    process.wait(timeout=20)
                    raise Boundary("server_runtime_defect", f"{arm}_server_exited")
                time.sleep(1)
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=20)
                raise Boundary("arm_timeout", arm)
            if process.returncode:
                raise Boundary("driver_integration_defect", f"{arm}:rc={process.returncode}")
        if not terminal.is_file():
            raise Boundary("terminal_retrieval_defect", f"{arm}_terminal_missing")
        value = load(terminal)
        if value.get("complete_requests") != 32:
            raise Boundary("incomplete_scientific_result", arm)
    finally:
        stop_server(name, deadline_epoch, arm_root)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-root", type=pathlib.Path, required=True)
    parser.add_argument("--remote-root", type=pathlib.Path, required=True)
    parser.add_argument("--target-source", type=pathlib.Path, required=True)
    parser.add_argument("--deadline-epoch", type=float, required=True)
    parser.add_argument("--generation", required=True)
    parser.add_argument(
        "--retry-scope",
        choices=("all", "ar", "dflash", "ngram", "summarize"),
        default="all",
    )
    args = parser.parse_args()
    packet = args.packet_root.resolve()
    root = args.remote_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    terminal_path = root / "REMOTE_TERMINAL.json"
    if terminal_path.exists():
        raise SystemExit("remote terminal already finalized")
    try:
        validate_packet(packet)
        source = materialize_source(packet, root / "immutable")
        target = root / "immutable" / "target"
        target_marker = hardlink_target_view(args.target_source, target, packet)
        draft = materialize_draft(root / "immutable", args.deadline_epoch, root)
        atomic(
            root / "PRE_SCIENCE_IDENTITY.json",
            {
                "schema_version": 1,
                "runtime_commit": SOURCE_COMMIT,
                "source_archive_sha256": SOURCE_ARCHIVE_SHA256,
                "target_manifest_sha256": TARGET_MANIFEST_SHA256,
                "target": target_marker,
                "draft_repo": DRAFT_REPO,
                "draft_revision": DRAFT_REVISION,
                "draft_config_sha256": DRAFT_CONFIG_SHA256,
                "draft_weight_sha256": DRAFT_WEIGHT_SHA256,
                "draft_weight_bytes": DRAFT_WEIGHT_BYTES,
                "runner_sha256": RUNNER_SHA256,
                "block_size_including_current": BLOCK_SIZE,
                "historical_request_25_replayed": False,
            },
        )
        scopes = (
            ("ar", "dflash", "ngram")
            if args.retry_scope == "all"
            else ()
            if args.retry_scope == "summarize"
            else (args.retry_scope,)
        )
        for arm in scopes:
            run_arm(
                arm,
                source=source,
                target=target,
                draft=draft,
                packet=packet,
                root=root,
                generation=args.generation,
                deadline_epoch=args.deadline_epoch,
            )
        summary = root / "COMPONENT_TERMINAL.json"
        result = run(
            [
                sys.executable,
                str(packet / "summarize_component.py"),
                "--root",
                str(root),
                "--terminal",
                str(summary),
                "--generation",
                args.generation,
            ],
            deadline_epoch=args.deadline_epoch,
            cap=60,
            stdout=root / "summarize.stdout",
            stderr=root / "summarize.stderr",
            check=False,
        )
        summary_value = load(summary) if summary.exists() else {}
        if result.returncode == 75:
            raise Boundary(
                "consumer_integration_defect",
                "component ledger incomplete after completed producer arms",
            )
        if result.returncode:
            raise Boundary("consumer_integration_defect", f"summarizer_rc={result.returncode}")
        atomic(
            terminal_path,
            {
                "schema_version": 1,
                "classification": summary_value["classification"],
                "scientific_terminal": True,
                "science_consumed": summary_value["science_consumed"],
                "component_terminal": str(summary),
                "component_terminal_sha256": sha256(summary),
                "historical_request_25_replayed": False,
            },
        )
        return 0
    except Boundary as error:
        atomic(
            root / "REMOTE_ATTEMPT.json",
            {
                "schema_version": 1,
                "classification": error.kind,
                "message": error.message,
                "recoverable": error.recoverable,
                "science_started": {
                    arm: (root / f"{arm}.SCIENCE_STARTED.json").exists()
                    for arm in ("ar", "dflash", "ngram")
                },
                "scientific_terminal": False,
            },
        )
        return 75 if error.recoverable else 76


if __name__ == "__main__":
    raise SystemExit(main())
