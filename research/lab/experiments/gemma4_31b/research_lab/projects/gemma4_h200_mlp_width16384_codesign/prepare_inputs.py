#!/usr/bin/env python3
from __future__ import annotations

import argparse
import array
import hashlib
import json
import os
import pathlib
import shutil
import time

import torch
from safetensors import safe_open
from safetensors.torch import save_file


PROJECT = pathlib.Path(__file__).resolve().parent
LAB = PROJECT.parent.parent
BASE = LAB / "projects/gemma4_h200_v0513_fp8_qkv_residual_profile"
FUSION = LAB / "projects/gemma4_h200_fp8_layer_dataflow_fusion"
QKV = LAB / "projects/gemma4_h200_qkv_epilogue_fusion"
RING = LAB / "projects/gemma4_h200_swa_contiguous_ring_cache"
TRACE = LAB / "projects/gemma4_h200_residual_h2d_sync_residency/artifacts/residual-h2d-current-frontier-20260723t0403z"
CONTROL = LAB / "projects/sglang_v0512_h200_gemma4_mtp_endpoint/artifacts/mtp-candidate-repair-20260723t0658z/retrieved/control/TERMINAL.json"
CHECKPOINT = BASE / "inputs/checkpoint"
SOURCE_SNAPSHOT = FUSION / "inputs/component/layer0-rms-qkv-gate-up.safetensors"
SOURCE_SNAPSHOT_SHA256 = "8230f5dcca70dd7e3b6f63d9614fc9b7ece632b539da00813b1a5af1d41923af"


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(16 * 1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: pathlib.Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def snapshot(source: pathlib.Path, destination: pathlib.Path) -> dict[str, object]:
    raw = source.read_bytes()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(raw)
    os.chmod(temporary, 0o444)
    os.replace(temporary, destination)
    return {
        "path": str(destination.relative_to(PROJECT)),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "source_provenance": str(source),
    }


def reflink(source: pathlib.Path, destination: pathlib.Path, expected: str) -> dict[str, object]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and sha256(destination) == expected:
        return {
            "path": str(destination.relative_to(PROJECT)),
            "bytes": destination.stat().st_size,
            "sha256": expected,
            "materialization": "existing_verified_project_local",
            "source_provenance": str(source),
        }
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    result = os.system(
        "cp --reflink=always -- "
        + " ".join(
            "'" + str(path).replace("'", "'\\''") + "'" for path in (source, temporary)
        )
    )
    if result:
        shutil.copyfile(source, temporary)
        materialization = "full_byte_copy_verified_project_local"
    else:
        materialization = "reflink_copy_on_write_verified_project_local"
    actual = sha256(temporary)
    if actual != expected:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"snapshot hash mismatch:{actual}:{expected}")
    os.chmod(temporary, 0o444)
    os.replace(temporary, destination)
    return {
        "path": str(destination.relative_to(PROJECT)),
        "bytes": destination.stat().st_size,
        "sha256": actual,
        "materialization": materialization,
        "source_provenance": str(source),
    }


def tensor(checkpoint_index: dict[str, str], key: str) -> torch.Tensor:
    shard = CHECKPOINT / checkpoint_index[key]
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        return handle.get_tensor(key)


def prepare_selection(output: pathlib.Path) -> dict[str, object]:
    spec = json.loads((PROJECT / "SELECTION_SPEC.json").read_text())
    width = int(spec["candidate_intermediate_size"])
    checkpoint_index = json.loads((CHECKPOINT / "model.safetensors.index.json").read_text())["weight_map"]
    layers = []
    started = time.time()
    for layer in range(int(spec["layer_count"])):
        prefix = f"model.language_model.layers.{layer}.mlp"
        gate = tensor(checkpoint_index, f"{prefix}.gate_proj.weight")
        up = tensor(checkpoint_index, f"{prefix}.up_proj.weight")
        down = tensor(checkpoint_index, f"{prefix}.down_proj.weight")
        if tuple(gate.shape) != (21504, 5376) or tuple(up.shape) != (21504, 5376) or tuple(down.shape) != (5376, 21504):
            raise RuntimeError(f"layer {layer} geometry mismatch:{gate.shape}:{up.shape}:{down.shape}")
        score = (
            gate.double().square().sum(dim=1)
            + up.double().square().sum(dim=1)
            + down.double().square().sum(dim=0)
        )
        ranked = torch.argsort(score, descending=True, stable=True)
        selected = torch.sort(ranked[:width]).values
        row = {
            "layer": layer,
            "indices": selected.tolist(),
            "indices_sha256": hashlib.sha256(array.array("q", selected.tolist()).tobytes()).hexdigest(),
            "selected_score_min": float(score[selected].min()),
            "selected_score_max": float(score[selected].max()),
            "first_excluded_score_max": float(score[ranked[width:]].max()),
            "source_shapes": [list(gate.shape), list(up.shape), list(down.shape)],
        }
        layers.append(row)
        atomic_json(
            output.with_name("SELECTION_PROGRESS.json"),
            {"completed_layers": layer + 1, "elapsed_seconds": time.time() - started},
        )
        del gate, up, down, score
    value = {
        "schema_version": 1,
        "pass": True,
        "spec": spec,
        "checkpoint_index_sha256": sha256(CHECKPOINT / "model.safetensors.index.json"),
        "layers": layers,
        "elapsed_seconds": time.time() - started,
    }
    atomic_json(output, value)
    return value


def prepare_down_snapshot(destination: pathlib.Path) -> dict[str, object]:
    key = "model.language_model.layers.0.mlp.down_proj.weight"
    index = json.loads((CHECKPOINT / "model.safetensors.index.json").read_text())["weight_map"]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.is_file():
        value = tensor(index, key)
        if tuple(value.shape) != (5376, 21504) or value.dtype != torch.bfloat16:
            raise RuntimeError(f"layer0 down geometry mismatch:{value.shape}:{value.dtype}")
        temporary = destination.with_suffix(destination.suffix + ".part")
        save_file({key: value.contiguous()}, str(temporary))
        os.chmod(temporary, 0o444)
        os.replace(temporary, destination)
    return {
        "path": str(destination.relative_to(PROJECT)),
        "bytes": destination.stat().st_size,
        "sha256": sha256(destination),
        "materialization": "derived_from_bound_checkpoint",
        "source_provenance": str(CHECKPOINT / index[key]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-selection", action="store_true")
    args = parser.parse_args()
    selection_path = PROJECT / "inputs/selection/JOINT_NORM_SELECTION.json"
    if args.skip_selection:
        selection = json.loads(selection_path.read_text())
    else:
        selection = prepare_selection(selection_path)
    if selection.get("pass") is not True or len(selection["layers"]) != 60:
        raise RuntimeError("selection invalid")

    component = reflink(
        SOURCE_SNAPSHOT,
        PROJECT / "inputs/component/layer0-rms-qkv-gate-up.safetensors",
        SOURCE_SNAPSHOT_SHA256,
    )
    down_component = prepare_down_snapshot(PROJECT / "inputs/component/layer0-down.safetensors")
    sources = {
        "proven_v0513_endpoint_entrypoint.py": QKV / "proven_v0513_endpoint_entrypoint.py",
        "fp8_qkv_paired_runner.py": QKV / "fp8_qkv_paired_runner.py",
        "install_endpoint_patch.py": RING / "inputs/endpoint_stack/install_endpoint_patch.py",
        "qkv_epilogue_discriminator.py": RING / "inputs/endpoint_stack/qkv_epilogue_discriminator.py",
        "attention_deferred_local_kv.py": RING / "inputs/endpoint_stack/attention_deferred_local_kv.py",
        "host_min_new_tokens_gate.py": RING / "inputs/endpoint_stack/host_min_new_tokens_gate.py",
        "pinned_async_penalty_tokens.py": RING / "inputs/endpoint_stack/pinned_async_penalty_tokens.py",
        "producer_fused_swa_translation.py": RING / "inputs/endpoint_stack/producer_fused_swa_translation.py",
        "residual_intervention.py": RING / "inputs/endpoint_stack/residual_intervention.py",
        "gemma4_causal.v0.5.13.py": FUSION / "inputs/source/gemma4_causal.py",
        "gemma3_causal.v0.5.13.py": FUSION / "inputs/source/gemma3_causal.py",
        "CURRENT_FP8_LINEAR_SHAPE_MAP.json": PROJECT / "inputs/bound/CURRENT_FP8_LINEAR_SHAPE_MAP.json",
        "CURRENT_TRACE_ATTRIBUTION.json": TRACE / "CURRENT_TRACE_ATTRIBUTION.json",
        "persisted_control_terminal.json": CONTROL,
    }
    snapshots = [
        snapshot(source, PROJECT / "inputs/bound" / name)
        for name, source in sources.items()
    ]
    programs = []
    for name in (
        "SELECTION_SPEC.json",
        "mlp_component.py",
        "sitecustomize.py",
        "remote_width16384.sh",
        "run_bench_owner.py",
    ):
        path = PROJECT / name
        programs.append({"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "schema_version": 1,
        "pass": True,
        "selection": {
            "path": str(selection_path.relative_to(PROJECT)),
            "bytes": selection_path.stat().st_size,
            "sha256": sha256(selection_path),
        },
        "component": component,
        "down_component": down_component,
        "bound_inputs": snapshots,
        "programs": programs,
        "checkpoint": {
            "remote_path": "/home/glmrunner/gemma4-fp8-layer-fusion/checkpoint",
            "bytes": 62578655208,
            "model_index_sha256": "d4aff3b976d69c123a29d1c085d7ba4de1ac3f4ca1726a7f81e1b11462a64ea2",
        },
        "runtime": {
            "commit": "28b095c01005d4a3a2a5b637b7d028b07fba31b2",
            "image": "docker.io/lmsysorg/sglang@sha256:6113665a292b50fe19c147ffa18fb4b119e66f50a7f6370386f2adaf546fbdc6",
        },
    }
    atomic_json(PROJECT / "GPU_INPUT_MANIFEST.json", manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
