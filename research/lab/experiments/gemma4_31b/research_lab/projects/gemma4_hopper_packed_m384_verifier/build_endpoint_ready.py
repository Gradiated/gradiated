#!/usr/bin/env python3
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib


PROJECT = pathlib.Path(__file__).resolve().parent
ENDPOINT = PROJECT / "inputs" / "endpoint"
CHECKPOINT = PROJECT / "inputs" / "checkpoint"
DIRECTOR = PROJECT / "DIRECTOR_H100_PACKED_M384_ENDPOINT_PROMOTION_20260726T1712Z.json"
COMPONENT = PROJECT / "artifacts" / "h100-component" / "PACKED_M384_VERIFIER_RESULT.json"
IMAGE = (
    "docker.io/lmsysorg/sglang@"
    "sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6"
)
REMOTE_ROOT = "/home/glmrunner/gemma4_hopper_packed_m384_endpoint"
DEADLINE_EPOCH = 1785092400
EXPECTED = {
    "director": "977d6f9cad3bf72974f95fa5ff6d60251eb01c5f2c6dcd36391195e16fdc0ee4",
    "component": "5b32a5c28ada71d88ed4e30201ef43ad91432c0597a1872772ede9c8e99e9e88",
    "v2": "640065a20745b5e8ffcfdbcee05687fa195506fd261848c1e8c6d54ef2744b55",
    "extend_attention": "1b52992bac37ae170524025654814541f3280edd41fcd80b4d77e655f94ffff1",
    "triton_backend": "7bc3ae9ef1be59ec07734df442c077a07fb54c28007747f53a552bb81e8e8e2d",
    "checkpoint_manifest": "6202e8f8565a350270875c95b67c31329a5266bbaf1cdc23b54df96da63da9d6",
}
PACKET_NAMES = [
    "decode_equivalent_lm_head.py",
    "endpoint_entrypoint.py",
    "endpoint_pair.py",
    "exact_runner.py",
    "packed_m384_endpoint.py",
    "sitecustomize.py",
    "token_trace_hook.py",
    "triton_backend.v0.5.13.py",
]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(8 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic(path: pathlib.Path, value: object) -> None:
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def row(local: pathlib.Path, remote: str) -> dict:
    return {
        "bytes": local.stat().st_size,
        "path": remote,
        "sha256": sha256(local),
        "source": str(local.relative_to(PROJECT)),
    }


def function_ast(path: pathlib.Path, name: str) -> str:
    module = ast.parse(path.read_text())
    node = next(
        item
        for item in module.body
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        and item.name == name
    )
    return hashlib.sha256(ast.dump(node, include_attributes=False).encode()).hexdigest()


def tokens(label: str, count: int) -> list[int]:
    values: list[int] = []
    index = 0
    while len(values) < count:
        digest = hashlib.sha256(
            f"gemma4-background-exact-mix-c32-20260718|{label}|{index}".encode()
        ).digest()
        for offset in range(0, len(digest), 4):
            values.append(
                1000
                + int.from_bytes(digest[offset : offset + 4], "big") % 249000
            )
            if len(values) == count:
                return values
        index += 1
    return values


def request_hashes() -> list[str]:
    common = tokens("common-prefix", 535)
    values = []
    for index in range(32):
        suffix = tokens(f"suffix-{index}", 4214 - 535)
        suffix[0] = 200000 + index
        body = {
            "model": "google/gemma-4-31B-it",
            "prompt": common + suffix,
            "max_tokens": 358,
            "min_tokens": 358,
            "ignore_eos": True,
            "temperature": 0,
            "seed": 20260718,
            "stream": True,
            "stream_options": {"include_usage": True},
            "return_token_ids": True,
            "add_special_tokens": False,
        }
        encoded = json.dumps(
            body, sort_keys=True, separators=(",", ":")
        ).encode()
        values.append(hashlib.sha256(encoded).hexdigest())
    return values


def main() -> None:
    observed = {
        "director": sha256(DIRECTOR),
        "component": sha256(COMPONENT),
        "v2": sha256(PROJECT / "packed_m384_attention_v2.py"),
        "extend_attention": sha256(PROJECT / "inputs" / "source" / "extend_attention.py"),
        "triton_backend": sha256(ENDPOINT / "triton_backend.v0.5.13.py"),
        "checkpoint_manifest": sha256(ENDPOINT / "CHECKPOINT_MANIFEST.json"),
    }
    if observed != EXPECTED:
        raise RuntimeError(f"binding_mismatch:{observed}")

    kernel_names = [
        "_score_partition_kernel",
        "_merge_state_kernel",
        "_value_consumer_kernel",
    ]
    original = PROJECT / "packed_m384_attention_v2.py"
    integrated = ENDPOINT / "packed_m384_endpoint.py"
    kernel_hashes = {
        name: {
            "measured_v2_ast_sha256": function_ast(original, name),
            "endpoint_ast_sha256": function_ast(integrated, name),
        }
        for name in kernel_names
    }
    if any(
        value["measured_v2_ast_sha256"] != value["endpoint_ast_sha256"]
        for value in kernel_hashes.values()
    ):
        raise RuntimeError("measured_kernel_ast_changed")
    integrated_source = integrated.read_text()
    if (
        "GLOBAL_PREFIX_CAPACITY = 4608" not in integrated_source
        or "LOCAL_PREFIX_CAPACITY = 1024" not in integrated_source
        or "prefix_tokens ==" in integrated_source
    ):
        raise RuntimeError("endpoint_capacity_adapter_invalid")
    if 4214 + 358 + 12 > 4608:
        raise RuntimeError("global_prefix_capacity_insufficient")
    backend = (ENDPOINT / "triton_backend.v0.5.13.py").read_text()
    if (
        "kv_indptr = self.forward_metadata.window_kv_indptr" not in backend
        or "kv_indices = self.forward_metadata.window_kv_indices" not in backend
        or "self.extend_attention_fwd(" not in backend
    ):
        raise RuntimeError("production_consumer_trace_missing")

    checkpoint_manifest = json.loads(
        (ENDPOINT / "CHECKPOINT_MANIFEST.json").read_text()
    )
    checkpoint_rows = []
    for value in checkpoint_manifest["files"]:
        path = CHECKPOINT / value["name"]
        if not path.is_file() or path.stat().st_size != value["bytes"]:
            raise RuntimeError(f"checkpoint_size_mismatch:{value['name']}")
        digest = sha256(path)
        if digest != value["sha256"]:
            raise RuntimeError(f"checkpoint_hash_mismatch:{value['name']}:{digest}")
        checkpoint_rows.append(
            {
                "bytes": value["bytes"],
                "path": f"checkpoint/{value['name']}",
                "sha256": digest,
                "source": f"inputs/checkpoint/{value['name']}",
            }
        )
    packet_rows = [
        row(ENDPOINT / name, f"input/{name}") for name in PACKET_NAMES
    ]
    input_manifest = {
        "schema_version": 1,
        "project": "gemma4_hopper_packed_m384_verifier",
        "packet_files": packet_rows,
        "checkpoint_files": checkpoint_rows,
        "checkpoint_total_bytes": sum(value["bytes"] for value in checkpoint_rows),
        "materialization": {
            "kind": "project_local_read_only_hardlinks",
            "root": "inputs/checkpoint",
            "resolve_shared_source_after_claim": False,
        },
    }
    manifest_path = ENDPOINT / "ENDPOINT_INPUT_MANIFEST.json"
    atomic(manifest_path, input_manifest)
    manifest_hash = sha256(manifest_path)

    outer_command = [
        "python3",
        f"{REMOTE_ROOT}/input/endpoint_pair.py",
        "--root",
        REMOTE_ROOT,
        "--manifest",
        f"{REMOTE_ROOT}/input/ENDPOINT_INPUT_MANIFEST.json",
        "--absolute-deadline-epoch",
        str(DEADLINE_EPOCH),
    ]
    ready = {
        "schema_version": 1,
        "type": "packed_m384_c32_endpoint_execution_ready",
        "project": "gemma4_hopper_packed_m384_verifier",
        "decision": "exact_matched_control_candidate_endpoint_command_bound",
        "gpu_claim_allowed": False,
        "director_must_consume_before_claim": True,
        "director_binding": {
            "path": DIRECTOR.name,
            "sha256": observed["director"],
        },
        "component_binding": {
            "path": str(COMPONENT.relative_to(PROJECT)),
            "sha256": observed["component"],
            "scientific_sample_consumed": True,
            "replay_allowed": False,
        },
        "identity": {
            "accelerator": "nvidia-h100-sxm",
            "model": "google/gemma-4-31B-it",
            "model_revision": "b9ea41a2887d8607f594846523f94c6cc75ac8a4",
            "checkpoint_manifest_sha256": observed["checkpoint_manifest"],
            "checkpoint_total_bytes": input_manifest["checkpoint_total_bytes"],
            "image": IMAGE,
            "runtime_release": "SGLang v0.5.13",
            "runtime_commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "runtime_source": {
                "extend_attention_sha256": observed["extend_attention"],
                "triton_backend_sha256": observed["triton_backend"],
            },
            "input_manifest": {
                "path": str(manifest_path.relative_to(PROJECT)),
                "sha256": manifest_hash,
            },
        },
        "runtime_integration": {
            "measured_v2_path": "packed_m384_attention_v2.py",
            "measured_v2_sha256": observed["v2"],
            "endpoint_path": "inputs/endpoint/packed_m384_endpoint.py",
            "endpoint_sha256": sha256(integrated),
            "route_patch": "inputs/endpoint/sitecustomize.py",
            "route_patch_sha256": sha256(ENDPOINT / "sitecustomize.py"),
            "kernel_ast_identity": kernel_hashes,
            "adapter_delta": (
                "The three measured V2 Triton kernels are AST-identical. "
                "The endpoint wrapper replaces per-step prefix specialization "
                "with fixed 1024-local and 4608-global capacities; the pinned "
                "backend already provides window-trimmed local paged-KV indices."
            ),
            "production_path": [
                "TritonAttnBackend.forward_extend",
                "window_kv_indptr/window_kv_indices or full kv_indptr/kv_indices",
                "sitecustomize.routed",
                "packed_m384_endpoint.extend_attention_fwd",
                "_score_partition_kernel",
                "_merge_state_kernel",
                "_value_consumer_kernel",
                "o_extend",
                "unchanged residual/model consumer",
                "decode-equivalent target LM head",
                "NGRAM target acceptance and emitted tokens",
            ],
        },
        "matched_command": {
            "outer": outer_command,
            "control": {
                "container": "gemma4-packed-m384-control",
                "arm_environment": "PACKED_M384_ENDPOINT_ARM=control",
                "server_args_symbol": "endpoint_pair.BASE_ARGS",
                "request_command": (
                    "sudo -n docker exec gemma4-packed-m384-control python3 "
                    "/work/input/exact_runner.py --output "
                    "/work/artifacts/control --arm control --concurrency 32"
                ),
            },
            "candidate": {
                "container": "gemma4-packed-m384-candidate",
                "arm_environment": "PACKED_M384_ENDPOINT_ARM=candidate",
                "server_args_symbol": "endpoint_pair.BASE_ARGS",
                "request_command": (
                    "sudo -n docker exec gemma4-packed-m384-candidate python3 "
                    "/work/input/exact_runner.py --output "
                    "/work/artifacts/candidate --arm candidate --concurrency 32"
                ),
            },
            "only_difference": (
                "PACKED_M384_ENDPOINT_ARM selects the hash-bound attention "
                "route; all image, checkpoint, server arguments, workload bytes, "
                "decode-equivalent target head, and token observer bytes match."
            ),
            "profiler": "off",
            "absolute_release_deadline_utc": "2026-07-26T19:00:00Z",
        },
        "workload": {
            "id": "gemma4-background-exact-mix-c32-20260718",
            "runner_sha256": sha256(ENDPOINT / "exact_runner.py"),
            "concurrency": 32,
            "prompt_tokens_per_request": 4214,
            "output_tokens_per_request": 358,
            "shared_prefix_tokens": 535,
            "temperature": 0,
            "seed": 20260718,
            "request_sha256": request_hashes(),
            "qualified_denominator_seconds_per_request": 0.625149101968745,
        },
        "gates": {
            "finite_nonempty_complete": "32/32 rows, 358 returned tokens each",
            "request_identity": "all 32 request SHA-256 values identical by arm",
            "cache": {
                "uncached_prompt_tokens_delta": 117728,
                "cached_prompt_tokens_delta": 17120,
            },
            "target_semantics": (
                "Exact raw SSE token IDs and cumulative scheduler-to-emitted "
                "token traces match control for every request."
            ),
            "no_fallback": (
                "Every custom-mask max_len_extend=12 call must route candidate "
                "or fail immediately; local/global audit counts must be 5:1, "
                "multiples of 50/10, and equal V2 dispatch counts."
            ),
            "global_capacity": {
                "required_max": 4214 + 358 + 12,
                "bound_capacity": 4608,
            },
        },
        "expected_terminal": {
            "path": "artifacts/ENDPOINT_TERMINAL.json",
            "type": "packed_m384_matched_c32_endpoint_terminal",
            "valid_classifications": ["endpoint_positive", "endpoint_nonpositive"],
            "invalid_classification": "semantic_or_path_reject",
            "required_measurements": [
                "control_service_seconds_per_request",
                "candidate_service_seconds_per_request",
                "service_reduction_fraction",
                "complete_request_throughput",
                "routing",
                "gates",
            ],
            "candidate_server_disposition": (
                "Retain healthy candidate container and release the occupied "
                "bench to maintenance unless the director names a compatible successor."
            ),
        },
        "spend": {
            "authorized_cumulative_usd": 8.0,
            "actual_before_endpoint_usd": 0.34,
            "maximum_additional_usd": 7.66,
            "provider_create_allowed": False,
        },
        "offline_validation": {
            "command": "python3 -m unittest -v test_endpoint_integration.py",
            "tests": 4,
            "pass": True,
            "boundary": (
                "Consumer/gate behavior and immutable identities only; the first "
                "candidate CUDA call remains due after director readmission."
            ),
        },
    }
    atomic(PROJECT / "ENDPOINT_READY.json", ready)
    print(
        json.dumps(
            {
                "endpoint_ready": str(PROJECT / "ENDPOINT_READY.json"),
                "endpoint_ready_sha256": sha256(PROJECT / "ENDPOINT_READY.json"),
                "input_manifest_sha256": manifest_hash,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
