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
    component = [
        row("remote_component.sh"),
        row("remote_component_consumer.sh"),
        row("component_benchmark.py"),
        row("local_value_split.py"),
        row("analyze_component.py"),
        row("inputs/source/extend_attention.v0.5.13.py", "inputs/source/extend_attention.v0.5.13.py"),
        row("EVIDENCE_BINDING.json", "inputs/evidence/EVIDENCE_BINDING.json"),
        row("inputs/evidence/authoritative_input_manifest.json", "inputs/evidence/authoritative_input_manifest.json"),
        row("inputs/evidence/residual_attribution.json", "inputs/evidence/residual_attribution.json"),
        row("inputs/evidence/retained_control_terminal.json", "inputs/evidence/retained_control_terminal.json"),
        row("inputs/evidence/attention_subtype_map.json", "inputs/evidence/attention_subtype_map.json"),
        row("inputs/evidence/host_gate_persisted_pair.json", "inputs/evidence/host_gate_persisted_pair.json"),
        row("inputs/evidence/host_gate_frozen_intervention.json", "inputs/evidence/host_gate_frozen_intervention.json"),
        row("inputs/evidence/host_gate_final_terminal.json", "inputs/evidence/host_gate_final_terminal.json"),
        row("inputs/evidence/host_gate_sync_counter.json", "inputs/evidence/host_gate_sync_counter.json"),
    ]
    endpoint_programs = [
        row("endpoint_sitecustomize.py", "sitecustomize.py"),
        row("candidate_local_value_split.py"),
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
    authoritative = json.loads((HERE / "inputs/evidence/authoritative_input_manifest.json").read_text())
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
        "schema_version": 1,
        "pass": True,
        "project": "gemma4_h200_local_attention_register_residency",
        "design": "extend_attention_fwd.local_head256_value_split2",
        "source_sha256": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
        "candidate_sha256": "9c32a590d68d156c36991625d3fcd04d7dac0e6e3e1a1df059fef951915ab158",
        "component": component,
        "endpoint_programs": endpoint_programs,
        "stack": stack,
        "checkpoint": checkpoint,
        "checkpoint_total_bytes": sum(int(item["bytes"]) for item in checkpoint),
    }
    output = HERE / "GPU_INPUT_MANIFEST.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, output)
    print(json.dumps(value, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
