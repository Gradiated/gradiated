from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import resource
import struct
import time
from pathlib import Path
from typing import Any


STOCK_GLOBAL_LAYERS = [5, 11, 17, 23, 29, 35, 41, 47, 53, 59]
ALTERNATING_RETAINED = [5, 17, 29, 41, 53]
TENSOR_TEMPLATE = (
    "model.language_model.layers.{layer}.post_attention_layernorm.weight"
)
HASH_CHUNK_BYTES = 16 * 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


def bf16_to_float32(raw: bytes) -> list[float]:
    if len(raw) % 2:
        raise ValueError("BF16 payload must contain an even number of bytes")
    words = struct.unpack(f"<{len(raw) // 2}H", raw)
    return [
        struct.unpack("<f", struct.pack("<I", word << 16))[0] for word in words
    ]


def rms(values: list[float]) -> float:
    if not values:
        raise ValueError("cannot compute RMS of an empty tensor")
    return math.sqrt(math.fsum(value * value for value in values) / len(values))


def rank_layers(scores: dict[int, float], retained_count: int) -> list[int]:
    return [
        layer
        for layer, _ in sorted(scores.items(), key=lambda item: (-item[1], item[0]))[
            :retained_count
        ]
    ]


def converted_layers(retained: list[int]) -> list[int]:
    retained_set = set(retained)
    return [layer for layer in STOCK_GLOBAL_LAYERS if layer not in retained_set]


def attention_work(retained: list[int]) -> dict[str, int]:
    unique = set(retained)
    if len(retained) != 5 or len(unique) != 5 or not unique <= set(
        STOCK_GLOBAL_LAYERS
    ):
        raise ValueError("placement must retain five unique stock global layers")
    return {"total_layers": 60, "local_layers": 55, "global_layers": 5}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def resolve_and_verify_inputs(
    preregistration: dict[str, Any], preregistration_path: Path
) -> tuple[list[dict[str, Any]], int]:
    verified = []
    logical_bytes = 0
    for item in preregistration["direct_inputs"]:
        path = (preregistration_path.parent / item["path"]).resolve()
        observed = sha256_file(path)
        if observed != item["sha256"]:
            raise ValueError(
                f"input hash mismatch for {path}: {observed} != {item['sha256']}"
            )
        size = path.stat().st_size
        logical_bytes += size
        verified.append(
            {
                "path": str(path),
                "sha256": observed,
                "size_bytes": size,
                "role": item["role"],
            }
        )
    return verified, logical_bytes


def find_input(verified: list[dict[str, Any]], suffix: str) -> Path:
    matches = [Path(item["path"]) for item in verified if item["path"].endswith(suffix)]
    if len(matches) != 1:
        raise ValueError(f"expected one direct input ending in {suffix}, found {matches}")
    return matches[0]


def read_safetensors_header(path: Path) -> tuple[int, dict[str, Any]]:
    with path.open("rb") as handle:
        raw_length = handle.read(8)
        if len(raw_length) != 8:
            raise ValueError(f"truncated safetensors header length in {path}")
        header_length = struct.unpack("<Q", raw_length)[0]
        header = json.loads(handle.read(header_length))
    if not isinstance(header, dict):
        raise ValueError("safetensors header must be a JSON object")
    return 8 + header_length, header


def read_tensor(
    shard: Path, data_start: int, header: dict[str, Any], name: str
) -> tuple[bytes, dict[str, Any]]:
    metadata = header.get(name)
    if not isinstance(metadata, dict):
        raise ValueError(f"missing tensor {name}")
    if metadata.get("dtype") != "BF16" or metadata.get("shape") != [5376]:
        raise ValueError(f"unexpected tensor contract for {name}: {metadata}")
    start, end = metadata["data_offsets"]
    with shard.open("rb") as handle:
        handle.seek(data_start + start)
        raw = handle.read(end - start)
    if len(raw) != end - start:
        raise ValueError(f"truncated tensor payload for {name}")
    return raw, metadata


def stable_terminal_bytes(terminal: dict[str, Any]) -> bytes:
    storage = terminal["resource_accounting"]["storage"]
    prior = None
    while storage["terminal_bytes_written"] != prior:
        prior = storage["terminal_bytes_written"]
        serialized = json.dumps(terminal, indent=2, sort_keys=True) + "\n"
        storage["terminal_bytes_written"] = len(serialized.encode())
    return (json.dumps(terminal, indent=2, sort_keys=True) + "\n").encode()


def write_atomic(path: Path, payload: bytes) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temporary.open("wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def execute(preregistration_path: Path, output_path: Path) -> dict[str, Any]:
    wall_start = time.perf_counter()
    cpu_start = resource.getrusage(resource.RUSAGE_SELF)
    preregistration = load_json(preregistration_path)
    if preregistration["selector"]["eligible_stock_global_layers"] != STOCK_GLOBAL_LAYERS:
        raise ValueError("preregistered stock global layers changed")
    if preregistration["comparator"]["retained_global_layers"] != ALTERNATING_RETAINED:
        raise ValueError("preregistered comparator changed")

    verified, logical_hash_bytes = resolve_and_verify_inputs(
        preregistration, preregistration_path
    )
    config_path = find_input(verified, "config.json")
    index_path = find_input(verified, "model.safetensors.index.json")
    shard_path = find_input(verified, "model-00002-of-00002.safetensors")
    execution_path = find_input(
        verified, "HYBRID_55L5G_H200_EXECUTION_TERMINAL.json"
    )
    model_source_path = find_input(verified, "models/gemma4_causal.py")

    text_config = load_json(config_path)["text_config"]
    layer_types = text_config["layer_types"]
    observed_globals = [
        index for index, layer_type in enumerate(layer_types)
        if layer_type == "full_attention"
    ]
    if len(layer_types) != 60 or observed_globals != STOCK_GLOBAL_LAYERS:
        raise ValueError("checkpoint architecture does not match the 60-layer contract")

    index = load_json(index_path)["weight_map"]
    data_start, header = read_safetensors_header(shard_path)
    rows = []
    scores: dict[int, float] = {}
    tensor_bytes_read = 0
    for layer in STOCK_GLOBAL_LAYERS:
        tensor_name = TENSOR_TEMPLATE.format(layer=layer)
        if index.get(tensor_name) != shard_path.name:
            raise ValueError(f"index maps {tensor_name} to {index.get(tensor_name)}")
        raw, metadata = read_tensor(shard_path, data_start, header, tensor_name)
        values = bf16_to_float32(raw)
        score = rms(values)
        scores[layer] = score
        tensor_bytes_read += len(raw)
        rows.append(
            {
                "layer": layer,
                "tensor": tensor_name,
                "tensor_sha256": hashlib.sha256(raw).hexdigest(),
                "dtype": metadata["dtype"],
                "shape": metadata["shape"],
                "payload_bytes": len(raw),
                "post_attention_residual_scale_rms": score,
            }
        )

    selected = rank_layers(scores, 5)
    selected_converted = converted_layers(selected)
    alternating_converted = converted_layers(ALTERNATING_RETAINED)
    execution = load_json(execution_path)
    if (
        execution["proxy"]["candidate_layers"] != ALTERNATING_RETAINED
        or execution["proxy"]["copied_local_layers"] != alternating_converted
    ):
        raise ValueError("execution terminal does not bind the exact comparator")

    source_text = model_source_path.read_text()
    attention_call = source_text.index("hidden_states = self.self_attn(")
    post_attention_norm = source_text.index(
        "hidden_states = self.post_attention_layernorm(hidden_states)", attention_call
    )
    residual_consumer = source_text.index(
        "hidden_states, residual = self.pre_feedforward_layernorm(",
        post_attention_norm,
    )
    if not attention_call < post_attention_norm < residual_consumer:
        raise ValueError("pinned source does not preserve the causal branch ordering")

    ranked = sorted(rows, key=lambda row: (-row["post_attention_residual_scale_rms"], row["layer"]))
    fifth = ranked[4]["post_attention_residual_scale_rms"]
    sixth = ranked[5]["post_attention_residual_scale_rms"]
    selected_sum = math.fsum(scores[layer] for layer in selected)
    alternating_sum = math.fsum(scores[layer] for layer in ALTERNATING_RETAINED)
    selector_work = attention_work(selected)
    comparator_work = attention_work(ALTERNATING_RETAINED)
    if selector_work != comparator_work:
        raise ValueError("attention work changed between placements")

    cpu_end = resource.getrusage(resource.RUSAGE_SELF)
    implementation_path = Path(__file__).resolve()
    test_path = implementation_path.with_name("test_layer_importance_selector.py")
    preregistration_sha = sha256_file(preregistration_path)
    implementation_sha = sha256_file(implementation_path)
    test_sha = sha256_file(test_path)
    terminal = {
        "schema_version": 1,
        "classification": "offline_scientific_terminal",
        "project": "gemma4_hybrid_attention_layer_importance_recovery",
        "completed_at_utc": dt.datetime.now(dt.UTC).isoformat(),
        "result": "typed_negative_no_executable_quality_recovery_consumer",
        "selector_outcome": "content_addressed_signal_distinguishes_placement",
        "scope": {
            "gpu_claimed": False,
            "ssh_used": False,
            "provider_or_endpoint_used": False,
            "checkpoint_shards_copied": 0,
            "selector_sweeps": 0,
            "training_runs": 0,
            "prior_science_replayed": False,
        },
        "identity": {
            "preregistration": {
                "path": str(preregistration_path.resolve()),
                "sha256": preregistration_sha,
            },
            "implementation": {
                "path": str(implementation_path),
                "sha256": implementation_sha,
            },
            "test": {"path": str(test_path), "sha256": test_sha},
            "direct_inputs": verified,
        },
        "signal": {
            **preregistration["signal"],
            "checkpoint_tensor_rows": rows,
            "ranking": [row["layer"] for row in ranked],
            "fifth_to_sixth_absolute_margin": fifth - sixth,
            "fifth_to_sixth_relative_margin": (fifth - sixth) / sixth,
        },
        "placements": {
            "selector": {
                "rule": preregistration["selector"]["rule"],
                "retained_global_layers": selected,
                "converted_to_local_layers": selected_converted,
                "retained_signal_sum": selected_sum,
            },
            "exact_alternating_comparator": {
                "retained_global_layers": ALTERNATING_RETAINED,
                "converted_to_local_layers": alternating_converted,
                "retained_signal_sum": alternating_sum,
            },
            "comparison": {
                "same_placement": selected == ALTERNATING_RETAINED,
                "retained_only_by_selector": sorted(
                    set(selected) - set(ALTERNATING_RETAINED)
                ),
                "retained_only_by_alternating": sorted(
                    set(ALTERNATING_RETAINED) - set(selected)
                ),
                "selector_signal_sum_fractional_gain": (
                    selected_sum / alternating_sum - 1.0
                ),
            },
        },
        "quality_recovery": {
            "causal_argument": (
                "Converting a stock global layer changes its attention branch. "
                "The pinned decoder applies the scored learned RMSNorm immediately "
                "after attention and before residual addition; retaining the five "
                "largest learned branch scales preserves the global modules with "
                "the greatest direct residual-injection scale under this signal."
            ),
            "quality_estimate": None,
            "uncertainty": {
                "type": "unbounded_epistemic",
                "quantified_quality_recovery": False,
                "reason": (
                    "Checkpoint scale alone contains no activation, routing, task, "
                    "or downstream-cancellation observations. The numeric ranking "
                    "is deterministic, but its GPQA-Diamond, TauBench, long-context, "
                    "tool-use, multimodal, and endpoint-quality effect is unknown."
                ),
            },
            "later_consumer": {
                "kind": "none",
                "reason": (
                    "No existing content-addressed lab input contains representative "
                    "per-layer attention/residual captures or raw paired quality "
                    "captures for this selected 55L5G placement, and the available "
                    "stock paired-quality runner cannot materialize or consume the "
                    "selected conversion. This turn forbids staging, training, GPU, "
                    "and endpoint execution."
                ),
            },
            "deployability_authorized": False,
        },
        "performance_invariant": {
            "selector_attention_work_count": selector_work,
            "alternating_attention_work_count": comparator_work,
            "proof": (
                "Both sets are five unique members of the same ten stock full-"
                "attention layers in the same 60-layer checkpoint. Each converts "
                "the other five stock globals to local, so both execute exactly "
                "55 local and 5 global attention layers for every token position "
                "and batch element; layer identity changes, attention-type work "
                "multiplicity does not."
            ),
            "inherited_component_attention_reduction_fraction": execution[
                "measurement"
            ]["weighted_attention_reduction_fraction"],
            "inherited_not_remeasured": True,
        },
        "resource_accounting": {
            "cpu": {
                "wall_seconds": time.perf_counter() - wall_start,
                "user_seconds": cpu_end.ru_utime - cpu_start.ru_utime,
                "system_seconds": cpu_end.ru_stime - cpu_start.ru_stime,
                "peak_rss_kib": cpu_end.ru_maxrss,
                "input_blocks": cpu_end.ru_inblock - cpu_start.ru_inblock,
                "measurement_boundary": "immediately before terminal serialization",
            },
            "storage": {
                "logical_direct_input_bytes_hashed": logical_hash_bytes,
                "checkpoint_tensor_payload_bytes_read": tensor_bytes_read,
                "checkpoint_bytes_copied": 0,
                "terminal_bytes_written": 0,
                "analysis_artifact_bytes_created": 0,
            },
            "gpu_seconds": 0,
            "network_requests": 0,
            "provider_mutations": 0,
            "actual_spend_usd": 0.0,
        },
    }
    artifact_sizes = (
        preregistration_path.stat().st_size
        + implementation_path.stat().st_size
        + test_path.stat().st_size
    )
    cpu_final = resource.getrusage(resource.RUSAGE_SELF)
    cpu_accounting = terminal["resource_accounting"]["cpu"]
    cpu_accounting.update(
        {
            "wall_seconds": time.perf_counter() - wall_start,
            "user_seconds": cpu_final.ru_utime - cpu_start.ru_utime,
            "system_seconds": cpu_final.ru_stime - cpu_start.ru_stime,
            "peak_rss_kib": cpu_final.ru_maxrss,
            "input_blocks": cpu_final.ru_inblock - cpu_start.ru_inblock,
        }
    )
    payload = stable_terminal_bytes(terminal)
    while True:
        total_created = artifact_sizes + len(payload)
        storage = terminal["resource_accounting"]["storage"]
        if storage["analysis_artifact_bytes_created"] == total_created:
            break
        storage["analysis_artifact_bytes_created"] = total_created
        payload = stable_terminal_bytes(terminal)
    write_atomic(output_path, payload)
    return terminal


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preregistration",
        type=Path,
        default=Path(__file__).with_name("SIGNAL_PREREGISTRATION.json"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).with_name(
            "HYBRID_ATTENTION_LAYER_IMPORTANCE_OFFLINE_TERMINAL.json"
        ),
    )
    args = parser.parse_args()
    terminal = execute(args.preregistration.resolve(), args.output.resolve())
    print(
        json.dumps(
            {
                "result": terminal["result"],
                "selected": terminal["placements"]["selector"][
                    "retained_global_layers"
                ],
                "terminal": str(args.output.resolve()),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
