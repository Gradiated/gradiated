#!/usr/bin/env python3
"""Build one content-addressed request-25 DFlash boundary-probe packet."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
ARTIFACT_ROOT = ROOT / "artifacts" / "request25-boundary-probe-preparation-20260726"
COMMIT = "588d1f7bc9424201f89957e145f9d5af633a3eb8"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)

SOURCE_FILES = {
    "dflash_info.py": (
        "python/sglang/srt/speculative/dflash_info.py",
        "f17c37c1d0047e75f3214ec67cf2b02dd52cfcec35cf0daaaee0407f892a0e53",
    ),
    "dflash_info_v2.py": (
        "python/sglang/srt/speculative/dflash_info_v2.py",
        "eb976179a5ec54d607bfaf66e087c04d1c39617f312c105081974a3a8aa9de08",
    ),
    "dflash_utils.py": (
        "python/sglang/srt/speculative/dflash_utils.py",
        "f6935ff13d8b0c24ab2b443509ba8425918f8b4a6fafc520cd8a875f91891030",
    ),
    "dflash_worker_v2.py": (
        "python/sglang/srt/speculative/dflash_worker_v2.py",
        "8fbddb39f4b33b4ac55b1919bc58fa846acb60892886199251d3592a5223050f",
    ),
    "forward_batch_info.py": (
        "python/sglang/srt/model_executor/forward_batch_info.py",
        "c977296f3b90be69fff5312f2b3af7699a17b20af24614b139f69888e5776516",
    ),
    "memory_pool.py": (
        "python/sglang/srt/mem_cache/memory_pool.py",
        "26ce123db5991db93f5d93fa6ca28cb360a7402a7ef0ed0e7315a3d3b37bb363",
    ),
    "swa_memory_pool.py": (
        "python/sglang/srt/mem_cache/swa_memory_pool.py",
        "fefdcaf49b78b252f68cbddc21cd3f2640c9c50c28052d231116c1d1eec7bac1",
    ),
    "tp_worker.py": (
        "python/sglang/srt/managers/tp_worker.py",
        "f2e00ea7d53b7250231d44b9d52415c6f6b5f936b0e7c6af4a13f5aff6c1e509",
    ),
}

PACKET_INPUTS = [
    "DIRECTOR_REQUEST25_BOUNDARY_PROBE_PREPARATION_20260726.json",
    "DFLASH_FIRST_TARGET_VERIFIER_CAUSAL_REPAIR_TERMINAL.json",
    "DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch",
    "dflash_endpoint_runner.py",
    "request25_boundary_probe.py",
    "request25_payload_adapter.py",
    "request25_boundary_probe_sitecustomize.py",
    "test_request25_boundary_probe.py",
]


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def write_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def run(*args: str, cwd: pathlib.Path | None = None) -> str:
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def materialize_checkout(checkout: pathlib.Path | None) -> tuple[pathlib.Path, object]:
    if checkout is not None:
        return checkout, None
    temporary = tempfile.TemporaryDirectory(prefix="request25-source-")
    path = pathlib.Path(temporary.name)
    run("git", "init", "-q", cwd=path)
    run(
        "git",
        "remote",
        "add",
        "origin",
        "https://github.com/sgl-project/sglang.git",
        cwd=path,
    )
    run("git", "fetch", "-q", "--depth=1", "origin", COMMIT, cwd=path)
    run("git", "checkout", "-q", "--detach", "FETCH_HEAD", cwd=path)
    run(
        "git",
        "apply",
        str(ROOT / "DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch"),
        cwd=path,
    )
    return path, temporary


def verify_checkout(checkout: pathlib.Path) -> list[dict[str, object]]:
    if run("git", "rev-parse", "HEAD", cwd=checkout) != COMMIT:
        raise RuntimeError("source checkout is not the pinned SGLang commit")
    diff_names = run("git", "diff", "--name-only", cwd=checkout).splitlines()
    if diff_names != ["python/sglang/srt/speculative/dflash_info_v2.py"]:
        raise RuntimeError(f"unexpected source modifications: {diff_names}")
    entries: list[dict[str, object]] = []
    for packet_name, (source_name, expected) in SOURCE_FILES.items():
        source = checkout / source_name
        observed = sha256(source)
        if observed != expected:
            raise RuntimeError(
                f"{source_name} hash {observed} differs from executed {expected}"
            )
        entries.append(
            {
                "packet_path": f"executed_source/{packet_name}",
                "source_path": source_name,
                "sha256": observed,
                "bytes": source.stat().st_size,
                "recovery": (
                    "pinned_commit_plus_bound_relay_patch"
                    if packet_name == "dflash_info_v2.py"
                    else "pinned_commit"
                ),
            }
        )
    return entries


def content_entries(root: pathlib.Path) -> list[dict[str, object]]:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        relative = path.relative_to(root).as_posix()
        entries.append(
            {
                "path": relative,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
        )
    return entries


def deterministic_tar(source: pathlib.Path, target: pathlib.Path) -> None:
    with tarfile.open(target, "w", format=tarfile.PAX_FORMAT) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            info = archive.gettarinfo(str(path), arcname=path.relative_to(source))
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = 0
            with path.open("rb") as handle:
                archive.addfile(info, handle)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkout", type=pathlib.Path)
    args = parser.parse_args()

    checkout, temporary = materialize_checkout(args.source_checkout)
    try:
        source_entries = verify_checkout(checkout)
        if ARTIFACT_ROOT.exists():
            raise RuntimeError(f"artifact root already exists: {ARTIFACT_ROOT}")
        staging = ARTIFACT_ROOT / "staging"
        executed = staging / "executed_source"
        observer = staging / "observer"
        contract = staging / "contract"
        executed.mkdir(parents=True)
        observer.mkdir()
        contract.mkdir()

        for packet_name, (source_name, _) in SOURCE_FILES.items():
            shutil.copyfile(checkout / source_name, executed / packet_name)
        for name in PACKET_INPUTS:
            destination = (
                observer / name
                if name.startswith(("request25_", "test_request25_"))
                or name == "dflash_endpoint_runner.py"
                else contract / name
            )
            shutil.copyfile(ROOT / name, destination)

        source_binding = {
            "schema_version": 1,
            "runtime_commit": COMMIT,
            "runtime_image_lineage": IMAGE,
            "recovery": {
                "upstream_repo": "https://github.com/sgl-project/sglang.git",
                "relay_patch_path": "contract/DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch",
                "relay_patch_sha256": sha256(
                    ROOT / "DFLASH_REQUEST_INDEXED_RELAY_REPAIR.patch"
                ),
                "executed_dflash_info_v2_observed_sha256": (
                    "eb976179a5ec54d607bfaf66e087c04d1c39617f312c105081974a3a8aa9de08"
                ),
                "reconstruction_matches_observed": True,
            },
            "executed_source": source_entries,
            "trace_anchors": {
                "worker_sha256": SOURCE_FILES["dflash_worker_v2.py"][1],
                "pre_forward_line": 528,
                "raw_pre_adjustment_line": 537,
                "post_adjustment_line": 544,
                "packaging_symbol": "DFlashVerifyInput.prepare_for_v2_verify",
                "logit_adjustment_symbol": (
                    "apply_dflash_verify_logits_adjustments"
                ),
            },
            "request25": {
                "index": 25,
                "semantic_request_sha256": (
                    "ee2edfa7a9ff571b0268966f506c4cb868868ab880ac87c2684b055d48a0e150"
                ),
                "input_ids_sha256": (
                    "51a23cdfb44941cb799a80c7ca3fd7f859e8558405f70976d1f8508703f6b360"
                ),
                "selector": (
                    "match exact Req.origin_input_ids digest once, then follow "
                    "the existing runtime-generated Req.rid"
                ),
                "request_body_mutated": False,
            },
        }
        source_binding_sha = hashlib.sha256(canonical(source_binding)).hexdigest()
        source_binding["source_binding_sha256"] = source_binding_sha
        write_json(staging / "SOURCE_BINDING.json", source_binding)

        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["REQUEST25_FIXTURE_SOURCE_ROOT"] = str(executed)
        environment["PYTHONPATH"] = str(observer)
        fixture = subprocess.run(
            ["python3", str(observer / "test_request25_boundary_probe.py"), "-v"],
            env=environment,
            text=True,
            capture_output=True,
            check=True,
        )
        (staging / "FIXTURE_STDOUT.txt").write_text(fixture.stdout)
        (staging / "FIXTURE_STDERR.txt").write_text(fixture.stderr)
        fixture_result = {
            "schema_version": 1,
            "status": "pass",
            "tests": 7,
            "cuda_invoked": False,
            "gpu_claimed": False,
            "endpoint_replayed": False,
        }
        write_json(staging / "FIXTURE_RESULT.json", fixture_result)

        files = content_entries(staging)
        identity = hashlib.sha256(canonical(files)).hexdigest()
        packet_root = ARTIFACT_ROOT / "packet" / identity
        packet_root.parent.mkdir(parents=True)
        staging.replace(packet_root)
        manifest = {
            "schema_version": 1,
            "packet_identity_sha256": identity,
            "source_binding_sha256": source_binding_sha,
            "files": files,
        }
        write_json(ARTIFACT_ROOT / "PACKET_MANIFEST.json", manifest)
        archive = ARTIFACT_ROOT / f"{identity}.tar"
        deterministic_tar(packet_root, archive)
        archive_sha = sha256(archive)

        result = {
            "schema_version": 1,
            "created_at_utc": dt.datetime.now(dt.UTC).isoformat().replace("+00:00", "Z"),
            "classification": "source_complete_boundary_probe_ready",
            "packet": {
                "path": str(packet_root.relative_to(ROOT)),
                "identity_sha256": identity,
                "manifest": str(
                    (ARTIFACT_ROOT / "PACKET_MANIFEST.json").relative_to(ROOT)
                ),
                "archive": str(archive.relative_to(ROOT)),
                "archive_sha256": archive_sha,
                "source_binding_sha256": source_binding_sha,
                "bytes": sum(int(item["bytes"]) for item in files),
            },
            "quality_gate": {
                "exact_executed_transition_source_complete": True,
                "executed_dflash_info_v2_matches_observed": True,
                "request25_only_logical_rid_fixture": True,
                "row_position_length_alignment_fixture": True,
                "pre_post_logit_labels_fixture": True,
                "gpu_claimed": False,
                "cuda_invoked": False,
                "endpoint_replayed": False,
            },
            "scientific_result": None,
            "repair_emitted": False,
            "actual_spend_usd": 0.0,
            "next": (
                "Await a later director turn; GPU re-entry and endpoint replay remain "
                "forbidden by this preparation terminal."
            ),
        }
        write_json(ARTIFACT_ROOT / "PREPARATION_RESULT.json", result)
        write_json(ROOT / "DFLASH_REQUEST25_BOUNDARY_PROBE_PREPARATION_TERMINAL.json", result)
        print(json.dumps(result, indent=2, sort_keys=True))
    finally:
        if temporary is not None:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
