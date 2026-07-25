from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT = Path(__file__).resolve().parent
OUTPUT = PROJECT / "IMMUTABLE_PACKET.json"
FILES = [
    "exact_consumer_oracle.py",
    "endpoint_pair.py",
    "remote_experiment.py",
    "intervention/extend_attention_fixed_m384.py",
    "inputs/harness/exact_runner.py",
    "inputs/harness/endpoint_entrypoint.py",
    "inputs/harness/decode_equivalent_lm_head.py",
    "inputs/harness/sitecustomize.py",
    "inputs/evidence/candidate-full-launch.json",
    "inputs/upstream/extend_attention.py",
    "inputs/upstream/triton_backend.py",
    "inputs/upstream/ngram_worker.py",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row(relative: str) -> dict:
    path = PROJECT / relative
    return {
        "path": relative,
        "bytes": path.stat().st_size,
        "mode": "0o444",
        "sha256": sha256(path),
    }


def main() -> None:
    checkpoint = json.loads(
        (PROJECT / "inputs/evidence/CHECKPOINT_MANIFEST.json").read_text()
    )
    checkpoint_rows = [
        {
            "path": f"inputs/checkpoint/{item['name']}",
            "bytes": item["bytes"],
            "mode": "0o444",
            "sha256": item["sha256"],
        }
        for item in checkpoint["files"]
    ]
    value = {
        "schema_version": 1,
        "kind": "gemma4_h200_fixed_m384_q12_attention_executor_packet",
        "offline_construction_pass": True,
        "scientific_question": (
            "Does an exact c32 q_len=12 eight-row attention schedule reduce the "
            "dominant recurring M384 target-forward boundary and the matched endpoint?"
        ),
        "hypothesis": {
            "causal_change": (
                "Dispatch only H200 batch-32, 384-row, max-extend-12, head-dim "
                "256/512 target verification from stock BLOCK_M 64/32 to BLOCK_M 8."
            ),
            "prediction": (
                "Fewer padded query rows and less live accumulator state lower warm "
                "attention time despite doubling query-block grid depth."
            ),
            "unchanged": [
                "BLOCK_N=64",
                "custom mask and causal semantics",
                "page-1 paged KV indices and FP8 E5M2 values",
                "BF16 query/output contract",
                "request ownership, positions, and cache accounting",
                "stock fallback for every non-M384 geometry",
            ],
        },
        "shape": {
            "batch": 32,
            "draft_tokens": 12,
            "query_positions": 384,
            "query_heads": 32,
            "local": {
                "layers": 50,
                "kv_heads": 16,
                "head_dim": 256,
                "window": 1024,
            },
            "global": {
                "layers": 10,
                "kv_heads": 4,
                "head_dim": 512,
                "window": None,
            },
            "page_size": 1,
            "kv_dtype": "fp8_e5m2",
            "activation_output_dtype": "bfloat16",
        },
        "runtime": {
            "sglang_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image": (
                "docker.io/lmsysorg/sglang@sha256:"
                "6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
            ),
            "control_source_sha256": (
                "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1"
            ),
        },
        "files": [row(relative) for relative in FILES],
        "checkpoint": {
            "total_bytes": checkpoint["total_bytes"],
            "files": checkpoint_rows,
            "materialization": (
                "Reconcile against the post-DFlash resident target; hard-link only "
                "matched exact bytes into the immutable experiment path."
            ),
        },
    }
    temporary = OUTPUT.with_suffix(".json.part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    temporary.replace(OUTPUT)


if __name__ == "__main__":
    main()
