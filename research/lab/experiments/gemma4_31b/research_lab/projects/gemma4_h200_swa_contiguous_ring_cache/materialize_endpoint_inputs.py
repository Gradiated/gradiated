#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "gemma4_h200_local_window512_codesign"
DEST = HERE / "inputs" / "endpoint_stack"
NAMES = (
    "attention_deferred_local_kv.py",
    "fp8_qkv_paired_runner.py",
    "host_min_new_tokens_gate.py",
    "install_endpoint_patch.py",
    "pinned_async_penalty_tokens.py",
    "producer_fused_swa_translation.py",
    "proven_v0513_endpoint_entrypoint.py",
    "qkv_epilogue_discriminator.py",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    DEST.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in NAMES:
        source = SOURCE / "inputs" / "stack" / name
        target = DEST / name
        shutil.copy2(source, target)
        rows.append(
            {
                "name": name,
                "source": str(source),
                "path": str(target.relative_to(HERE)),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    # The retained stack intentionally stages this producer module twice:
    # its source patch imports the runtime launcher as residual_intervention.
    residual_source = SOURCE / "inputs" / "stack" / "producer_fused_swa_translation.py"
    residual_target = DEST / "residual_intervention.py"
    shutil.copy2(residual_source, residual_target)
    rows.append(
        {
            "name": residual_target.name,
            "source": str(residual_source),
            "path": str(residual_target.relative_to(HERE)),
            "bytes": residual_target.stat().st_size,
            "sha256": sha256(residual_target),
        }
    )
    checkpoint_source = SOURCE / "CHECKPOINT_SHA256SUMS.txt"
    checkpoint_target = HERE / "inputs" / "CHECKPOINT_SHA256SUMS.txt"
    shutil.copy2(checkpoint_source, checkpoint_target)
    rows.append(
        {
            "name": checkpoint_target.name,
            "source": str(checkpoint_source),
            "path": str(checkpoint_target.relative_to(HERE)),
            "bytes": checkpoint_target.stat().st_size,
            "sha256": sha256(checkpoint_target),
        }
    )
    (HERE / "ENDPOINT_INPUT_SNAPSHOT.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "immutable_after_claim": True,
                "files": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
