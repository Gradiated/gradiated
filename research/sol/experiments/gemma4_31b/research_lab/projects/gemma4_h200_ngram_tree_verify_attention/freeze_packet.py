#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import py_compile


ROOT = pathlib.Path(__file__).resolve().parent
OUTPUT = ROOT / "IMMUTABLE_PACKET.json"
CHECKPOINT_TOTAL = 62_578_655_208


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 << 20):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def row(path: pathlib.Path) -> dict[str, object]:
    return {
        "path": str(path.relative_to(ROOT)),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
        "mode": oct(path.stat().st_mode & 0o777),
    }


def main() -> None:
    binding = json.loads((ROOT / "EVIDENCE_BINDING.json").read_text())
    for item in binding["source_files"]:
        path = (ROOT / item["path"]).resolve()
        if sha256(path) != item["sha256"]:
            raise RuntimeError(f"evidence_binding_mismatch:{path}")
    expected = {
        "inputs/source/extend_attention.v0.5.13.py": (
            "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
        ),
        "inputs/source/triton_backend.v0.5.13.py": (
            "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d"
        ),
        "inputs/source/ngram_info.py": (
            "ffa88c663e1893c306710ac801da0693d8248ebcfd1a5bc705c157f90657af1c"
        ),
        "inputs/source/ngram_worker.py": (
            "27721b777cae08657ec9854ec0137a0db50afd49d84809503312fa43e399b554"
        ),
    }
    for name, digest in expected.items():
        if sha256(ROOT / name) != digest:
            raise RuntimeError(f"pinned_source_mismatch:{name}")
    candidate = ROOT / "inputs/bound/candidate_extend_attention.py"
    tree = ast.parse(candidate.read_text())
    text = candidate.read_text()
    required = (
        "max_len_extend == 12",
        "q_extend.shape[0] == 384",
        "q_extend.shape[1] == 32",
        "k_extend.shape[1] == 16",
        "BLOCK_M = 16",
        "custom_mask is not None",
    )
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "extend_attention_fwd"
        for node in ast.walk(tree)
    ) or any(token not in text for token in required):
        raise RuntimeError("candidate_exact_shape_binding_missing")
    admitted = [
        ROOT / "component_benchmark.py",
        ROOT / "endpoint_pair.py",
        ROOT / "remote_experiment.py",
        candidate,
        ROOT / "inputs/bound/exact_runner.py",
        ROOT / "inputs/bound/endpoint_entrypoint.py",
        ROOT / "inputs/bound/decode_equivalent_lm_head.py",
        ROOT / "inputs/bound/sitecustomize.py",
        ROOT / "inputs/evidence/candidate-full-launch.json",
        *sorted((ROOT / "inputs/source").glob("*.py")),
    ]
    for path in admitted:
        if path.suffix == ".py":
            py_compile.compile(str(path), doraise=True)
    checkpoint = [row(path) for path in sorted((ROOT / "inputs/checkpoint").iterdir())]
    if sum(int(item["bytes"]) for item in checkpoint) != CHECKPOINT_TOTAL:
        raise RuntimeError("checkpoint_byte_count_mismatch")
    if any((ROOT / str(item["path"])).stat().st_mode & 0o222 for item in checkpoint):
        raise RuntimeError("checkpoint_snapshot_mutable")
    packet = {
        "schema_version": 1,
        "kind": "gemma4_h200_ngram_fixed_tree_block_m16_sm90_packet",
        "scientific_question": (
            "Does a 16-row query tile replace the stock 64-row tile only for "
            "exact c32 NGRAM target verification and reduce attention plus endpoint time?"
        ),
        "hypothesis": {
            "causal_change": "BLOCK_M 64 to 16 for the exact 384x32x256 custom-mask call",
            "unchanged": [
                "BLOCK_N=64",
                "launch count and grid",
                "tree mask and causal semantics",
                "page-1 paged KV indices and FP8 E5M2 values",
                "BF16 query/output contract",
                "50 local and 10 full layer routing",
            ],
            "prediction": (
                "Lower registers/shared memory and kernel time with unchanged compulsory "
                "KV bytes, no new synchronization, and exact output agreement."
            ),
        },
        "shape": {
            "batch": 32,
            "draft_tokens": 12,
            "query_positions": 384,
            "q_heads": 32,
            "kv_heads": 16,
            "head_dim": 256,
            "local_layers": 50,
            "full_layers": 10,
            "local_window": 1024,
            "page_size": 1,
            "kv_dtype": "fp8_e5m2",
            "activation_output_dtype": "bfloat16",
        },
        "runtime": {
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
            "sglang_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "control_source_sha256": expected[
                "inputs/source/extend_attention.v0.5.13.py"
            ],
        },
        "files": [row(path) for path in admitted],
        "checkpoint": {
            "total_bytes": CHECKPOINT_TOTAL,
            "files": checkpoint,
            "materialization": (
                "project-local immutable hard links to previously hash-verified bytes; "
                "only this manifest is admitted to remote reconciliation"
            ),
        },
        "offline_construction_pass": True,
    }
    atomic(OUTPUT, packet)
    print(json.dumps(packet, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
