#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import threading

from b200_static_scheduler_endpoint_owner import BENCH, Owner, atomic_json, load, sha256


def emit(args: argparse.Namespace) -> int:
    project = args.project_root.resolve()
    source_manifest = project / "B200_STATIC_SCHEDULER_ENDPOINT_RUNTIME_MANIFEST.json"
    value = {
        "schema_version": 1,
        "classification": "static_scheduler_endpoint_retained_claim_runtime_manifest",
        "scientific_binding": args.binding.name,
        "scientific_binding_sha256": sha256(args.binding),
        "source_owner": "b200_static_scheduler_endpoint_owner.py",
        "source_owner_sha256": sha256(project / "b200_static_scheduler_endpoint_owner.py"),
        "retained_claim_owner": "b200_static_scheduler_endpoint_retained_claim_owner.py",
        "retained_claim_owner_sha256": sha256(project / "b200_static_scheduler_endpoint_retained_claim_owner.py"),
        "source_runtime_manifest": source_manifest.name,
        "source_runtime_manifest_sha256": sha256(source_manifest),
        "runner_sha256": sha256(project / "b200_static_scheduler_endpoint_pair.py"),
        "candidate_source_sha256": sha256(project / "m32_static_persistent_geometric_rebind_extension.cu"),
        "checkpoint_manifest_sha256": sha256(project / "inputs/static-scheduler-endpoint-checkpoint/model-files.sha256"),
        "adopts_claimed_at_utc": "2026-07-29T00:43:20.343760Z",
    }
    atomic_json(args.runtime_manifest, value)
    return 0


def execute(args: argparse.Namespace) -> int:
    project = args.project_root.resolve()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_manifest = project / "B200_STATIC_SCHEDULER_ENDPOINT_RUNTIME_MANIFEST.json"
    owner = Owner(argparse.Namespace(
        repo_root=args.repo_root,
        project_root=project,
        lab=args.lab,
        binding=args.binding,
        runtime_manifest=source_manifest,
        preclaim=project / "PRECLAIM_B200_STATIC_SCHEDULER_ENDPOINT_TERMINAL.json",
        output=out,
    ))
    try:
        runtime = load(args.runtime_manifest)
        if runtime["scientific_binding_sha256"] != sha256(args.binding):
            raise RuntimeError("retained_binding_mismatch")
        if runtime["source_owner_sha256"] != sha256(project / "b200_static_scheduler_endpoint_owner.py"):
            raise RuntimeError("source_owner_mismatch")
        if runtime["retained_claim_owner_sha256"] != sha256(project / "b200_static_scheduler_endpoint_retained_claim_owner.py"):
            raise RuntimeError("retained_owner_mismatch")
        for attribute, executable in (("ssh_path", "ssh"), ("scp_path", "scp"), ("tail_path", "tail")):
            resolved = shutil.which(executable)
            if resolved is None:
                raise RuntimeError(f"controller_executable_missing:{executable}")
            setattr(owner, attribute, str(Path(resolved).resolve()))
        owner.establish_ssh()
        owner.claimed = True
        threading.Thread(target=owner.heartbeat, daemon=True).start()
        owner.pool("heartbeat", "--project", owner.project.name, "--bench", BENCH)
        owner.progress("retained_claim_adopted", original_claimed_at_utc=runtime["adopts_claimed_at_utc"])
        while True:
            try:
                owner.stage()
                owner.build()
                break
            except Exception as exc:
                if not owner.repair_wait(exc):
                    raise
        while True:
            try:
                owner.run_pair()
                break
            except Exception as exc:
                if not owner.repair_wait(exc):
                    raise
                owner.phase = "artifact_retrieval"
                break
        while True:
            try:
                owner.retrieve_release()
                return 0
            except Exception as exc:
                if not owner.repair_wait(exc):
                    raise
    except Exception as exc:
        atomic_json(out / "OWNER_INCOMPLETE.json", {"classification": "retained_claim_owner_incomplete", "error": repr(exc), "claimed": True, "last_command": owner.last_command})
        return 1
    finally:
        owner.stop.set()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path("/root/workspace"))
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--lab", type=Path)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--runtime-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--emit", action="store_true")
    args = parser.parse_args()
    if args.emit:
        return emit(args)
    if args.lab is None or args.output is None:
        parser.error("--lab and --output required")
    return execute(args)


if __name__ == "__main__":
    raise SystemExit(main())
