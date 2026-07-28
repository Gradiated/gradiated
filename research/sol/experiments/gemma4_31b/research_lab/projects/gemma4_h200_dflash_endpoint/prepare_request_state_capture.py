#!/usr/bin/env python3
"""Bind the exact request-state capture packet and emit its no-CUDA gate."""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib
import subprocess
import tarfile
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
ARTIFACT_ROOT = ROOT / "artifacts" / "request-state-capture-rebinding-20260725t2309z"
ARCHIVE = ARTIFACT_ROOT / "REQUEST_STATE_CAPTURE_PACKET.tar"
MANIFEST = ROOT / "REQUEST_STATE_CAPTURE_PACKET_MANIFEST.json"
CHECKSUMS = ROOT / "PACKET.sha256"

PACKET_FILES = [
    "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE.json",
    "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE_REBINDING.json",
    "EXPECTED_INSTALLED_SOURCE.sha256",
    "dflash_endpoint_runner.py",
    "remote_request_state_capture.sh",
    "request_state_capture_sitecustomize.py",
    "request_state_observer.py",
    "summarize_request_state_capture.py",
    "test_request_state_observer.py",
    "inputs/bound/dflash_info_v2.py",
    "inputs/bound/dflash_worker_v2.py",
    "inputs/bound/forward_batch_info.py",
    "inputs/bound/memory_pool.py",
    "inputs/bound/swa_memory_pool.py",
    "inputs/bound/tp_worker.py",
]

SOURCE_ANCHORS = {
    "inputs/bound/dflash_worker_v2.py": [
        "batch_output.next_draft_input = self._make_next_draft_input_prefill(",
        "target_predict = torch.argmax(logits_output.next_token_logits",
        "new_seq_lens = prefix_lens + commit_lens.to(prefix_lens.dtype)",
        "next_token_ids=out_tokens.reshape(-1)",
    ],
    "inputs/bound/tp_worker.py": [
        "def forward_batch_generation(",
        "if is_verify:",
        "batch_result.next_token_ids = self.model_runner.sample(",
    ],
    "inputs/bound/memory_pool.py": [
        "def get_key_buffer(self, layer_id: int)",
        "def get_value_buffer(self, layer_id: int)",
    ],
    "inputs/bound/swa_memory_pool.py": [
        "def translate_loc_from_full_to_swa",
        "def get_key_buffer(self, layer_id: int)",
    ],
}


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
        temporary = pathlib.Path(handle.name)
    temporary.replace(path)


def main() -> int:
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    binding = json.loads((ROOT / "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE.json").read_text())
    rebinding = json.loads(
        (ROOT / "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE_REBINDING.json").read_text()
    )
    if binding["offline_gate"]["cuda_forbidden"] is not True:
        raise ValueError("director offline gate is not CUDA-forbidden")
    if rebinding["offline_rebinding_gate"]["cuda_forbidden"] is not True:
        raise ValueError("director rebinding gate is not CUDA-forbidden")
    if rebinding["offline_rebinding_gate"]["source_byte_mutation_forbidden"] is not True:
        raise ValueError("director rebinding did not prohibit source-byte mutation")
    expected_paths = {
        "dflash_worker_v2.py": "/sgl-workspace/sglang/python/sglang/srt/speculative/dflash_worker_v2.py",
        "dflash_info_v2.py": "/sgl-workspace/sglang/python/sglang/srt/speculative/dflash_info_v2.py",
        "tp_worker.py": "/sgl-workspace/sglang/python/sglang/srt/managers/tp_worker.py",
        "forward_batch_info.py": "/sgl-workspace/sglang/python/sglang/srt/model_executor/forward_batch_info.py",
        "memory_pool.py": "/sgl-workspace/sglang/python/sglang/srt/mem_cache/memory_pool.py",
        "swa_memory_pool.py": "/sgl-workspace/sglang/python/sglang/srt/mem_cache/swa_memory_pool.py",
    }
    rebinding_hashes = {entry["path"]: entry["sha256"] for entry in rebinding["installed_source_identity"]}
    if set(rebinding_hashes) != set(expected_paths):
        raise ValueError("director rebinding does not enumerate the six required sources")
    # This is intentionally the only rebinding mutation: the source copies under
    # inputs/bound/ are retained evidence and must not be rewritten to fit the image.
    CHECKSUMS.parent.mkdir(parents=True, exist_ok=True)
    (ROOT / "EXPECTED_INSTALLED_SOURCE.sha256").write_text(
        "".join(
            f"{rebinding_hashes[name]}  {remote_path}\n"
            for name, remote_path in expected_paths.items()
        )
    )
    for relative, anchors in SOURCE_ANCHORS.items():
        text = (ROOT / relative).read_text()
        missing = [anchor for anchor in anchors if anchor not in text]
        if missing:
            raise ValueError(f"{relative} missing source anchors: {missing}")

    fixture = subprocess.run(
        ["python3", "-m", "unittest", "-v", "test_request_state_observer.py"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if fixture.returncode:
        raise RuntimeError(fixture.stdout)
    compile_check = subprocess.run(
        [
            "python3",
            "-m",
            "py_compile",
            "request_state_observer.py",
            "request_state_capture_sitecustomize.py",
            "summarize_request_state_capture.py",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if compile_check.returncode:
        raise RuntimeError(compile_check.stdout)

    files = [
        {
            "path": relative,
            "bytes": (ROOT / relative).stat().st_size,
            "sha256": sha256(ROOT / relative),
        }
        for relative in PACKET_FILES
    ]
    CHECKSUMS.write_text(
        "".join(f"{entry['sha256']}  {entry['path']}\n" for entry in files)
    )
    files.append(
        {
            "path": CHECKSUMS.name,
            "bytes": CHECKSUMS.stat().st_size,
            "sha256": sha256(CHECKSUMS),
        }
    )
    manifest = {
        "schema_version": 1,
        "project": binding["project"],
        "director_binding_sha256": sha256(
            ROOT / "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE_REBINDING.json"
        ),
        "superseded_measurement_contract_sha256": sha256(
            ROOT / "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE.json"
        ),
        "files": files,
    }
    atomic(MANIFEST, manifest)
    with tarfile.open(ARCHIVE.with_suffix(".tar.part"), "w") as archive:
        for relative in PACKET_FILES:
            archive.add(ROOT / relative, arcname=relative, recursive=False)
        archive.add(CHECKSUMS, arcname=CHECKSUMS.name, recursive=False)
        archive.add(MANIFEST, arcname=MANIFEST.name, recursive=False)
    ARCHIVE.with_suffix(".tar.part").replace(ARCHIVE)

    maximum_locations = 32 * 4214
    layer_count = 60
    sampled_values = maximum_locations * layer_count * 2
    ready = {
        "schema_version": 1,
        "classification": "request_state_capture_ready",
        "pass": True,
        "created_at_utc": datetime.datetime.now(datetime.UTC).isoformat().replace(
            "+00:00", "Z"
        ),
        "cuda_used": False,
        "fixture": {
            "command": "python3 -m unittest -v test_request_state_observer.py",
            "returncode": fixture.returncode,
            "stdout": fixture.stdout,
            "pass_through_identity_tested": True,
            "permuted_exact_c32_request_ownership_tested": True,
            "duplicate_marker_fail_closed_tested": True,
            "event_digest_determinism_tested": True,
        },
        "source_binding": {
            "director_rebinding": "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE_REBINDING.json",
            "director_rebinding_sha256": sha256(
                ROOT / "DIRECTOR_EXACT_REQUEST_STATE_CAPTURE_REBINDING.json"
            ),
            "expected_installed_source": "EXPECTED_INSTALLED_SOURCE.sha256",
            "expected_installed_source_sha256": sha256(
                ROOT / "EXPECTED_INSTALLED_SOURCE.sha256"
            ),
            "materialized_sources": [
                entry for entry in files if entry["path"].startswith("inputs/bound/")
            ],
            "materialized_source_bytes_mutated": False,
            "anchors_pass": True,
        },
        "observer": {
            "sites": [
                "TpModelWorker target-prefill return",
                "TpModelWorker first ordinary AR decode return",
                "DFlashWorkerV2 first target-verify/accept/bonus return",
            ],
            "kv_digest_scheme": "all referenced locations, one deterministic K and V coordinate per target KV layer",
            "maximum_prefill_locations": maximum_locations,
            "maximum_sampled_values": sampled_values,
            "maximum_sampled_bytes_bfloat16": sampled_values * 2,
            "explicit_cuda_synchronizations": 0,
            "bounded_host_transfer_synchronizations_per_transition": 1,
            "semantics_mutation": False,
            "timing_claim_authorized": False,
        },
        "packet": {
            "manifest": MANIFEST.name,
            "manifest_sha256": sha256(MANIFEST),
            "archive": str(ARCHIVE.relative_to(ROOT)),
            "archive_sha256": sha256(ARCHIVE),
            "archive_bytes": ARCHIVE.stat().st_size,
        },
    }
    atomic(ROOT / binding["offline_gate"]["artifact"], ready)
    print(json.dumps(ready, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
