#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib


HERE = pathlib.Path(__file__).resolve().parent


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(16 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row(path: str, remote_name: str | None = None) -> dict[str, object]:
    source = HERE / path
    return {
        "path": path,
        "bytes": source.stat().st_size,
        "sha256": sha256(source),
        "remote_name": remote_name or pathlib.Path(path).name,
    }


def main() -> int:
    dependency = HERE / "ITERATION2_DEPENDENCY_BINDING.json"
    dependency_snapshot = HERE / "inputs/evidence/flashinfer_metadata_scalar_terminal.json"
    if not dependency.is_file() or not dependency_snapshot.is_file():
        raise RuntimeError("iteration2_dependency_terminal_not_materialized")
    dependency_value = json.loads(dependency.read_text())
    if not dependency_value.get("pass"):
        raise RuntimeError("iteration2_dependency_binding_not_admitted")
    component = [
        row("remote_iteration2.sh"),
        row("remote_iteration2_consumer.sh"),
        row("iteration2_benchmark.py"),
        row("two_stage_local_attention.py"),
        row("analyze_iteration2.py"),
        row("ITERATION2_BINDING.json", "inputs/evidence/ITERATION2_BINDING.json"),
        row("ITERATION2_CONTRACT.json", "inputs/evidence/ITERATION2_CONTRACT.json"),
        row("ITERATION2_PHYSICAL_MODEL.json", "inputs/evidence/ITERATION2_PHYSICAL_MODEL.json"),
        row("ITERATION2_DEPENDENCY_BINDING.json", "inputs/evidence/ITERATION2_DEPENDENCY_BINDING.json"),
        row("inputs/evidence/flashinfer_metadata_scalar_terminal.json", "inputs/evidence/flashinfer_metadata_scalar_terminal.json"),
        row("inputs/source/extend_attention.v0.5.13.py", "inputs/source/extend_attention.v0.5.13.py"),
        row("EVIDENCE_BINDING.json", "inputs/evidence/EVIDENCE_BINDING.json"),
        row("artifacts/FINAL_TERMINAL.json", "inputs/evidence/iteration1_FINAL_TERMINAL.json"),
        row("artifacts/remote-component/artifacts__COMPONENT_RESULT.json", "inputs/evidence/iteration1_COMPONENT_RESULT.json"),
    ]
    endpoint_programs = [
        row("iteration2_sitecustomize.py", "sitecustomize.py"),
        row("two_stage_local_attention.py"),
        row("remote_endpoint_pair.sh"),
    ]
    stack_names = (
        "proven_v0513_endpoint_entrypoint.py",
        "fp8_qkv_paired_runner.py",
        "install_endpoint_patch.py",
        "qkv_epilogue_discriminator.py",
        "residual_sitecustomize.py",
        "attention_intervention.py",
    )
    stack = [row(f"inputs/stack/{name}", name) for name in stack_names]
    authoritative = json.loads(
        (HERE / "inputs/evidence/authoritative_input_manifest.json").read_text()
    )
    checkpoint = []
    for bound in authoritative["checkpoint_files"]:
        path = HERE / "inputs/checkpoint" / bound["name"]
        if path.stat().st_size != bound["bytes"]:
            raise RuntimeError(f"checkpoint_size_mismatch:{bound['name']}")
        checkpoint.append(
            {
                "path": f"inputs/checkpoint/{bound['name']}",
                "bytes": bound["bytes"],
                "sha256": bound["sha256"],
                "remote_name": bound["name"],
                "identity_basis": "immutable_project_local_hardlink_to_preverified_storage_identity",
            }
        )
    value = {
        "schema_version": 2,
        "pass": True,
        "project": "gemma4_h200_local_attention_register_residency",
        "design": "extend_attention_fwd.local_head256_two_stage_blockprob_vslice2",
        "source_sha256": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
        "candidate_sha256": sha256(HERE / "two_stage_local_attention.py"),
        "component": component,
        "endpoint_programs": endpoint_programs,
        "stack": stack,
        "checkpoint": checkpoint,
        "checkpoint_total_bytes": sum(int(item["bytes"]) for item in checkpoint),
        "prior_spend_usd": 0.185853,
        "authorized_cumulative_usd": 20.0,
    }
    output = HERE / "ITERATION2_GPU_INPUT_MANIFEST.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
