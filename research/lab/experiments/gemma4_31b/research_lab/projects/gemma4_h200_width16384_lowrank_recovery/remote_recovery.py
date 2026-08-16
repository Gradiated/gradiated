#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
import time
from pathlib import Path

import torch
from safetensors.torch import save_file
from transformers import Gemma4ForConditionalGeneration


SEED = 20260723
WIDTH = 16384
FULL_WIDTH = 21504
HIDDEN = 5376
RANK = 256
CAL_REQUESTS = tuple(range(6))
HOLDOUT_REQUESTS = (30, 31)
TOKENS_PER_REQUEST = 128
CAMPAIGN_SEED = "gemma4-background-exact-mix-c32-20260718"


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def atomic(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".part")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def campaign_tokens(label: str, count: int) -> list[int]:
    result: list[int] = []
    index = 0
    while len(result) < count:
        digest = hashlib.sha256(
            f"{CAMPAIGN_SEED}|{label}|{index}".encode()
        ).digest()
        for offset in range(0, len(digest), 4):
            result.append(
                1000
                + int.from_bytes(digest[offset : offset + 4], "big") % 249000
            )
            if len(result) == count:
                return result
        index += 1
    raise AssertionError("unreachable")


def exact_request(index: int) -> list[int]:
    common = campaign_tokens("common-prefix", 535)
    suffix = campaign_tokens(f"suffix-{index}", 4214 - 535)
    suffix[0] = 200000 + index
    return common + suffix


def sampled_inputs() -> tuple[torch.Tensor, dict[str, object]]:
    request_ids = CAL_REQUESTS + HOLDOUT_REQUESTS
    rows = []
    windows = []
    for ordinal, request_id in enumerate(request_ids):
        full = exact_request(request_id)
        # Fixed, diverse content-bound windows. The holdout request identities are
        # disjoint from calibration; no captured activation crosses the split.
        start = 535 + ((request_id * 431 + ordinal * 97) % (4214 - 535 - 128))
        window = full[start : start + TOKENS_PER_REQUEST]
        windows.append(window)
        rows.append(
            {
                "request_id": request_id,
                "split": "calibration"
                if request_id in CAL_REQUESTS
                else "holdout",
                "start": start,
                "tokens": len(window),
                "token_sha256": hashlib.sha256(
                    json.dumps(window, separators=(",", ":")).encode()
                ).hexdigest(),
            }
        )
    tensor = torch.tensor(windows, dtype=torch.long)
    identity = {
        "campaign_seed": CAMPAIGN_SEED,
        "sampling_seed": SEED,
        "rows": rows,
        "tensor_sha256": hashlib.sha256(tensor.numpy().tobytes()).hexdigest(),
    }
    return tensor, identity


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output
    factors = output / "factors"
    factors.mkdir(parents=True, exist_ok=False)
    atomic(
        output / "INVOCATION_STATE.json",
        {
            "schema_version": 1,
            "intent_recorded": True,
            "health_probe_passed": torch.cuda.is_available(),
            "scientific_workload_started": False,
            "timestamp_utc": utc_now(),
        },
    )
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA unavailable before scientific invocation")
    props = torch.cuda.get_device_properties(0)
    if "H200" not in props.name or props.total_memory < 140_000_000_000:
        raise RuntimeError(f"frozen H200 geometry mismatch:{props}")

    torch.manual_seed(SEED)
    torch.cuda.manual_seed_all(SEED)
    random.seed(SEED)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    selection_doc = json.loads(args.selection.read_text())
    selections = {
        int(row["layer"]): torch.tensor(
            row["indices"], dtype=torch.long, device="cuda"
        )
        for row in selection_doc["layers"]
    }
    if sorted(selections) != list(range(60)) or any(
        value.numel() != WIDTH for value in selections.values()
    ):
        raise RuntimeError("immutable selection geometry mismatch")
    input_ids, capture_identity = sampled_inputs()
    atomic(output / "CAPTURE_IDENTITY.json", capture_identity)

    state = json.loads((output / "INVOCATION_STATE.json").read_text())
    state.update(
        {
            "scientific_workload_started": True,
            "scientific_started_utc": utc_now(),
            "stage": "full_checkpoint_teacher_load",
        }
    )
    atomic(output / "INVOCATION_STATE.json", state)
    started = time.monotonic()
    model = Gemma4ForConditionalGeneration.from_pretrained(
        args.checkpoint,
        dtype=torch.bfloat16,
        local_files_only=True,
        low_cpu_mem_usage=False,
    )
    model.eval()
    model.to("cuda")
    language_model = model.model.language_model
    if len(language_model.layers) != 60:
        raise RuntimeError("teacher layer count mismatch")

    rows: list[dict[str, object]] = []
    manifest_rows: list[dict[str, object]] = []
    aggregate = {
        "baseline_error_sq": 0.0,
        "recovered_error_sq": 0.0,
        "teacher_sq": 0.0,
    }
    cal_count = len(CAL_REQUESTS) * TOKENS_PER_REQUEST

    def make_hook(layer_index: int):
        def hook(module, inputs, full_output):
            x = inputs[0].detach().reshape(-1, HIDDEN)
            full_output_flat = full_output.detach().reshape(-1, HIDDEN)
            if x.shape[0] != 1024:
                raise RuntimeError(f"capture row mismatch:{x.shape}")
            with torch.no_grad():
                full_activation = module.act_fn(module.gate_proj(x)) * module.up_proj(x)
                indices = selections[layer_index]
                retained = full_activation.index_select(1, indices)
                selected_down = module.down_proj.weight.index_select(1, indices)
                proxy = torch.nn.functional.linear(retained, selected_down)
                residual = full_output_flat - proxy
                x_cal = retained[:cal_count].float()
                y_cal = residual[:cal_count].float()
                x_hold = retained[cal_count:].float()
                y_hold = residual[cal_count:].float()
                teacher_hold = full_output_flat[cal_count:].float()

                gram = x_cal @ x_cal.T
                ridge = max(
                    float(torch.trace(gram).item() / gram.shape[0]) * 1.0e-4,
                    1.0e-6,
                )
                regularized = gram + torch.eye(
                    gram.shape[0], device=gram.device, dtype=gram.dtype
                ) * ridge
                chol = torch.linalg.cholesky(regularized)
                coefficients = torch.cholesky_solve(y_cal, chol)
                fitted = gram @ coefficients
                output_gram = fitted @ fitted.T
                eigenvalues, eigenvectors = torch.linalg.eigh(output_gram)
                order = torch.argsort(eigenvalues, descending=True)[:RANK]
                values = eigenvalues.index_select(0, order).clamp_min(0)
                singular = values.sqrt()
                u = eigenvectors.index_select(1, order)
                if not torch.isfinite(singular).all() or float(singular[-1]) <= 0:
                    raise RuntimeError(f"nonfinite_or_deficient_rank:{layer_index}")
                left = (fitted.T @ u) / singular.unsqueeze(0)
                lowrank_targets = u * singular.unsqueeze(0)
                reduced_coefficients = torch.cholesky_solve(lowrank_targets, chol)
                right = reduced_coefficients.T @ x_cal
                predicted = (x_hold @ right.T) @ left.T
                baseline_sq = float(torch.sum(y_hold.square()).item())
                recovered_sq = float(torch.sum((y_hold - predicted).square()).item())
                teacher_sq = float(torch.sum(teacher_hold.square()).item())
                factor_path = factors / f"layer-{layer_index:02d}.safetensors"
                save_file(
                    {
                        "left": left.to("cpu", dtype=torch.bfloat16).contiguous(),
                        "right": right.to("cpu", dtype=torch.bfloat16).contiguous(),
                    },
                    factor_path,
                    metadata={
                        "layer": str(layer_index),
                        "rank": str(RANK),
                        "selection_sha256": sha256(args.selection),
                    },
                )
                factor_hash = sha256(factor_path)
                row = {
                    "layer": layer_index,
                    "rank": RANK,
                    "ridge": ridge,
                    "factor_sha256": factor_hash,
                    "factor_bytes": factor_path.stat().st_size,
                    "singular_max": float(singular[0].item()),
                    "singular_min_retained": float(singular[-1].item()),
                    "baseline_relative_l2": math.sqrt(baseline_sq / teacher_sq),
                    "recovered_relative_l2": math.sqrt(recovered_sq / teacher_sq),
                    "residual_energy_recovered_fraction": 1.0
                    - recovered_sq / baseline_sq,
                    "finite": all(
                        math.isfinite(value)
                        for value in (baseline_sq, recovered_sq, teacher_sq)
                    ),
                }
                rows.append(row)
                manifest_rows.append(
                    {
                        "layer": layer_index,
                        "path": f"factors/{factor_path.name}",
                        "bytes": factor_path.stat().st_size,
                        "sha256": factor_hash,
                        "left_shape": [HIDDEN, RANK],
                        "right_shape": [RANK, WIDTH],
                        "dtype": "torch.bfloat16",
                    }
                )
                aggregate["baseline_error_sq"] += baseline_sq
                aggregate["recovered_error_sq"] += recovered_sq
                aggregate["teacher_sq"] += teacher_sq
                atomic(output / "LAYER_RESULTS.json", {"rows": rows})
                atomic(
                    output / "FACTOR_MANIFEST.json",
                    {"schema_version": 1, "files": manifest_rows},
                )
                del full_activation, retained, proxy, residual
                torch.cuda.empty_cache()
        return hook

    handles = [
        layer.mlp.register_forward_hook(make_hook(index))
        for index, layer in enumerate(language_model.layers)
    ]
    try:
        with torch.inference_mode():
            language_model(
                input_ids=input_ids.to("cuda"),
                use_cache=False,
                return_dict=True,
            )
    finally:
        for handle in handles:
            handle.remove()

    if len(rows) != 60 or len(manifest_rows) != 60:
        raise RuntimeError(f"incomplete layer capture:{len(rows)}")
    global_baseline = math.sqrt(
        aggregate["baseline_error_sq"] / aggregate["teacher_sq"]
    )
    global_recovered = math.sqrt(
        aggregate["recovered_error_sq"] / aggregate["teacher_sq"]
    )
    recovered_fraction = (
        1.0
        - aggregate["recovered_error_sq"] / aggregate["baseline_error_sq"]
    )
    improved_layers = sum(
        row["recovered_relative_l2"] < row["baseline_relative_l2"] for row in rows
    )
    gate = {
        "all_layers_finite_and_exact_rank": all(row["finite"] for row in rows),
        "global_baseline_relative_l2": global_baseline,
        "global_recovered_relative_l2": global_recovered,
        "global_residual_energy_recovered_fraction": recovered_fraction,
        "improved_layers": improved_layers,
        "pass": (
            all(row["finite"] for row in rows)
            and global_recovered <= 0.2
            and recovered_fraction >= 0.5
            and improved_layers >= 57
        ),
    }
    terminal = {
        "schema_version": 1,
        "status": "terminal",
        "classification": "heldout_reconstruction_pass"
        if gate["pass"]
        else "reconstruction_or_coherence_reject",
        "checkpoint": str(args.checkpoint),
        "selection_sha256": sha256(args.selection),
        "capture_identity": capture_identity,
        "elapsed_seconds": time.monotonic() - started,
        "factor_manifest_sha256": sha256(output / "FACTOR_MANIFEST.json"),
        "gate": gate,
        "timestamp_utc": utc_now(),
    }
    atomic(output / "PRODUCER_TERMINAL.json", terminal)
    state = json.loads((output / "INVOCATION_STATE.json").read_text())
    state.update(
        {
            "scientific_completed": True,
            "terminal_classification": terminal["classification"],
            "completed_utc": utc_now(),
        }
    )
    atomic(output / "INVOCATION_STATE.json", state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
