"""Build and verify the v2 physical-42 serving root without self-reference."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
PROVEN = HERE.parent / "distilled_depth_student_architecture" / "build_student39_checkpoint.py"
FROZEN_ROOT = Path("/root/.cache/glm47flash-awq-minimal-depth-4c84badbce22")
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
EXPECTED_LAYERS = 42
SKIPPED = (6, 15, 24, 33, 42)
PAYLOAD_POLICY = "v2-served-payload-allowlist-12-files"
PAYLOAD_NAMES = (
    ".gitattributes",
    "README.md",
    "chat_template.jinja",
    "config.json",
    "generation_config.json",
    "model-00001-of-00004.safetensors",
    "model-00002-of-00004.safetensors",
    "model-00003-of-00004.safetensors",
    "model-00004-of-00004.safetensors",
    "model.safetensors.index.json",
    "tokenizer.json",
    "tokenizer_config.json",
)
CONTROL_NAMES = ("model-files-manifest.json", "model-files.sha256")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_proven():
    spec = importlib.util.spec_from_file_location("proven_minimal_materializer", PROVEN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load proven materializer: {PROVEN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def contract(module, source_map: dict[str, str]) -> tuple[dict[str, object], str]:
    mapping = {source: student for student, source in enumerate(module.RETAINED)}
    value = {
        "schema_version": 2,
        "source_revision": module.EXPECTED_REVISION,
        "source_config_sha256": module.EXPECTED_CONFIG_SHA,
        "source_index_sha256": module.EXPECTED_INDEX_SHA,
        "skipped_source_layers": list(SKIPPED),
        "mapping": mapping,
        "artifact_policy": PAYLOAD_POLICY,
        "payload_allowlist": list(PAYLOAD_NAMES),
        "control_names": list(CONTROL_NAMES),
        "builder_sha256": digest(Path(__file__)),
        "source_tensor_keys": len(source_map),
    }
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return value, hashlib.sha256(encoded).hexdigest()


def payload_rows(root: Path) -> list[dict[str, object]]:
    return [{"path": name, "bytes": (root / name).stat().st_size, "sha256": digest(root / name)} for name in PAYLOAD_NAMES]


def write_controls(root: Path, revision: str) -> dict[str, object]:
    rows = payload_rows(root)
    shards = [row for row in rows if str(row["path"]).endswith(".safetensors")]
    manifest = {
        "schema_version": 2,
        "repository": "local-derived/glm47flash-minimal-depth42-v2",
        "revision": revision,
        "policy": PAYLOAD_POLICY,
        "shard_count": len(shards),
        "weight_bytes": sum(int(row["bytes"]) for row in shards),
        "files": rows,
    }
    (root / "model-files-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (root / "model-files.sha256").write_text("".join(f"{row['sha256']}  {row['path']}\n" for row in rows))
    return manifest


def materialize(module, root: Path, source_map, tensor_headers, source_headers, config, mapping) -> None:
    grouped: dict[str, list[str]] = {}
    renamed: dict[str, str] = {}
    for old, shard in source_map.items():
        new = module.rename(old, mapping)
        if new is not None:
            grouped.setdefault(shard, []).append(old)
            renamed[old] = new
    output_map: dict[str, str] = {}
    for ordinal, source_shard in enumerate(sorted(grouped), 1):
        output_shard = f"model-{ordinal:05d}-of-{len(grouped):05d}.safetensors"
        module.write_shard(SOURCE / source_shard, root / output_shard, grouped[source_shard], renamed, tensor_headers)
        for old in grouped[source_shard]:
            output_map[renamed[old]] = output_shard
    (root / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
    total = sum(int(tensor_headers[old]["data_offsets"][1] - tensor_headers[old]["data_offsets"][0]) for old in renamed)
    (root / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": total}, "weight_map": dict(sorted(output_map.items()))}, indent=2, sort_keys=True) + "\n")
    for name in PAYLOAD_NAMES:
        if name in {"config.json", "model.safetensors.index.json"} or name.endswith(".safetensors"):
            continue
        shutil.copy2(SOURCE / name, root / name)


def validate(module, root: Path, source_map, tensor_headers, mapping, runtime: dict[str, object]) -> dict[str, object]:
    if set(p.name for p in root.iterdir()) != set(PAYLOAD_NAMES) | set(CONTROL_NAMES):
        raise AssertionError("runtime root contains a non-serving or missing file")
    if any(p.is_symlink() for p in root.iterdir()):
        raise AssertionError("runtime root contains a symlink")
    index = json.loads((root / "model.safetensors.index.json").read_text())
    config = json.loads((root / "config.json").read_text())
    expected = {new for old in source_map if (new := module.rename(old, mapping)) is not None}
    if set(index["weight_map"]) != expected:
        raise AssertionError("index key closure mismatch")
    if config["num_hidden_layers"] != EXPECTED_LAYERS or len(config["mlp_layer_types"]) != EXPECTED_LAYERS:
        raise AssertionError("config layer closure mismatch")
    if config["num_nextn_predict_layers"] != 0 or any(module.layer_id(key) == 47 for key in expected):
        raise AssertionError("MTP closure mismatch")
    if any((layer := module.layer_id(key)) is not None and layer >= EXPECTED_LAYERS for key in expected):
        raise AssertionError("dangling layer closure mismatch")
    expected_payload = sum(int(tensor_headers[old]["data_offsets"][1] - tensor_headers[old]["data_offsets"][0]) for old in source_map if module.rename(old, mapping) is not None)
    if index["metadata"]["total_size"] != expected_payload:
        raise AssertionError("index total mismatch")
    frozen_hashes = {name: digest(FROZEN_ROOT / name) for name in PAYLOAD_NAMES if name.endswith(".safetensors")}
    actual_hashes = {name: digest(root / name) for name in frozen_hashes}
    if actual_hashes != frozen_hashes:
        raise AssertionError("new shards differ from frozen failed-root shards")
    if runtime["files"] != payload_rows(root):
        raise AssertionError("runtime manifest does not close over payload bytes")
    sha_lines = (root / "model-files.sha256").read_text().splitlines()
    if sha_lines != [f"{row['sha256']}  {row['path']}" for row in runtime["files"]]:
        raise AssertionError("checksum list closure mismatch")
    return {
        "status": "PASS",
        "payload_file_count": len(PAYLOAD_NAMES),
        "control_file_count": len(CONTROL_NAMES),
        "shard_byte_identity_to_frozen_root": True,
        "full_checksum_check": True,
        "config_index_key_layer_closure": True,
        "no_symlinks": True,
        "index_payload_bytes": expected_payload,
        "runtime_manifest_sha256": digest(root / "model-files-manifest.json"),
        "checksum_list_sha256": digest(root / "model-files.sha256"),
        "shard_sha256": actual_hashes,
    }


def run() -> dict[str, object]:
    module = load_proven()
    module.SKIPPED = SKIPPED
    module.RETAINED = tuple(i for i in range(47) if i not in SKIPPED)
    source_map, tensor_headers, source_headers = module.source_inventory()
    mapping = {source: student for student, source in enumerate(module.RETAINED)}
    config = module.student_config(json.loads((SOURCE / "config.json").read_text()), mapping)
    semantic_contract, contract_hash = contract(module, source_map)
    output = Path(f"/root/.cache/glm47flash-awq-minimal-depth42-v2-{contract_hash[:12]}")
    if not output.exists():
        temp = Path(tempfile.mkdtemp(prefix="minimal-depth42-v2-", dir="/root/.cache"))
        try:
            materialize(module, temp, source_map, tensor_headers, source_headers, config, mapping)
            runtime = write_controls(temp, module.EXPECTED_REVISION)
            validate(module, temp, source_map, tensor_headers, mapping, runtime)
            os.replace(temp, output)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
    runtime = json.loads((output / "model-files-manifest.json").read_text())
    verification = validate(module, output, source_map, tensor_headers, mapping, runtime)
    result = {
        "schema_version": 2,
        "status": "PASS",
        "root": str(output),
        "future_admission_identity": {"contract_sha256": contract_hash, "root_basename": output.name, "runtime_manifest_sha256": verification["runtime_manifest_sha256"], "checksum_list_sha256": verification["checksum_list_sha256"]},
        "semantic_contract": semantic_contract,
        "source": {"root": str(SOURCE), "revision": module.EXPECTED_REVISION, "config_sha256": module.EXPECTED_CONFIG_SHA, "index_sha256": module.EXPECTED_INDEX_SHA},
        "verification": verification,
        "idempotence": "PASS",
    }
    (HERE / "CLEAN_MATERIALIZATION_RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
