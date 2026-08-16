#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import py_compile


ROOT = pathlib.Path(__file__).resolve().parent
PINNED = {
    "inputs/source/ngram_worker.py": "27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554",
    "inputs/source/ngram_info.py": "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c",
    "inputs/source/triton_backend.v0.5.13.py": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "inputs/source/extend_attention.v0.5.13.py": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(path: pathlib.Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def main() -> None:
    for name, expected in PINNED.items():
        if sha256(ROOT / name) != expected:
            raise RuntimeError(f"pinned_source_mismatch:{name}")
    candidates = {
        "inputs/bound/candidate_ngram_worker.py": ("USE_FULL_MASK = False",),
        "inputs/bound/candidate_triton_backend.py": (
            "self.num_draft_tokens * self.num_draft_tokens",
        ),
        "inputs/bound/candidate_extend_attention.py": (
            "* cur_seq_len_extend",
        ),
    }
    admitted = [
        ROOT / "component_benchmark.py",
        ROOT / "endpoint_pair.py",
        ROOT / "remote_experiment.py",
        *(ROOT / name for name in candidates),
        *sorted((ROOT / "inputs/bound").glob("*.py")),
        *sorted((ROOT / "inputs/evidence").glob("*")),
        *sorted((ROOT / "inputs/source").glob("*.py")),
    ]
    admitted = list(dict.fromkeys(admitted))
    for name, tokens in candidates.items():
        text = (ROOT / name).read_text()
        if any(token not in text for token in tokens):
            raise RuntimeError(f"candidate_contract_missing:{name}")
    for path in admitted:
        if path.suffix == ".py":
            py_compile.compile(str(path), doraise=True)
    packet = {
        "schema_version": 1,
        "kind": "gemma4_h200_ngram_qlen_mask_target_verify",
        "director_binding_sha256": sha256(ROOT / "DIRECTOR_BINDING.json"),
        "hypothesis": {
            "causal_change": "replace full-prefix target-verify masks with exact 12x12 QLEN suffix masks",
            "prediction": "remove 1,618,176 mask booleans and their allocations/copies per c32 verify step while preserving M64 attention outputs",
            "unchanged": [
                "stock BLOCK_M=64",
                "32 requests x 12 query rows",
                "page-1 FP8-E5M2 KV",
                "BF16 query/output",
                "50 sliding and 10 full layers",
                "NGRAM settings, scheduler, and wave policy",
            ],
        },
        "files": [row(path) for path in admitted],
        "offline_construction_pass": True,
    }
    atomic(ROOT / "IMMUTABLE_PACKET.json", packet)
    print(json.dumps(packet, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
