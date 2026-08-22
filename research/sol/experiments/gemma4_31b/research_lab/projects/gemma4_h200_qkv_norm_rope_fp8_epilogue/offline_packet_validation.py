#!/usr/bin/env python3
"""CPU-only behavioral checks for the QKV endpoint owner/worker packet."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.util
import json
import pathlib
import sys
import tempfile


PROJECT = pathlib.Path(__file__).resolve().parent
INPUTS = PROJECT / "inputs" / "endpoint_packet"


def load_module(name: str, path: pathlib.Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=pathlib.Path, required=True)
    args = parser.parse_args()
    packet = load_module("qkv_endpoint_packet", PROJECT / "endpoint_execution_packet.py")
    owner = load_module("qkv_endpoint_owner", PROJECT / "endpoint_owner.py")
    driver = load_module("qkv_endpoint_driver", INPUTS / "endpoint_driver.py")
    admitted = json.loads((INPUTS / "WORKLOAD.json").read_text())
    generated = [
        hashlib.sha256(driver.canonical(value)).hexdigest()
        for value in driver.bodies()
    ]
    request_identity = generated == admitted["request_sha256"]

    rows = [
        {
            "index": index,
            "error": None,
            "prompt_tokens": 4214,
            "completion_tokens": 358,
            "text_nonempty": True,
            "request_sha256": digest,
        }
        for index, digest in enumerate(generated)
    ]
    terminal = {
        "pass": True,
        "endpoint_submission_count": 1,
        "concurrency": 32,
        "complete_requests": 32,
        "service_seconds_per_request": 0.55,
        "rows": rows,
    }
    path_rows = [
        {
            "candidate_symbol": "_qkv_norm_rope_direct_fp8_cache_kernel",
            "geometry": {"scope": scope},
        }
        for scope in ("local", "global")
    ]
    positive = packet.classify_endpoint(
        terminal, path_rows, 32, {"zero_gpu": True}
    )
    negative = packet.classify_endpoint(
        {**terminal, "service_seconds_per_request": 0.70},
        path_rows,
        32,
        {"zero_gpu": True},
    )
    missing_path = packet.classify_endpoint(
        terminal, path_rows[:1], 32, {"zero_gpu": True}
    )
    missing_response = packet.classify_endpoint(
        terminal, path_rows, 31, {"zero_gpu": True}
    )
    invocation = {
        "endpoint_science_started": True,
        "endpoint_submission_count": 1,
    }
    owner_accepts_complete = owner.terminal_complete(
        positive, invocation, {"zero_gpu": True}
    )
    owner_rejects_incomplete = not owner.terminal_complete(
        positive, invocation, {"zero_gpu": False}
    )

    packet_sha = packet.sha256(PROJECT / "endpoint_execution_packet.py")
    with tempfile.TemporaryDirectory() as temporary:
        temporary_ready = pathlib.Path(temporary) / "READY.json"
        temporary_ready.write_text(
            json.dumps(
                {
                    "packet": {
                        "path": "endpoint_execution_packet.py",
                        "sha256": packet_sha,
                    },
                    "packet_manifest": {
                        "sha256": packet.sha256(INPUTS / "PACKET_MANIFEST.json")
                    },
                }
            )
        )
        original_ready = owner.READY
        owner.READY = temporary_ready
        try:
            binding = {
                "project": owner.PROJECT_NAME,
                "decision": "one_qkv_direct_c32_endpoint",
                "claim_allowed": True,
                "endpoint_submission_limit": 1,
                "endpoint_packet_ready_sha256": owner.sha256(temporary_ready),
                "accelerator": "nvidia-h200-sxm",
                "conservative_project_exposure_usd": 9.99,
                "absolute_release_deadline_epoch": 4102444800,
                "packet_sha256": packet_sha,
                "packet_manifest_sha256": packet.sha256(
                    INPUTS / "PACKET_MANIFEST.json"
                ),
            }
            binding_path = pathlib.Path(temporary) / "EXECUTION_BINDING.json"
            binding_path.write_text(json.dumps(binding))
            owner.validate_binding(
                binding_path
            )
            owner_binding_validation = True
        finally:
            owner.READY = original_ready

    driver_source = (INPUTS / "endpoint_driver.py").read_text()
    marker_before_release = driver_source.index(
        "atomic(\n            args.science_marker"
    ) < driver_source.rindex("release.wait(timeout=120)")
    packet_source = (PROJECT / "endpoint_execution_packet.py").read_text()
    server_supervises_driver = (
        'while kill -0 \\"$worker\\"' in packet_source
        and "SERVER_EXIT_DURING_DRIVER.log" in packet_source
        and "container_state" in packet_source
    )
    physical_zero_gpu_gate = (
        "COMPUTE_BEGIN" in packet_source
        and "MEMORY_BEGIN" in packet_source
        and "not compute_lines" in packet_source
        and 'all(line == "0" for line in memory_lines)' in packet_source
    )
    owner_source = (PROJECT / "endpoint_owner.py").read_text()
    owner_tree = ast.parse(owner_source)
    finally_calls_release = False
    repair_ready_call = False
    for node in ast.walk(owner_tree):
        if isinstance(node, ast.Try):
            for child in ast.walk(ast.Module(body=node.finalbody, type_ignores=[])):
                if (
                    isinstance(child, ast.Call)
                    and isinstance(child.func, ast.Name)
                    and child.func.id == "release"
                ):
                    finally_calls_release = True
        if (
            isinstance(node, ast.Constant)
            and node.value == "ready"
        ):
            repair_ready_call = True

    checks = {
        "exact_request_hashes": request_identity,
        "positive_adoption": positive["pass"]
        and positive["classification"] == "endpoint_positive",
        "negative_is_interpretable": negative["pass"]
        and negative["classification"] == "endpoint_negative",
        "missing_path_rejected": not missing_path["pass"],
        "missing_raw_response_rejected": not missing_response["pass"],
        "owner_accepts_only_complete_terminal": owner_accepts_complete
        and owner_rejects_incomplete,
        "owner_future_binding_validation": owner_binding_validation,
        "science_marker_immediately_precedes_release": marker_before_release,
        "server_liveness_supervises_driver": server_supervises_driver,
        "physical_zero_gpu_release_gate": physical_zero_gpu_gate,
        "owner_has_no_unconditional_finally_release": not finally_calls_release,
        "owner_contains_shared_repair_ready_path": repair_ready_call,
        "ambiguous_science_routes_to_no_replay_retrieval": (
            "if science_started is False:" in owner_source
            and 'retry_scope = "retrieval_or_terminal_adoption_no_endpoint_replay"'
            in owner_source
            and 'invocation["endpoint_science_started"] = None' in owner_source
        ),
        "endpoint_submission_limit": packet.offline_plan()["submission_limit"] == 1,
        "offline_plan_has_zero_actions": packet.offline_plan()[
            "network_or_accelerator_actions"
        ]
        == 0,
    }
    value = {
        "schema_version": 1,
        "pass": all(checks.values()),
        "checks": checks,
        "positive_fixture": positive,
        "negative_fixture": negative,
        "missing_path_fixture": missing_path,
        "missing_response_fixture": missing_response,
        "evidence_scope": "CPU/static/pure-decision logic only; no endpoint result",
        "endpoint_science_consumed": False,
        "endpoint_submission_count": 0,
    }
    temporary = args.output.with_suffix(args.output.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    json.loads(temporary.read_text())
    temporary.replace(args.output)
    print(json.dumps({"pass": value["pass"], "checks": checks}, sort_keys=True))
    return 0 if value["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
