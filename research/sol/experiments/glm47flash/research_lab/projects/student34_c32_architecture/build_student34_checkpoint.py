"""Build and fail-closed validate the byte-preserving 34-layer AWQ student."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path


HERE = Path(__file__).parent
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
EXPECTED_REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
EXPECTED_CONFIG_SHA = "079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9"
EXPECTED_INDEX_SHA = "b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695"
SKIPPED = (3, 7, 10, 13, 16, 20, 23, 26, 30, 33, 36, 39, 43)
RETAINED = tuple(i for i in range(47) if i not in SKIPPED)
MIB = 1024 * 1024


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def header(path: Path) -> tuple[int, dict[str, object]]:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return n + 8, json.loads(f.read(n))


def layer_id(name: str) -> int | None:
    prefix = "model.layers."
    if not name.startswith(prefix):
        return None
    tail = name[len(prefix):].split(".", 1)
    return int(tail[0]) if len(tail) == 2 and tail[0].isdigit() else None


def renamed(name: str, mapping: dict[int, int]) -> str | None:
    old = layer_id(name)
    if old is None:
        return name
    if old not in mapping:
        return None
    return name.replace(f"model.layers.{old}.", f"model.layers.{mapping[old]}.", 1)


def inventory() -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    index_path = SOURCE / "model.safetensors.index.json"
    if digest(SOURCE / "config.json") != EXPECTED_CONFIG_SHA or digest(index_path) != EXPECTED_INDEX_SHA:
        raise RuntimeError("source identity drift")
    source_map = json.loads(index_path.read_text())["weight_map"]
    tensors: dict[str, dict[str, object]] = {}
    for shard in sorted(set(source_map.values())):
        _, items = header(SOURCE / shard)
        tensors.update({name: {**item, "shard": shard} for name, item in items.items() if name != "__metadata__"})
    if set(source_map) != set(tensors):
        raise RuntimeError("source index/header key mismatch")
    return source_map, tensors


def student_config(mapping: dict[int, int]) -> dict[str, object]:
    config = json.loads((SOURCE / "config.json").read_text())
    config["num_hidden_layers"] = len(RETAINED)
    config["mlp_layer_types"] = [config["mlp_layer_types"][i] for i in RETAINED]
    config["num_nextn_predict_layers"] = 0
    ignore = config["quantization_config"].get("ignore", [])
    config["quantization_config"]["ignore"] = [new for old in ignore if (new := renamed(old, mapping)) is not None]
    return config


def write_shard(source: Path, output: Path, names: list[str], names_out: dict[str, str], tensors: dict[str, dict[str, object]]) -> None:
    offset, source_header = header(source)
    pieces = []
    for old in names:
        item = tensors[old]
        start, end = map(int, item["data_offsets"])
        pieces.append((names_out[old], item, start, end))
    result: dict[str, object] = {"__metadata__": source_header.get("__metadata__", {})}
    cursor = 0
    for name, item, start, end in pieces:
        row = {k: v for k, v in item.items() if k not in {"data_offsets", "shard"}}
        row["data_offsets"] = [cursor, cursor + end - start]
        result[name] = row
        cursor += end - start
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
    encoded += b" " * ((8 - (len(encoded) + 8) % 8) % 8)
    with source.open("rb") as src, output.open("wb") as dst:
        dst.write(struct.pack("<Q", len(encoded)))
        dst.write(encoded)
        for _, _, start, end in pieces:
            src.seek(offset + start)
            remaining = end - start
            while remaining:
                block = src.read(min(1 << 20, remaining))
                if not block:
                    raise RuntimeError("truncated source payload")
                dst.write(block)
                remaining -= len(block)


def materialize(root: Path, source_map: dict[str, str], tensors: dict[str, dict[str, object]], mapping: dict[int, int]) -> None:
    groups: dict[str, list[str]] = {}
    output_names: dict[str, str] = {}
    for old, shard in source_map.items():
        new = renamed(old, mapping)
        if new is not None:
            groups.setdefault(shard, []).append(old)
            output_names[old] = new
    output_map: dict[str, str] = {}
    for number, shard in enumerate(sorted(groups), 1):
        target = f"model-{number:05d}-of-{len(groups):05d}.safetensors"
        write_shard(SOURCE / shard, root / target, groups[shard], output_names, tensors)
        output_map.update({output_names[old]: target for old in groups[shard]})
    config = student_config(mapping)
    (root / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    total_payload = sum(int(tensors[old]["data_offsets"][1]) - int(tensors[old]["data_offsets"][0]) for old in output_names)
    (root / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": total_payload}, "weight_map": dict(sorted(output_map.items()))}, indent=2, sort_keys=True) + "\n")
    excluded = {"config.json", "model.safetensors.index.json", "model-files-manifest.json", "model-files.sha256"}
    for source in SOURCE.iterdir():
        if source.is_file() and not source.name.endswith(".safetensors") and source.name not in excluded:
            shutil.copy2(source, root / source.name)


def validate(root: Path, source_map: dict[str, str], tensors: dict[str, dict[str, object]], mapping: dict[int, int]) -> dict[str, object]:
    index = json.loads((root / "model.safetensors.index.json").read_text())
    config = json.loads((root / "config.json").read_text())
    actual: dict[str, dict[str, object]] = {}
    for shard in sorted(set(index["weight_map"].values())):
        _, items = header(root / shard)
        actual.update({name: item for name, item in items.items() if name != "__metadata__"})
    expected = {new for old in source_map if (new := renamed(old, mapping)) is not None}
    if set(index["weight_map"]) != expected or set(actual) != expected:
        raise RuntimeError("output key closure failed")
    if config["num_hidden_layers"] != 34 or len(config["mlp_layer_types"]) != 34 or config["num_nextn_predict_layers"] != 0:
        raise RuntimeError("layer-indexed config rewrite failed")
    if any((i := layer_id(name)) is not None and i >= 34 for name in expected):
        raise RuntimeError("dangling layer key")
    if any(layer_id(name) == 47 for name in expected):
        raise RuntimeError("MTP key retained")
    if any((i := layer_id(name)) is not None and i >= 34 for name in config["quantization_config"].get("ignore", [])):
        raise RuntimeError("dangling quantization-ignore key")
    payload = sum(int(tensors[old]["data_offsets"][1]) - int(tensors[old]["data_offsets"][0]) for old in source_map if renamed(old, mapping) is not None)
    if index["metadata"]["total_size"] != payload:
        raise RuntimeError("index payload total mismatch")
    return {"status": "PASS", "expected_key_count": len(expected), "config_model_type": config["model_type"], "architecture": config["architectures"], "quantization": config["quantization_config"], "index_total_size_exact": True, "no_mtp_layer47_tensors": True}


def write_runtime_manifest(root: Path) -> dict[str, object]:
    files = [p for p in sorted(root.iterdir()) if p.is_file() and p.name not in {"model-files-manifest.json", "model-files.sha256", "student34_checkpoint_manifest.json", "student34_runtime_preflight.json"}]
    rows = [{"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in files]
    shards = [row for row in rows if row["path"].endswith(".safetensors")]
    manifest = {"schema_version": 1, "repository": "local-derived/glm47flash-student34", "revision": EXPECTED_REVISION, "shard_count": len(shards), "weight_bytes": sum(row["bytes"] for row in shards), "files": rows}
    (root / "model-files-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (root / "model-files.sha256").write_text("".join(f"{row['sha256']}  {row['path']}\n" for row in rows))
    return manifest


def bound() -> dict[str, object]:
    old = {"c16": 36353.840072631836, "c32": 45851.0}
    removed_awq_mib = 4824665872 / MIB
    corrected = {"c16": old["c16"] - removed_awq_mib, "c24": (old["c16"] - removed_awq_mib) + 3.65625 * 1024 / 2, "c32": old["c32"] - removed_awq_mib}
    rate = 711.0323355381839
    return {"schema_version": 1, "evidence_class": "derived_corrected_memory_and_fixed_cost_bound_not_measured", "source": "distilled_depth_student_bound.json student_34_even plus corrected omitted removed-AWQ term", "removed_awq_mib_applied_each_concurrency": removed_awq_mib, "card_mib": 46068, "memory_mib": {key: {"peak": value, "headroom": 46068 - value} for key, value in corrected.items()}, "economics": {"planning_l40s_usd_per_hour": 1.1, "fixed_cost_endpoint_bound_output_tok_s": rate, "fixed_cost_endpoint_bound_usd_per_million": 1.1 * 1_000_000 / (3600 * rate), "promotion_output_tok_s": 594.466, "target_usd_per_million_output_tokens": 0.514}, "decision": "capacity_and_fixed_cost_gate_pass_only; throughput_and_quality_unmeasured"}


def main() -> None:
    source_map, tensors = inventory()
    mapping = {old: new for new, old in enumerate(RETAINED)}
    contract = {"source_revision": EXPECTED_REVISION, "source_config_sha256": EXPECTED_CONFIG_SHA, "source_index_sha256": EXPECTED_INDEX_SHA, "skipped_source_layers": SKIPPED, "source_to_student_layer": mapping}
    contract_sha = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    root = Path(f"/root/.cache/glm47flash-awq-student34-{contract_sha[:12]}")
    if not root.exists():
        temp = Path(tempfile.mkdtemp(prefix="student34-", dir="/root/.cache"))
        try:
            materialize(temp, source_map, tensors, mapping)
            os.replace(temp, root)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
    preflight = validate(root, source_map, tensors, mapping)
    runtime = write_runtime_manifest(root)
    manifest = {"schema_version": 1, "evidence_class": "content_addressed_byte_preserving_tensor_payload_rewrite", "source": contract, "student": {"layer_count": 34, "skipped_source_layers": list(SKIPPED), "source_to_student_layer": {str(k): v for k, v in mapping.items()}, "excluded_source_layer_ids": [47], "excluded_mtp": True}, "student_root": str(root), "manifest_contract_sha256": contract_sha, "student_config_sha256": digest(root / "config.json"), "student_index_sha256": digest(root / "model.safetensors.index.json"), "source_shard_sha256": {p.name: digest(p) for p in sorted(SOURCE.glob("*.safetensors"))}, "student_shard_sha256": {p.name: digest(p) for p in sorted(root.glob("*.safetensors"))}, "runtime_manifest_sha256": digest(root / "model-files-manifest.json"), "runtime": runtime}
    manifest["whole_manifest_payload_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    preflight.update({"student_root": str(root), "manifest_contract_sha256": contract_sha, "runtime_manifest": {"shard_count": runtime["shard_count"], "weight_bytes": runtime["weight_bytes"], "manifest_sha256": manifest["runtime_manifest_sha256"]}, "status": "STRUCTURAL_EXACT_PENDING_PINNED_LOADER_CONTRACT"})
    (root / "student34_checkpoint_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (root / "student34_runtime_preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    (HERE / "student34_checkpoint_manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (HERE / "student34_runtime_preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    (HERE / "student34_corrected_bound.json").write_text(json.dumps(bound(), indent=2, sort_keys=True) + "\n")
    print(json.dumps({"student_root": str(root), "manifest_contract_sha256": contract_sha, "weight_bytes": runtime["weight_bytes"], "keys": preflight["expected_key_count"]}, sort_keys=True))


if __name__ == "__main__":
    main()
