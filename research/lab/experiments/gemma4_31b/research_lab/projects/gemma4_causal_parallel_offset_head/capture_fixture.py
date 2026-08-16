#!/usr/bin/env python3
"""Execution fixture for request ownership across prefill and decode capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import types

from capture_offset_taps import HIDDEN, OffsetTapCapture


class Mode:
    def __init__(self, name: str) -> None:
        self.name = name

    def is_extend(self) -> bool:
        return self.name == "extend"

    def is_target_verify(self) -> bool:
        return False

    def is_decode(self) -> bool:
        return self.name == "decode"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", required=True, type=pathlib.Path)
    args = parser.parse_args()
    import torch

    capture_root = args.artifact_root / "capture"
    capture = OffsetTapCapture(capture_root, rows_per_chunk=1)
    lengths = [536, 536]
    starts = torch.tensor([0, 536], dtype=torch.int32)
    input_ids = torch.zeros(sum(lengths), dtype=torch.int64)
    input_ids[535] = 200007
    input_ids[536 + 535] = 200021
    hidden = torch.zeros((sum(lengths), HIDDEN), dtype=torch.bfloat16)
    aux = [hidden + index for index in (1, 2, 3)]
    prefill = types.SimpleNamespace(
        forward_mode=Mode("extend"),
        rids=["rid-seven", "rid-twenty-one"],
        extend_seq_lens_cpu=lengths,
        extend_start_loc=starts,
        seq_lens_cpu=None,
        seq_lens=None,
    )
    capture.observe(input_ids, hidden, prefill, aux)
    decode_hidden = torch.zeros((2, HIDDEN), dtype=torch.bfloat16)
    decode = types.SimpleNamespace(
        forward_mode=Mode("decode"),
        rids=["rid-twenty-one", "rid-seven"],
        extend_seq_lens_cpu=None,
        extend_start_loc=None,
        seq_lens_cpu=torch.tensor([4215, 4215], dtype=torch.int32),
        seq_lens=None,
    )
    capture.observe(
        torch.tensor([123, 456], dtype=torch.int64),
        decode_hidden,
        decode,
        [decode_hidden + index for index in (1, 2, 3)],
    )
    capture.close()
    chunks = sorted(capture_root.glob("tap-chunk-*.pt"))
    rows = []
    for path in chunks:
        payload = torch.load(path, map_location="cpu", weights_only=True)
        rows.extend(payload["rows"])
    observed = [
        (row["request_index"], row["target_offset"], row["rid"]) for row in rows
    ]
    expected = [
        (7, 0, "rid-seven"),
        (21, 0, "rid-twenty-one"),
        (21, 1, "rid-twenty-one"),
        (7, 1, "rid-seven"),
    ]
    terminal = json.loads((capture_root / "CAPTURE_TERMINAL.json").read_text())
    result = {
        "schema_version": 1,
        "classification": "capture_request_ownership_fixture",
        "pass": observed == expected and terminal["pass"],
        "observed": observed,
        "expected": expected,
        "capture_terminal_sha256": sha256(
            capture_root / "CAPTURE_TERMINAL.json"
        ),
        "chunk_hashes": [
            {"path": path.name, "sha256": sha256(path)} for path in chunks
        ],
        "checks": {
            "prefill_marker_maps_request_identity": observed[:2] == expected[:2],
            "decode_reordering_preserves_request_identity": observed[2:] == expected[2:],
            "prefill_label_offset_zero": all(row[1] == 0 for row in observed[:2]),
            "first_decode_label_offset_one": all(
                row[1] == 1 for row in observed[2:]
            ),
        },
        "evidence_label": "executed CPU ownership fixture; no model or CUDA claim",
    }
    args.artifact_root.mkdir(parents=True, exist_ok=True)
    output = args.artifact_root / "CAPTURE_FIXTURE.json"
    temporary = output.with_suffix(".json.part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
