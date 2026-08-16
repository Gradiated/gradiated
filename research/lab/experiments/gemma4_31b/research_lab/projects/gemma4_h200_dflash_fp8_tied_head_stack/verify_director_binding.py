#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tarfile


def digest(path: pathlib.Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            value.update(chunk)
    return value.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sglang-root", type=pathlib.Path, required=True)
    parser.add_argument("--adapted-gemma", type=pathlib.Path, required=True)
    parser.add_argument("--capture-gemma", type=pathlib.Path, required=True)
    parser.add_argument("--runtime-identity-binding", type=pathlib.Path)
    parser.add_argument("--correction-binding", type=pathlib.Path)
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()

    project = pathlib.Path(__file__).resolve().parent
    dflash = project.parent / "gemma4_h200_dflash_endpoint"
    fp8 = (
        project.parent
        / "gemma4_h200_fp8_tied_head_endpoint"
        / "iterations/c32-topology-settled-resume-20260723t2110z"
        / "resident-consumer-repair-artifacts"
    )
    binding = json.loads((project / "DIRECTOR_BINDING.json").read_text())
    checks: list[dict[str, object]] = []

    def check(label: str, path: pathlib.Path, expected: str) -> None:
        observed = digest(path)
        checks.append(
            {
                "label": label,
                "path": str(path.resolve()),
                "expected_sha256": expected,
                "observed_sha256": observed,
                "pass": observed == expected,
            }
        )

    for group_name in ("dflash_inputs", "prior_fp8_head_inputs"):
        for name, value in binding[group_name].items():
            if isinstance(value, dict) and {"path", "sha256"} <= value.keys():
                check(
                    f"director.{group_name}.{name}",
                    project / value["path"],
                    value["sha256"],
                )

    fresh_path = project / binding["dflash_inputs"]["director_binding"]["path"]
    fresh = json.loads(fresh_path.read_text())
    check(
        "fresh.incorporated_scientific_binding",
        dflash / fresh["incorporated_scientific_binding"]["path"],
        fresh["incorporated_scientific_binding"]["sha256"],
    )
    check(
        "fresh.offline_gate",
        dflash / fresh["offline_gate"]["path"],
        fresh["offline_gate"]["sha256"],
    )
    check(
        "fresh.retirement_artifact",
        dflash / fresh["resident_state_discontinuity"]["retirement_artifact"]["path"],
        fresh["resident_state_discontinuity"]["retirement_artifact"]["sha256"],
    )
    for key, suffix in (
        ("archive", "archive_sha256"),
        ("manifest", "manifest_sha256"),
        ("launcher", "launcher_sha256"),
    ):
        check(
            f"fresh.execution_packet.{key}",
            dflash / fresh["execution_packet"][key],
            fresh["execution_packet"][suffix],
        )

    reopening = json.loads(
        (dflash / fresh["incorporated_scientific_binding"]["path"]).read_text()
    )
    for name, value in reopening["immutable_inputs"].items():
        check(
            f"reopening.immutable_inputs.{name}",
            dflash / value["path"],
            value["sha256"],
        )

    offline = json.loads((dflash / fresh["offline_gate"]["path"]).read_text())
    check(
        "offline.reopening_binding",
        dflash / offline["reopening_binding"]["path"],
        offline["reopening_binding"]["sha256"],
    )
    check(
        "offline.exact_runtime.consumer",
        args.sglang_root / "python/sglang/srt/speculative/dflash_worker.py",
        offline["exact_runtime"]["consumer_file_sha256"],
    )
    check(
        "offline.exact_runtime.shard_contract",
        args.sglang_root
        / "python/sglang/srt/layers/vocab_parallel_embedding.py",
        offline["exact_runtime"]["shard_contract_file_sha256"],
    )
    check(
        "offline.exact_runtime.adapted_gemma",
        args.adapted_gemma,
        offline["exact_runtime"]["gemma4_adapted_file_sha256"],
    )
    check(
        "offline.adapter",
        dflash / offline["adapter"]["path"],
        offline["adapter"]["sha256"],
    )
    check(
        "offline.measurement.result",
        dflash / offline["offline_measurement"]["result"],
        offline["offline_measurement"]["result_sha256"],
    )
    check(
        "offline.measurement.runner",
        dflash / offline["offline_measurement"]["runner"],
        offline["offline_measurement"]["runner_sha256"],
    )
    for key, suffix in (
        ("archive", "archive_sha256"),
        ("manifest", "manifest_sha256"),
        ("launcher", "launcher_sha256"),
    ):
        check(
            f"offline.execution_packet.{key}",
            dflash / offline["execution_packet"][key],
            offline["execution_packet"][suffix],
        )

    original_runtime_path = dflash / "DRAFT_RUNTIME_BINDING.json"
    runtime_path = args.runtime_identity_binding or original_runtime_path
    runtime = json.loads(runtime_path.read_text())
    runtime_source = runtime["runtime_source"]
    check(
        "runtime.python_pyproject",
        args.sglang_root / "python/pyproject.toml",
        runtime_source["python_pyproject_sha256"],
    )
    check(
        "runtime.dockerfile",
        args.sglang_root / "docker/Dockerfile",
        runtime_source["dockerfile_sha256"],
    )
    for relative, expected in runtime_source["dflash_sources"].items():
        check(
            f"runtime.dflash_sources.{relative}",
            args.sglang_root / relative,
            expected,
        )

    capture = json.loads((dflash / "CAPTURE_HOOK_BINDING.json").read_text())
    check(
        "capture.gemma4_mm_base",
        args.sglang_root / "python/sglang/srt/models/gemma4_mm.py",
        capture["pinned_runtime"]["gemma4_mm_base_sha256"],
    )
    check(
        "capture.gemma4_mm_patched",
        args.capture_gemma,
        capture["pinned_runtime"]["gemma4_mm_patched_sha256"],
    )
    check(
        "capture.patch",
        dflash / "gemma4_dflash_capture_hook.patch",
        capture["pinned_runtime"]["patch_sha256"],
    )
    check(
        "capture.runner",
        dflash / "dflash_endpoint_runner.py",
        capture["runner_api_repair"]["runner_sha256"],
    )

    manifest_path = dflash / fresh["execution_packet"]["manifest"]
    archive_path = dflash / fresh["execution_packet"]["archive"]
    manifest = json.loads(manifest_path.read_text())
    with tarfile.open(archive_path) as archive:
        for row in manifest["files"]:
            extracted = archive.extractfile(row["path"])
            if extracted is None:
                raise RuntimeError(f"missing archive member {row['path']}")
            data = extracted.read()
            observed = hashlib.sha256(data).hexdigest()
            checks.append(
                {
                    "label": f"dflash_archive_member.{row['path']}",
                    "path": f"{archive_path.resolve()}::{row['path']}",
                    "expected_sha256": row["sha256"],
                    "observed_sha256": observed,
                    "expected_bytes": row["bytes"],
                    "observed_bytes": len(data),
                    "pass": observed == row["sha256"] and len(data) == row["bytes"],
                }
            )

    prior_archive = project / binding["prior_fp8_head_inputs"]["compact_archive"]["path"]
    with tarfile.open(prior_archive) as archive:
        members = sorted(
            member.name.removeprefix("./")
            for member in archive.getmembers()
            if member.isfile()
        )

    correction = None
    if args.correction_binding is not None:
        correction_binding = json.loads(args.correction_binding.read_text())
        correction_checks = []
        for name, value in correction_binding["bound_inputs"].items():
            path = project / value["path"]
            observed = digest(path)
            correction_checks.append(
                {
                    "label": name,
                    "path": str(path.resolve()),
                    "expected_sha256": value["sha256"],
                    "observed_sha256": observed,
                    "pass": observed == value["sha256"],
                }
            )

        original_runtime = json.loads(original_runtime_path.read_text())
        changed_paths = []

        def compare(left: object, right: object, path: tuple[str, ...] = ()) -> None:
            if isinstance(left, dict) and isinstance(right, dict):
                if left.keys() != right.keys():
                    changed_paths.append(
                        {
                            "path": ".".join(path),
                            "original_keys": sorted(left),
                            "corrected_keys": sorted(right),
                        }
                    )
                    return
                for key in left:
                    compare(left[key], right[key], (*path, key))
                return
            if left != right:
                changed_paths.append(
                    {
                        "path": ".".join(path),
                        "original": left,
                        "corrected": right,
                    }
                )

        compare(original_runtime, runtime)
        expected_change = {
            "path": "runtime_source.dflash_sources.python/sglang/srt/speculative/triton_ops/dflash_accept_bonus.py",
            "original": correction_binding["runtime_identity"][
                "false_declared_sha256"
            ],
            "corrected": correction_binding["runtime_identity"][
                "correct_observed_sha256"
            ],
        }
        correction = {
            "binding": str(args.correction_binding.resolve()),
            "binding_sha256": digest(args.correction_binding),
            "bound_input_checks": correction_checks,
            "bound_inputs_pass": all(row["pass"] for row in correction_checks),
            "original_runtime_binding": str(original_runtime_path.resolve()),
            "original_runtime_binding_sha256": digest(original_runtime_path),
            "corrected_runtime_binding": str(runtime_path.resolve()),
            "corrected_runtime_binding_sha256": digest(runtime_path),
            "changed_paths": changed_paths,
            "only_authorized_field_changed": changed_paths == [expected_change],
        }

    failed = [row for row in checks if not row["pass"]]
    if correction is not None and (
        not correction["bound_inputs_pass"]
        or not correction["only_authorized_field_changed"]
    ):
        failed.append(
            {
                "label": "source_identity_correction_contract",
                "pass": False,
            }
        )
    result = {
        "schema_version": 1,
        "status": "pass" if not failed else "fail",
        "director_binding": str((project / "DIRECTOR_BINDING.json").resolve()),
        "runtime_commit": runtime_source["merge_commit"],
        "checks": checks,
        "check_count": len(checks),
        "failure_count": len(failed),
        "correction": correction,
        "prior_compact_archive_members": members,
        "excluded_non_file_digest": {
            "field": "runtime_source.cuda_base_manifest_sha256",
            "reason": "OCI manifest identity is declarative and has no bound local file path; no registry or provider access was authorized.",
            "value": runtime_source["cuda_base_manifest_sha256"],
        },
    }
    atomic_json(args.output, result)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
