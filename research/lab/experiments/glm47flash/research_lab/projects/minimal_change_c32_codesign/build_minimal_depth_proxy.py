"""Materialize the smallest screened physical-depth c32 proxy.

This reuses the byte-preserving shard writer from the proven student39
materializer and changes only the retained serving-layer set.
"""
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
SKIPPED = (6, 15, 24, 33, 42)
EXPECTED_LAYERS = 42


def load_proven():
    spec = importlib.util.spec_from_file_location("proven_student_materializer", PROVEN)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load proven materializer: {PROVEN}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate(module, root: Path, source_map, tensor_headers, mapping) -> dict[str, object]:
    index = json.loads((root / "model.safetensors.index.json").read_text())
    config = json.loads((root / "config.json").read_text())
    expected = {
        new for old in source_map if (new := module.rename(old, mapping)) is not None
    }
    actual = set(index["weight_map"])
    if actual != expected:
        raise AssertionError(f"key closure mismatch: {len(actual)} != {len(expected)}")
    if config["num_hidden_layers"] != EXPECTED_LAYERS:
        raise AssertionError("layer count mismatch")
    if len(config["mlp_layer_types"]) != EXPECTED_LAYERS:
        raise AssertionError("mlp layer type count mismatch")
    if config["num_nextn_predict_layers"] != 0:
        raise AssertionError("MTP was not disabled")
    if any(module.layer_id(key) == 47 for key in actual):
        raise AssertionError("MTP layer remains")
    if any((layer := module.layer_id(key)) is not None and layer >= EXPECTED_LAYERS for key in actual):
        raise AssertionError("dangling layer remains")
    expected_payload = sum(
        int(tensor_headers[old]["data_offsets"][1] - tensor_headers[old]["data_offsets"][0])
        for old in source_map
        if module.rename(old, mapping) is not None
    )
    if index["metadata"]["total_size"] != expected_payload:
        raise AssertionError("index payload total mismatch")
    return {
        "status": "PASS",
        "key_closure": "PASS",
        "index_payload_exact": True,
        "layer_count": EXPECTED_LAYERS,
        "retained_source_layers": list(module.RETAINED),
        "skipped_source_layers": list(SKIPPED),
        "excluded_mtp_layer": 47,
        "quantization": config["quantization_config"]["quant_method"],
        "loader_route": "proven student39 byte-preserving compressed-tensors W4 materializer; runtime model instantiation still requires CUDA",
        "loader_consumed_missing_unexpected": "UNMEASURED_NO_MODEL_INSTANTIATION",
    }


def main() -> None:
    module = load_proven()
    module.SKIPPED = SKIPPED
    module.RETAINED = tuple(i for i in module.SOURCE_SERVING if i not in SKIPPED)
    if len(module.RETAINED) != EXPECTED_LAYERS:
        raise AssertionError("unexpected retained layer count")
    source_map, tensor_headers, source_headers = module.source_inventory()
    mapping = {source: student for student, source in enumerate(module.RETAINED)}
    config = module.student_config(json.loads((module.SOURCE / "config.json").read_text()), mapping)
    contract = {
        "source_revision": module.EXPECTED_REVISION,
        "source_config_sha256": module.EXPECTED_CONFIG_SHA,
        "source_index_sha256": module.EXPECTED_INDEX_SHA,
        "skipped_source_layers": list(SKIPPED),
        "mapping": mapping,
        "materializer": digest(PROVEN),
    }
    contract_hash = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    output = Path(f"/root/.cache/glm47flash-awq-minimal-depth-{contract_hash[:12]}")
    if not output.exists():
        temp = Path(tempfile.mkdtemp(prefix="minimal-depth-", dir="/root/.cache"))
        try:
            manifest = module.materialize(
                temp, source_map, tensor_headers, source_headers, config, mapping
            )
            os.replace(temp, output)
        except Exception:
            shutil.rmtree(temp, ignore_errors=True)
            raise
    else:
        manifest = json.loads((output / "minimal_depth_checkpoint_manifest.json").read_text())["materializer_manifest"]
    verification = validate(module, output, source_map, tensor_headers, mapping)
    runtime_manifest = module.write_runtime_manifest(output, module.EXPECTED_REVISION)
    result = {
        "schema_version": 1,
        "evidence_class": "measured_local_content_addressed_checkpoint_rewrite_and_structural_loader_contract",
        "source": {"root": str(module.SOURCE), "revision": module.EXPECTED_REVISION, "config_sha256": module.EXPECTED_CONFIG_SHA, "index_sha256": module.EXPECTED_INDEX_SHA},
        "proxy": {"root": str(output), "contract_sha256": contract_hash, "manifest_sha256": digest(PROVEN), "layer_count": EXPECTED_LAYERS, "skipped_source_layers": list(SKIPPED), "weight_bytes": runtime_manifest["weight_bytes"]},
        "verification": verification,
        "runtime_manifest": {"manifest_sha256": digest(output / "model-files-manifest.json"), "shard_count": runtime_manifest["shard_count"], "weight_bytes": runtime_manifest["weight_bytes"]},
        "materializer_manifest": manifest,
    }
    (output / "minimal_depth_checkpoint_manifest.json").write_text(json.dumps({"materializer_manifest": manifest, **result}, indent=2, sort_keys=True) + "\n")
    (HERE / "minimal_depth_checkpoint_manifest.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
