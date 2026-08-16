"""Materialize and statically validate the nominated 39-layer AWQ student.

The rewrite is byte-preserving for retained tensor payloads; it only changes
tensor names, safetensors offsets, shard headers, and the layer-count config.
No model loader or CUDA is required.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import tempfile
from pathlib import Path

SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
BF16_SOURCE = Path("/root/.cache/glm47flash-bf16-33faccf4")
EXPECTED_REVISION = "ab31d120fbe79988fe2a0259993cf3c222aa8881"
EXPECTED_CONFIG_SHA = "079f8fcd477b07378deafc21ecc5c3b974bf109ce5c9115854d97f88fa7622b9"
EXPECTED_INDEX_SHA = "b9c53433e94f2fe7870cdbc3fcb6ed1431eb500c5242a039de93fef4bb988695"
SKIPPED = (5, 10, 15, 20, 26, 31, 36, 41)
SOURCE_SERVING = tuple(range(47))
RETAINED = tuple(i for i in SOURCE_SERVING if i not in SKIPPED)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_header(path: Path) -> tuple[int, dict[str, object]]:
    with path.open("rb") as f:
        n = struct.unpack("<Q", f.read(8))[0]
        return n + 8, json.loads(f.read(n))


def layer_id(name: str) -> int | None:
    prefix = "model.layers."
    if not name.startswith(prefix):
        return None
    tail = name[len(prefix) :]
    if "." not in tail:
        return None
    value = tail.split(".", 1)[0]
    return int(value) if value.isdigit() else None


def rename(name: str, mapping: dict[int, int]) -> str | None:
    i = layer_id(name)
    if i is None:
        return name
    if i not in mapping:
        return None
    return name.replace(f"model.layers.{i}.", f"model.layers.{mapping[i]}.", 1)


def source_inventory() -> tuple[dict[str, str], dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    index_path = SOURCE / "model.safetensors.index.json"
    assert digest(SOURCE / "config.json") == EXPECTED_CONFIG_SHA, "config drift"
    assert digest(index_path) == EXPECTED_INDEX_SHA, "index drift"
    index = json.loads(index_path.read_text())
    headers: dict[str, dict[str, object]] = {}
    tensor_headers: dict[str, dict[str, object]] = {}
    for shard in sorted(set(index["weight_map"].values())):
        _, h = read_header(SOURCE / shard)
        headers[shard] = h
        for name, item in h.items():
            if name != "__metadata__":
                tensor_headers[name] = {**item, "shard": shard}
    assert set(index["weight_map"]) == set(tensor_headers), "source index/header mismatch"
    return index["weight_map"], tensor_headers, headers


def student_config(source: dict[str, object], mapping: dict[int, int]) -> dict[str, object]:
    config = json.loads(json.dumps(source))
    config["num_hidden_layers"] = len(RETAINED)
    config["mlp_layer_types"] = [source["mlp_layer_types"][i] for i in RETAINED]
    config["num_nextn_predict_layers"] = 0
    quant = config.get("quantization_config")
    if isinstance(quant, dict) and isinstance(quant.get("ignore"), list):
        quant["ignore"] = [new for old in quant["ignore"] if (new := rename(old, mapping)) is not None]
    return config


def write_shard(source_path: Path, output_path: Path, names: list[str], renamed: dict[str, str], headers: dict[str, dict[str, object]]) -> None:
    source_header_bytes, source_header = read_header(source_path)
    items: list[tuple[str, dict[str, object], int, int]] = []
    for old in names:
        item = headers[old]
        start, end = item["data_offsets"]
        items.append((renamed[old], item, int(start), int(end)))
    new_header: dict[str, object] = {"__metadata__": source_header.get("__metadata__", {})}
    cursor = 0
    for new, item, start, end in items:
        copied = {k: v for k, v in item.items() if k != "data_offsets"}
        copied["data_offsets"] = [cursor, cursor + (end - start)]
        new_header[new] = copied
        cursor += end - start
    encoded = json.dumps(new_header, separators=(",", ":"), sort_keys=True).encode()
    encoded += b" " * ((8 - ((len(encoded) + 8) % 8)) % 8)
    with source_path.open("rb") as src, output_path.open("wb") as out:
        out.write(struct.pack("<Q", len(encoded)))
        out.write(encoded)
        for _, _, start, end in items:
            src.seek(source_header_bytes + start)
            remaining = end - start
            while remaining:
                chunk = src.read(min(1 << 20, remaining))
                if not chunk:
                    raise IOError("source tensor payload truncated")
                out.write(chunk)
                remaining -= len(chunk)


def materialize(root: Path, source_map: dict[str, str], tensor_headers: dict[str, dict[str, object]], source_headers: dict[str, dict[str, object]], config: dict[str, object], mapping: dict[int, int]) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    grouped: dict[str, list[str]] = {}
    renamed: dict[str, str] = {}
    for old, shard in source_map.items():
        new = rename(old, mapping)
        if new is None:
            continue
        renamed[old] = new
        grouped.setdefault(shard, []).append(old)
    output_map: dict[str, str] = {}
    for ordinal, source_shard in enumerate(sorted(grouped), 1):
        output_shard = f"model-{ordinal:05d}-of-{len(grouped):05d}.safetensors"
        write_shard(SOURCE / source_shard, root / output_shard, grouped[source_shard], renamed, tensor_headers)
        for old in grouped[source_shard]:
            output_map[renamed[old]] = output_shard
    total = sum((root / shard).stat().st_size for shard in set(output_map.values()))
    (root / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    (root / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": sum(int(tensor_headers[x]["data_offsets"][1] - tensor_headers[x]["data_offsets"][0]) for x in renamed)}, "weight_map": dict(sorted(output_map.items()))}, indent=2, sort_keys=True) + "\n")
    for source_file in SOURCE.iterdir():
        if source_file.name.endswith(".safetensors") or source_file.name in {"config.json", "model.safetensors.index.json", "model-files.sha256", "model-files-manifest.json"}:
            continue
        target = root / source_file.name
        if source_file.is_file():
            shutil.copy2(source_file, target)
    manifest = {
        "schema_version": 1,
        "evidence_class": "source_bound_materialized_byte_preserving_rewrite",
        "source": {"root": str(SOURCE), "revision": EXPECTED_REVISION, "config_sha256": EXPECTED_CONFIG_SHA, "index_sha256": EXPECTED_INDEX_SHA},
        "student": {"layer_count": len(RETAINED), "skipped_source_layers": list(SKIPPED), "source_to_student_layer": {str(k): v for k, v in mapping.items()}, "excluded_source_layer_ids": [47], "excluded_mtp": True},
        "tensor_counts": {"source": len(source_map), "student": len(renamed), "removed": len(source_map) - len(renamed)},
        "student_config_sha256": digest(root / "config.json"),
        "student_index_sha256": digest(root / "model.safetensors.index.json"),
        "materialized_bytes": total,
        "output_files": sorted(p.name for p in root.iterdir()),
    }
    return manifest


def validate(root: Path, manifest: dict[str, object], source_map: dict[str, str], tensor_headers: dict[str, dict[str, object]], mapping: dict[int, int]) -> dict[str, object]:
    index = json.loads((root / "model.safetensors.index.json").read_text())
    config = json.loads((root / "config.json").read_text())
    output_headers: dict[str, dict[str, object]] = {}
    for shard in sorted(set(index["weight_map"].values())):
        _, h = read_header(root / shard)
        output_headers.update({k: v for k, v in h.items() if k != "__metadata__"})
    expected = {new for old in source_map if (new := rename(old, mapping)) is not None}
    assert set(index["weight_map"]) == expected == set(output_headers), "student key closure failed"
    assert config["num_hidden_layers"] == 39 and len(config["mlp_layer_types"]) == 39
    assert config["num_nextn_predict_layers"] == 0
    assert not any(layer_id(k) == 47 for k in expected)
    assert all(layer_id(k) is None or layer_id(k) < 39 for k in expected)
    assert index["metadata"]["total_size"] == sum(int(tensor_headers[old]["data_offsets"][1] - tensor_headers[old]["data_offsets"][0]) for old in source_map if rename(old, mapping) is not None)
    return {"status": "PASS", "config_model_type": config["model_type"], "quant_method": config["quantization_config"]["quant_method"], "key_consumption": "PASS", "no_dangling_source_layers": True, "no_mtp_layer47_tensors": True, "index_total_size_exact": True, "runtime_identity": {"architecture": config["architectures"], "model_type": config["model_type"], "quantization": "compressed-tensors pack-quantized W4 group-32", "pinned_runtime": "vllm/vllm-openai:v0.15.0 sha256:97187c9535fd6d6040444d68bb073f17344fd454e9241cc7a4e998141f244543"}}


def write_runtime_manifest(root: Path, revision: str) -> dict[str, object]:
    excluded = {"model-files-manifest.json", "model-files.sha256", "student39_checkpoint_manifest.json", "student39_runtime_preflight.json"}
    files = [p for p in sorted(root.iterdir()) if p.is_file() and p.name not in excluded and not p.name.startswith(".campaign-")]
    rows = [{"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in files]
    shards = [row for row in rows if row["path"].endswith(".safetensors")]
    manifest = {"schema_version": 1, "repository": "local-derived/glm47flash-student39", "revision": revision, "shard_count": len(shards), "weight_bytes": sum(row["bytes"] for row in shards), "files": rows}
    (root / "model-files-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (root / "model-files.sha256").write_text("".join(f"{row['sha256']}  {row['path']}\n" for row in rows))
    return manifest


def main() -> None:
    source_map, tensor_headers, source_headers = source_inventory()
    mapping = {source: student for student, source in enumerate(RETAINED)}
    config = student_config(json.loads((SOURCE / "config.json").read_text()), mapping)
    contract = {"source_revision": EXPECTED_REVISION, "skipped": SKIPPED, "mapping": mapping, "source_config_sha256": EXPECTED_CONFIG_SHA, "source_index_sha256": EXPECTED_INDEX_SHA}
    manifest_hash = hashlib.sha256(json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output = Path(f"/root/.cache/glm47flash-awq-student39-{manifest_hash[:12]}")
    if output.exists() and (output / "student39_checkpoint_manifest.json").exists():
        manifest = json.loads((output / "student39_checkpoint_manifest.json").read_text())
    else:
        temp = Path(tempfile.mkdtemp(prefix="student39-", dir="/root/.cache"))
        try:
            manifest = materialize(temp, source_map, tensor_headers, source_headers, config, mapping)
            if output.exists():
                raise FileExistsError(f"unexpected pre-existing output {output}")
            os.replace(temp, output)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
        (output / "student39_checkpoint_manifest.json").write_text(json.dumps({**manifest, "manifest_contract_sha256": manifest_hash}, indent=2, sort_keys=True) + "\n")
    preflight = validate(output, manifest, source_map, tensor_headers, mapping)
    runtime_manifest = write_runtime_manifest(output, EXPECTED_REVISION)
    preflight["runtime_manifest"] = {"shard_count": runtime_manifest["shard_count"], "weight_bytes": runtime_manifest["weight_bytes"], "manifest_sha256": digest(output / "model-files-manifest.json")}
    manifest["source_shard_sha256"] = {p.name: digest(p) for p in sorted(SOURCE.glob("*.safetensors"))}
    manifest["student_shard_sha256"] = {p.name: digest(p) for p in sorted(output.glob("*.safetensors"))}
    manifest["whole_manifest_payload_sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    preflight["student_root"] = str(output)
    preflight["manifest_contract_sha256"] = manifest_hash
    (output / "student39_runtime_preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    here = Path(__file__).parent
    (here / "student39_checkpoint_manifest.json").write_text(json.dumps({**manifest, "student_root": str(output), "manifest_contract_sha256": manifest_hash}, indent=2, sort_keys=True) + "\n")
    (here / "student39_runtime_preflight.json").write_text(json.dumps(preflight, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"student_root": str(output), "manifest_contract_sha256": manifest_hash, "preflight": preflight}, indent=2))


if __name__ == "__main__":
    main()
