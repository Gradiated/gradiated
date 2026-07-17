#!/usr/bin/env python3
"""Zero-provider feasibility preflight for the fixed 39-layer recovery job.

It reads safetensors headers only: no full checkpoint is materialized and no
model runtime is required.  The small numerical fixture is deliberately not a
quality measurement; it proves the training loss/checkpoint/W4 conversion
contracts are wired and deterministic.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import struct
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
TEACHER = Path("/root/.cache/glm47flash-bf16-33faccf4")
STUDENT = Path("/root/.cache/glm47flash-awq-student39-183247870f89")
SKIPPED = (5, 10, 15, 20, 26, 31, 36, 41)
RETAINED = tuple(i for i in range(47) if i not in SKIPPED)
TARGET_SUFFIXES = (
    ".self_attn.q_a_proj.weight",
    ".self_attn.q_b_proj.weight",
    ".self_attn.o_proj.weight",
    ".mlp.gate.weight",
)


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def layer_id(name: str) -> int | None:
    prefix = "model.layers."
    if not name.startswith(prefix):
        return None
    word = name[len(prefix):].split(".", 1)[0]
    return int(word) if word.isdigit() else None


def renamed(name: str, mapping: dict[int, int]) -> str | None:
    old = layer_id(name)
    if old is None:
        return name
    if old not in mapping:
        return None
    return name.replace(f"model.layers.{old}.", f"model.layers.{mapping[old]}.", 1)


def header(path: Path) -> dict[str, dict[str, object]]:
    with path.open("rb") as f:
        length = struct.unpack("<Q", f.read(8))[0]
        return json.loads(f.read(length))


def header_size(path: Path) -> tuple[int, dict[str, dict[str, object]]]:
    with path.open("rb") as f:
        length = struct.unpack("<Q", f.read(8))[0]
        return length + 8, json.loads(f.read(length))


def inventory(root: Path) -> tuple[dict[str, str], dict[str, dict[str, object]]]:
    index = json.loads((root / "model.safetensors.index.json").read_text())["weight_map"]
    tensors: dict[str, dict[str, object]] = {}
    for shard in sorted(set(index.values())):
        tensors.update({k: v for k, v in header(root / shard).items() if k != "__metadata__"})
    if set(index) != set(tensors):
        raise RuntimeError("safetensors index/header key mismatch")
    return index, tensors


def count(values: list[int]) -> int:
    answer = 1
    for value in values:
        answer *= value
    return answer


def softmax(values: list[float]) -> list[float]:
    maximum = max(values)
    exps = [math.exp(v - maximum) for v in values]
    total = sum(exps)
    return [v / total for v in exps]


def kl(teacher: list[float], student: list[float]) -> float:
    p, q = softmax(teacher), softmax(student)
    return sum(x * math.log(x / y) for x, y in zip(p, q))


def mse(left: list[float], right: list[float]) -> float:
    return sum((a - b) ** 2 for a, b in zip(left, right)) / len(left)


def pack_int4_group32(values: list[float]) -> dict[str, object]:
    """Minimal symmetric group-32 W4 reference used only for conversion parity."""
    packed, scales = [], []
    for start in range(0, len(values), 32):
        group = values[start:start + 32]
        scale = max(max(abs(x) for x in group) / 7.0, 1e-12)
        codes = [max(-8, min(7, int(round(x / scale)))) + 8 for x in group]
        packed.extend(codes[i] | ((codes[i + 1] if i + 1 < len(codes) else 8) << 4) for i in range(0, len(codes), 2))
        scales.append(scale)
    return {"group_size": 32, "num_bits": 4, "packed_hex": bytes(packed).hex(), "scales": scales}


def materialize_bf16_student(output: Path, index: dict[str, str], tensors: dict[str, dict[str, object]], mapping: dict[int, int]) -> None:
    """Streaming, idempotent BF16 initializer for the future job only."""
    if output.exists():
        raise FileExistsError(f"refusing to replace existing {output}")
    temporary = Path(tempfile.mkdtemp(prefix="student39-bf16-", dir=output.parent))
    try:
        grouped: dict[str, list[str]] = {}
        for name, shard in index.items():
            if renamed(name, mapping) is not None:
                grouped.setdefault(shard, []).append(name)
        new_index: dict[str, str] = {}
        for ordinal, (shard, names) in enumerate(sorted(grouped.items()), 1):
            source_header_bytes, source_header = header_size(TEACHER / shard)
            out_name = f"model-{ordinal:05d}-of-{len(grouped):05d}.safetensors"
            records, cursor = [], 0
            for name in sorted(names):
                item = tensors[name]
                start, end = item["data_offsets"]
                copied = {k: v for k, v in item.items() if k != "data_offsets"}
                copied["data_offsets"] = [cursor, cursor + end - start]
                records.append((name, renamed(name, mapping), copied, start, end))
                cursor += end - start
            out_header: dict[str, object] = {"__metadata__": source_header.get("__metadata__", {})}
            out_header.update({new: item for _, new, item, _, _ in records})
            encoded = canonical(out_header)
            encoded += b" " * ((8 - ((len(encoded) + 8) % 8)) % 8)
            with (TEACHER / shard).open("rb") as source, (temporary / out_name).open("wb") as destination:
                destination.write(struct.pack("<Q", len(encoded)))
                destination.write(encoded)
                for _, new, _, start, end in records:
                    source.seek(source_header_bytes + start)
                    remaining = end - start
                    while remaining:
                        block = source.read(min(1 << 20, remaining))
                        if not block:
                            raise IOError(f"truncated tensor payload in {shard}")
                        destination.write(block)
                        remaining -= len(block)
                    new_index[new] = out_name
        config = json.loads((TEACHER / "config.json").read_text())
        serving_config = json.loads((STUDENT / "config.json").read_text())
        config["num_hidden_layers"] = 39
        # This field is part of the validated AWQ serving config but is absent
        # from the older BF16 config; bind it from that fixed serving contract.
        config["mlp_layer_types"] = serving_config["mlp_layer_types"]
        config["num_nextn_predict_layers"] = 0
        for key in ("head_dim", "qk_head_dim", "rope_interleave", "rope_parameters"):
            if key in serving_config:
                config[key] = serving_config[key]
        (temporary / "config.json").write_text(json.dumps(config, indent=2, sort_keys=True) + "\n")
        total_size = sum(tensors[name]["data_offsets"][1] - tensors[name]["data_offsets"][0] for name in index if renamed(name, mapping) is not None)
        (temporary / "model.safetensors.index.json").write_text(json.dumps({"metadata": {"total_size": total_size}, "weight_map": dict(sorted(new_index.items()))}, indent=2, sort_keys=True) + "\n")
        for source in TEACHER.iterdir():
            if source.is_file() and not source.name.endswith(".safetensors") and source.name not in {"config.json", "model.safetensors.index.json"}:
                shutil.copy2(source, temporary / source.name)
        os_replace = __import__("os").replace
        os_replace(temporary, output)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def fixture(root: Path) -> dict[str, object]:
    teacher_logits = [0.4, -0.2, 0.9, 0.1]
    student_logits = [0.1, 0.0, 0.5, 0.2]
    bridge_teacher = [[0.2, -0.4, 0.3], [0.1, 0.7, -0.2]]
    bridge_student = [[0.0, -0.3, 0.2], [0.2, 0.5, -0.1]]
    bridge_loss = sum(mse(a, b) for a, b in zip(bridge_teacher, bridge_student)) / len(bridge_teacher)
    loss = kl(teacher_logits, student_logits) + 0.25 * bridge_loss
    adapters = {"model.layers.0.self_attn.o_proj.lora_A": [[0.0, 0.01], [0.02, -0.01]], "model.layers.0.self_attn.o_proj.lora_B": [[0.03, 0.0], [-0.02, 0.01]]}
    state = {"schema": 1, "loss": loss, "adapters": adapters, "optimizer": {"kind": "adamw", "step": 1}, "quantization": pack_int4_group32([x for row in adapters["model.layers.0.self_attn.o_proj.lora_B"] for x in row] * 16)}
    checkpoint = root / "fixture_adapter_checkpoint.json"
    checkpoint.write_bytes(canonical(state))
    reloaded = json.loads(checkpoint.read_text())
    quant_repeat = pack_int4_group32([x for row in adapters["model.layers.0.self_attn.o_proj.lora_B"] for x in row] * 16)
    return {"loss_wiring": {"kl": kl(teacher_logits, student_logits), "bridge_mse": bridge_loss, "total": loss, "formula": "KL(teacher_logits/T=1||student_logits/T=1) + 0.25*mean(MSE(student_pre_skip_hidden, teacher_post_skip_hidden))"}, "checkpoint_reload_identity": canonical(state) == canonical(reloaded), "deterministic_w4_group32": canonical(state["quantization"]) == canonical(quant_repeat), "checkpoint_sha256": sha(checkpoint)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=HERE / "STUDENT39_RECOVERY_FEASIBILITY.json")
    parser.add_argument("--materialize-bf16-student", type=Path, help="future-job-only streaming BF16 student output; never use during zero-cost preflight")
    args = parser.parse_args()
    teacher_index, teacher = inventory(TEACHER)
    student_index, _ = inventory(STUDENT)
    mapping = {old: new for new, old in enumerate(RETAINED)}
    if args.materialize_bf16_student:
        materialize_bf16_student(args.materialize_bf16_student, teacher_index, teacher, mapping)
    pairs = []
    for source in sorted(teacher):
        target = renamed(source, mapping)
        if target is not None:
            item = teacher[source]
            pairs.append({"source": source, "student": target, "shape": item["shape"], "dtype": item["dtype"], "elements": count(item["shape"])})
    expected_student = {pair["student"] for pair in pairs}
    # AWQ stores packed/scale/shape variants, so only source names that remain
    # exact unquantized names are compared; all logical layers must be present.
    logical_layers = sorted({layer_id(name) for name in student_index if layer_id(name) is not None})
    if logical_layers != list(range(39)) or len(pairs) != 7843:
        raise RuntimeError("student layer closure or BF16 mapping drift")
    if any(layer_id(pair["student"]) == 47 for pair in pairs):
        raise RuntimeError("MTP leaked into mapping")
    targets = [pair for pair in pairs if pair["source"].endswith(TARGET_SUFFIXES)]
    if len(targets) != 155:
        raise RuntimeError(f"unexpected LoRA target count: {len(targets)}")
    rank = 16
    lora_parameters = sum(rank * (pair["shape"][0] + pair["shape"][1]) for pair in targets)
    bf16_bytes = sum(pair["elements"] * 2 for pair in pairs)
    # The estimates are admission envelopes, not observed allocator peaks.
    memory = {
        "student_bf16_weights_gib": bf16_bytes / 2**30,
        "teacher_bf16_weights_gib": sum(count(v["shape"]) * 2 for v in teacher.values()) / 2**30,
        "lora_rank": rank,
        "lora_trainable_parameters": lora_parameters,
        "lora_weights_grad_adamw_gib": lora_parameters * 16 / 2**30,
        "student_training_envelope_gib": 68.0,
        "teacher_capture_envelope_gib": 72.0,
        "single_gpu_requirement": "80GB H100/H200 class; L40S 48GB is excluded for BF16 recovery",
        "activation_contract": "microbatch=1, sequence=1024, gradient_checkpointing=true, FlashAttention2, no teacher co-residency",
    }
    with tempfile.TemporaryDirectory(prefix="student39-recovery-preflight-") as temp:
        fixture_result = fixture(Path(temp))
    bridges = [{"removed_teacher_layer": layer, "student_pre_skip_layer": mapping[layer - 1], "teacher_hidden_target_after_layer": layer} for layer in SKIPPED]
    report = {
        "schema_version": 1,
        "decision": "NOMINATE_ONE_BOUNDED_RECOVERY_JOB",
        "evidence_class": {"mapping": "source_bound", "preflight": "measured_synthetic_fixture", "memory_and_hours": "derived", "quality": "unmeasured"},
        "teacher": {"root": str(TEACHER), "config_sha256": sha(TEACHER / "config.json"), "index_sha256": sha(TEACHER / "model.safetensors.index.json"), "tensor_count": len(teacher)},
        "student": {"root": str(STUDENT), "manifest_contract_sha256": "183247870f8965b8b92260b167eb5c22f486210bf86ffb8a8a4bb0226799caf1", "logical_layer_count": 39, "no_mtp": True, "final_norm_and_lm_head_retained": all(x in expected_student for x in ("model.norm.weight", "lm_head.weight"))},
        "mapping": {"removed_source_layers": list(SKIPPED), "source_to_student_layers": {str(k): v for k, v in mapping.items()}, "mapped_tensor_count": len(pairs), "mapped_bf16_parameters": sum(p["elements"] for p in pairs), "mapping_sha256": hashlib.sha256(canonical(pairs)).hexdigest(), "pairs": pairs},
        "trainable_contract": {"method": "BF16 LoRA rank-16 on retained q_a_proj, q_b_proj, o_proj, and sparse MoE router gate; all base tensors frozen", "target_count": len(targets), "target_mapping_sha256": hashlib.sha256(canonical(targets)).hexdigest(), "trainable_parameters": lora_parameters, "targets": [{"source": x["source"], "student": x["student"], "shape": x["shape"]} for x in targets]},
        "loss_contract": {"logits": "teacher KL over next-token logits", "bridges": bridges, "bridge_weight": 0.25, "teacher_capture": "store per-token top-64 logits plus eight BF16 2048-wide bridge hidden states; teacher never co-resides with student"},
        "memory_envelope": memory,
        "preflight": fixture_result,
        "quantization_contract": {"base": "merge LoRA into the mapped BF16 student, then run the pinned compressed-tensors AWQ group-32 W4 conversion", "required_invariants": ["39 layers", "no layer 47/MTP", "same tokenizer", "final norm and lm_head", "pack-quantized symmetric int4 group_size=32"], "fixture_only": True},
        "quality_separation": "No frozen development or holdout record was read for training. The development suite is only an after-training gate; no static/synthetic preflight is quality evidence.",
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(args.output), "decision": report["decision"], "mapping_sha256": report["mapping"]["mapping_sha256"], "lora_trainable_parameters": lora_parameters, "preflight": fixture_result}, indent=2))


if __name__ == "__main__":
    main()
