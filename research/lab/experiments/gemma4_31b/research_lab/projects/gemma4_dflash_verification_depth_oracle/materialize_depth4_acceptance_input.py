#!/usr/bin/env python3

import argparse
import hashlib
import json
from pathlib import Path


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.part")
    temporary.write_bytes(data)
    temporary.replace(path)


def final_data_frame(response_bytes: bytes) -> bytes:
    frames = [
        line[6:]
        for line in response_bytes.splitlines()
        if line.startswith(b"data: ") and line != b"data: [DONE]"
    ]
    if not frames:
        raise ValueError("response contains no JSON data frame")
    return frames[-1]


def materialize(
    responses: Path,
    endpoint_terminal_path: Path,
    output_path: Path,
    manifest_path: Path,
) -> dict:
    terminal_bytes = endpoint_terminal_path.read_bytes()
    terminal = json.loads(terminal_bytes)
    candidate = terminal["candidate"]
    if candidate["arm"] != "dflash-depth4-c32":
        raise ValueError("endpoint terminal is not the exact depth-4 c32 arm")
    rows = sorted(candidate["rows"], key=lambda row: row["index"])
    response_paths = sorted(responses.glob("response-*.sse"))
    if len(response_paths) != len(rows) or len(rows) != 32:
        raise ValueError("expected exactly 32 endpoint rows and 32 SSE responses")

    compact_rows = []
    source_records = []
    request_ids = set()
    for endpoint_row, response_path in zip(rows, response_paths, strict=True):
        expected_name = f"response-{endpoint_row['index']:02d}.sse"
        if response_path.name != expected_name:
            raise ValueError(f"expected {expected_name}, found {response_path.name}")
        response_bytes = response_path.read_bytes()
        frame_bytes = final_data_frame(response_bytes)
        frame = json.loads(frame_bytes)
        meta = frame["meta_info"]
        histogram = meta["spec_accept_histogram"]
        verify_cycles = meta["spec_verify_ct"]
        accepted_drafts = sum(index * count for index, count in enumerate(histogram))
        if len(histogram) != 4:
            raise ValueError(f"{response_path}: histogram does not bind depth four")
        if sum(histogram) != verify_cycles:
            raise ValueError(f"{response_path}: histogram count mismatch")
        if accepted_drafts != meta["spec_accepted_drafts"]:
            raise ValueError(f"{response_path}: accepted-draft count mismatch")
        if meta["spec_proposed_drafts"] != verify_cycles * 3:
            raise ValueError(f"{response_path}: proposed-draft count mismatch")
        if meta["id"] != endpoint_row["request_id"]:
            raise ValueError(f"{response_path}: request id mismatch")
        if meta["prompt_tokens"] != endpoint_row["prompt_tokens"]:
            raise ValueError(f"{response_path}: prompt token mismatch")
        if meta["completion_tokens"] != endpoint_row["completion_tokens"]:
            raise ValueError(f"{response_path}: completion token mismatch")
        if meta["id"] in request_ids:
            raise ValueError(f"{response_path}: duplicate request id")
        request_ids.add(meta["id"])
        compact_rows.append(
            {
                "accept_histogram": histogram,
                "accepted_drafts": accepted_drafts,
                "completion_tokens": meta["completion_tokens"],
                "prompt_tokens": meta["prompt_tokens"],
                "proposed_drafts": meta["spec_proposed_drafts"],
                "request_id": meta["id"],
                "request_index": endpoint_row["index"],
                "request_sha256": endpoint_row["request_sha256"],
                "verification_depth": 4,
                "verify_cycles": verify_cycles,
            }
        )
        source_records.append(
            {
                "bytes": len(response_bytes),
                "final_frame_sha256": sha256(frame_bytes),
                "path": str(response_path),
                "sha256": sha256(response_bytes),
            }
        )

    output_bytes = b"".join(canonical_json(row) + b"\n" for row in compact_rows)
    manifest = {
        "schema_version": 1,
        "classification": "exact_depth4_c32_distinct_request_acceptance_input",
        "content": {
            "bytes": len(output_bytes),
            "path": str(output_path),
            "request_count": len(compact_rows),
            "sha256": sha256(output_bytes),
        },
        "derivation": (
            "Canonical projection of only decision-bearing final-frame metadata. "
            "Hashing and validation precede oracle analysis."
        ),
        "excluded_source": (
            "The later request-25 boundary probe with unrecoverable response bytes "
            "was neither read nor reconstructed."
        ),
        "source_endpoint_terminal": {
            "bytes": len(terminal_bytes),
            "path": str(endpoint_terminal_path),
            "sha256": sha256(terminal_bytes),
        },
        "source_responses": source_records,
    }
    atomic_write(output_path, output_bytes)
    atomic_write(manifest_path, json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--responses", type=Path, required=True)
    parser.add_argument("--endpoint-terminal", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    manifest = materialize(
        args.responses,
        args.endpoint_terminal,
        args.output,
        args.manifest,
    )
    print(json.dumps(manifest["content"], sort_keys=True))


if __name__ == "__main__":
    main()
