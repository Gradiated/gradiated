"""Materialize the checksum-closed nested 43-layer AWQ serving root."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
PROVEN = HERE.parent / "minimal_depth42_clean_materialization" / "build_clean_materialization.py"
SOURCE = Path("/root/.cache/glm47flash-awq-ab31d120")
EXPECTED_LAYERS = 43
SKIPPED = (6, 15, 24, 33)
PAYLOAD_NAMES = (
    ".gitattributes", "README.md", "chat_template.jinja", "config.json",
    "generation_config.json", "model-00001-of-00004.safetensors",
    "model-00002-of-00004.safetensors", "model-00003-of-00004.safetensors",
    "model-00004-of-00004.safetensors", "model.safetensors.index.json",
    "tokenizer.json", "tokenizer_config.json",
)
CONTROL_NAMES = ("model-files-manifest.json", "model-files.sha256")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_proven():
    spec = importlib.util.spec_from_file_location("depth42_writer", PROVEN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load proven writer: {PROVEN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_proven()


def payload_rows(root: Path) -> list[dict[str, object]]:
    return [{"path": name, "bytes": (root / name).stat().st_size, "sha256": digest(root / name)} for name in PAYLOAD_NAMES]


def write_controls(root: Path, revision: str) -> dict[str, object]:
    rows = payload_rows(root)
    manifest = {
        "schema_version": 2,
        "repository": "local-derived/glm47flash-minimal-depth43-v2",
        "revision": revision,
        "policy": "v2-served-payload-allowlist-12-files",
        "shard_count": 4,
        "weight_bytes": sum(int(row["bytes"]) for row in rows if str(row["path"]).endswith(".safetensors")),
        "files": rows,
    }
    (root / CONTROL_NAMES[0]).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    (root / CONTROL_NAMES[1]).write_text("".join(f"{row['sha256']}  {row['path']}\n" for row in rows))
    return manifest


def validate(module, root: Path, source_map, headers, mapping, runtime) -> dict[str, object]:
    names = {path.name for path in root.iterdir()}
    if names != set(PAYLOAD_NAMES) | set(CONTROL_NAMES) or any(path.is_symlink() for path in root.iterdir()):
        raise AssertionError("served payload closure failed")
    index = json.loads((root / "model.safetensors.index.json").read_text())
    config = json.loads((root / "config.json").read_text())
    expected = {new for old in source_map if (new := module.rename(old, mapping)) is not None}
    if set(index["weight_map"]) != expected:
        raise AssertionError("tensor key closure failed")
    if config["num_hidden_layers"] != EXPECTED_LAYERS or len(config["mlp_layer_types"]) != EXPECTED_LAYERS:
        raise AssertionError("layer closure failed")
    if config["num_nextn_predict_layers"] != 0 or any(module.layer_id(name) == 47 for name in expected):
        raise AssertionError("MTP closure failed")
    if any((layer := module.layer_id(name)) is not None and layer >= EXPECTED_LAYERS for name in expected):
        raise AssertionError("renumbered layer closure failed")
    payload = sum(int(headers[old]["data_offsets"][1] - headers[old]["data_offsets"][0]) for old in source_map if module.rename(old, mapping) is not None)
    if index["metadata"]["total_size"] != payload or runtime["files"] != payload_rows(root):
        raise AssertionError("payload accounting closure failed")
    if (root / CONTROL_NAMES[1]).read_text().splitlines() != [f"{row['sha256']}  {row['path']}" for row in runtime["files"]]:
        raise AssertionError("checksum closure failed")
    return {
        "status": "PASS", "payload_file_count": len(PAYLOAD_NAMES), "control_file_count": len(CONTROL_NAMES),
        "no_symlinks": True, "full_checksum_check": True, "config_index_key_layer_closure": True,
        "index_payload_bytes": payload, "runtime_manifest_sha256": digest(root / CONTROL_NAMES[0]),
        "checksum_list_sha256": digest(root / CONTROL_NAMES[1]),
        "shard_sha256": {path.name: digest(path) for path in sorted(root.glob("*.safetensors"))},
    }


def run() -> dict[str, object]:
    module = load_proven()
    module.SKIPPED, module.RETAINED = SKIPPED, tuple(layer for layer in range(47) if layer not in SKIPPED)
    source_map, headers, source_headers = module.source_inventory()
    mapping = {source: target for target, source in enumerate(module.RETAINED)}
    semantic = {
        "schema_version": 2, "source_revision": module.EXPECTED_REVISION,
        "source_config_sha256": module.EXPECTED_CONFIG_SHA, "source_index_sha256": module.EXPECTED_INDEX_SHA,
        "skipped_source_layers": list(SKIPPED), "mapping": mapping,
        "artifact_policy": "v2-served-payload-allowlist-12-files", "payload_allowlist": list(PAYLOAD_NAMES),
        "control_names": list(CONTROL_NAMES), "builder_sha256": digest(Path(__file__)), "source_tensor_keys": len(source_map),
    }
    contract_sha = hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    output = Path(f"/root/.cache/glm47flash-awq-minimal-depth43-v2-{contract_sha[:12]}")
    if not output.exists():
        temp = Path(tempfile.mkdtemp(prefix="minimal-depth43-v2-", dir="/root/.cache"))
        try:
            config = module.student_config(json.loads((SOURCE / "config.json").read_text()), mapping)
            module.materialize(temp, source_map, headers, source_headers, config, mapping)
            for extra in temp.iterdir():
                if extra.name not in PAYLOAD_NAMES:
                    if extra.is_dir(): shutil.rmtree(extra)
                    else: extra.unlink()
            runtime = write_controls(temp, module.EXPECTED_REVISION)
            validate(module, temp, source_map, headers, mapping, runtime)
            os.replace(temp, output)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
    runtime = json.loads((output / CONTROL_NAMES[0]).read_text())
    verification = validate(module, output, source_map, headers, mapping, runtime)
    result = {"schema_version": 2, "status": "PASS", "root": str(output),
              "future_admission_identity": {"contract_sha256": contract_sha, "root_basename": output.name,
                 "runtime_manifest_sha256": verification["runtime_manifest_sha256"], "checksum_list_sha256": verification["checksum_list_sha256"]},
              "semantic_contract": semantic, "source": {"root": str(SOURCE), "revision": module.EXPECTED_REVISION,
                 "config_sha256": module.EXPECTED_CONFIG_SHA, "index_sha256": module.EXPECTED_INDEX_SHA},
              "verification": verification, "idempotence": "PASS"}
    (HERE / "CLEAN_MATERIALIZATION_RESULT.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


if __name__ == "__main__":
    print(json.dumps(run(), indent=2, sort_keys=True))
