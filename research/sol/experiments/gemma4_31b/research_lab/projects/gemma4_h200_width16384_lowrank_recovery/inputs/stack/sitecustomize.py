from __future__ import annotations

import hashlib
import importlib
import os
import pathlib


SOURCE = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py")
MM_SOURCE = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/models/gemma4_mm.py")
PRISTINE_SHA256 = "bc8bc948a89e82b2118c32d380497ce76a568b8839c7f02150195af93a0e8989"
WIDTH_OLD = """        layer_intermediate_size = config.intermediate_size * (
            2 if use_double_wide_mlp else 1
        )
"""
WIDTH_NEW = """        layer_intermediate_size = config.intermediate_size * (
            2 if use_double_wide_mlp else 1
        )
        if os.environ.get("MLP_WIDTH16384_ARM") == "candidate":
            if config.intermediate_size != 21504 or use_double_wide_mlp:
                raise RuntimeError("frozen MLP geometry mismatch")
            layer_intermediate_size = 16384
"""
LOADER_OLD = """        loaded_params: Set[str] = set()
        for name, loaded_weight in weights:
"""
LOADER_NEW = """        loaded_params: Set[str] = set()
        width_selection = None
        width_audit = None
        recovery_factor_root = None
        if os.environ.get("MLP_WIDTH16384_ARM") == "candidate":
            import json
            selection_path = os.environ["MLP_WIDTH16384_SELECTION"]
            recovery_factor_root = os.environ["MLP_RECOVERY_FACTORS"]
            width_selection = {
                int(row["layer"]): torch.tensor(row["indices"], dtype=torch.long)
                for row in json.load(open(selection_path))["layers"]
            }
            if len(width_selection) != 60:
                raise RuntimeError("frozen MLP selection layer count mismatch")
            width_audit = open(os.environ["MLP_WIDTH16384_AUDIT"], "a")
        for name, loaded_weight in weights:
            if width_selection is not None:
                width_match = re.search(r"layers\\.(\\d+)\\.mlp\\.(gate_proj|up_proj|down_proj)\\.weight$", name)
                if width_match:
                    width_layer = int(width_match.group(1))
                    width_projection = width_match.group(2)
                    width_indices = width_selection[width_layer]
                    width_source_shape = list(loaded_weight.shape)
                    width_dim = 1 if width_projection == "down_proj" else 0
                    loaded_weight = loaded_weight.index_select(width_dim, width_indices)
                    recovery = {}
                    if width_projection == "down_proj":
                        from safetensors.torch import load_file
                        factors = load_file(
                            f"{recovery_factor_root}/layer-{width_layer:02d}.safetensors",
                            device="cuda",
                        )
                        left = factors["left"]
                        right = factors["right"]
                        if list(left.shape) != [5376, 256] or list(right.shape) != [256, 16384]:
                            raise RuntimeError(f"recovery factor geometry mismatch:{width_layer}")
                        correction = torch.matmul(left.float(), right.float())
                        loaded_weight = loaded_weight.to("cuda").add_(
                            correction.to(dtype=loaded_weight.dtype)
                        )
                        recovery = {
                            "recovery_merged": True,
                            "recovery_rank": 256,
                            "left_shape": list(left.shape),
                            "right_shape": list(right.shape),
                            "runtime_adapter": False,
                        }
                    width_audit.write(json.dumps({
                        "layer": width_layer,
                        "projection": width_projection,
                        "source_shape": width_source_shape,
                        "candidate_shape": list(loaded_weight.shape),
                        "indices_count": int(width_indices.numel()),
                        **recovery,
                    }, sort_keys=True) + "\\n")
                    width_audit.flush()
"""
MM_LOADER_OLD = """        loaded_params: Set[str] = set()

        for name, loaded_weight in weights:
"""
MM_LOADER_NEW = """        loaded_params: Set[str] = set()
        width_selection = None
        width_audit = None
        recovery_factor_root = None
        import os
        if os.environ.get("MLP_WIDTH16384_ARM") == "candidate":
            import json
            selection_path = os.environ["MLP_WIDTH16384_SELECTION"]
            recovery_factor_root = os.environ["MLP_RECOVERY_FACTORS"]
            width_selection = {
                int(row["layer"]): torch.tensor(row["indices"], dtype=torch.long)
                for row in json.load(open(selection_path))["layers"]
            }
            if len(width_selection) != 60:
                raise RuntimeError("frozen MLP selection layer count mismatch")
            width_audit = open(os.environ["MLP_WIDTH16384_AUDIT"], "a")

        for name, loaded_weight in weights:
"""
MM_NAME_OLD = """            name = re.sub(r"^model\\.", "", name)
"""
MM_NAME_NEW = """            name = re.sub(r"^model\\.", "", name)
            if width_selection is not None:
                width_match = re.search(r"^language_model\\.layers\\.(\\d+)\\.mlp\\.(gate_proj|up_proj|down_proj)\\.weight$", name)
                if width_match:
                    width_layer = int(width_match.group(1))
                    width_projection = width_match.group(2)
                    width_indices = width_selection[width_layer]
                    width_source_shape = list(loaded_weight.shape)
                    width_dim = 1 if width_projection == "down_proj" else 0
                    loaded_weight = loaded_weight.index_select(width_dim, width_indices)
                    recovery = {}
                    if width_projection == "down_proj":
                        from safetensors.torch import load_file
                        factors = load_file(
                            f"{recovery_factor_root}/layer-{width_layer:02d}.safetensors",
                            device="cuda",
                        )
                        left = factors["left"]
                        right = factors["right"]
                        if list(left.shape) != [5376, 256] or list(right.shape) != [256, 16384]:
                            raise RuntimeError(f"recovery factor geometry mismatch:{width_layer}")
                        correction = torch.matmul(left.float(), right.float())
                        loaded_weight = loaded_weight.to("cuda").add_(
                            correction.to(dtype=loaded_weight.dtype)
                        )
                        recovery = {
                            "recovery_merged": True,
                            "recovery_rank": 256,
                            "left_shape": list(left.shape),
                            "right_shape": list(right.shape),
                            "runtime_adapter": False,
                        }
                    width_audit.write(json.dumps({
                        "layer": width_layer,
                        "projection": width_projection,
                        "source_shape": width_source_shape,
                        "candidate_shape": list(loaded_weight.shape),
                        "indices_count": int(width_indices.numel()),
                        **recovery,
                    }, sort_keys=True) + "\\n")
                    width_audit.flush()
"""


def install_qkv_and_frontier() -> None:
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD

    raw = SOURCE.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual == EXPECTED_SHA256:
        text = raw.decode()
        if text.count(OLD) != 1:
            raise RuntimeError("bound QKV patch target is not unique")
        SOURCE.write_text(text.replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError(f"bound QKV source mismatch:{actual}")
    audit = os.environ.get("RESIDUAL_CANDIDATE_AUDIT")
    if audit:
        os.environ["SYNC_CANDIDATE_AUDIT"] = audit
    attention = importlib.import_module("attention_deferred_local_kv")
    if "deferred_local_fp8_kv" not in attention.TARGET.read_text():
        attention.install()
    pinned = importlib.import_module("pinned_async_penalty_tokens")
    pinned_actual = hashlib.sha256(pinned.TARGET.read_bytes()).hexdigest()
    if pinned_actual == pinned.EXPECTED_SHA256:
        pinned.install()
    elif pinned_actual != "b6480f792867d7aba3dc39ef66048408c6c92ddad3ed81b23934493a351be459":
        raise RuntimeError(f"pinned schedule_batch source mismatch:{pinned_actual}")
    importlib.import_module("host_min_new_tokens_gate").install()
    importlib.import_module("producer_fused_swa_translation").install()


def install_width() -> None:
    text = SOURCE.read_text()
    if WIDTH_NEW not in text or LOADER_NEW not in text:
        if text.count(WIDTH_OLD) != 1 or text.count(LOADER_OLD) != 1:
            raise RuntimeError("frozen MLP text loader target is not unique")
        text = text.replace(WIDTH_OLD, WIDTH_NEW).replace(LOADER_OLD, LOADER_NEW)
        if "import os" not in text.splitlines()[:30]:
            text = text.replace("import logging\n", "import logging\nimport os\n")
        SOURCE.write_text(text)
    mm_text = MM_SOURCE.read_text()
    if MM_LOADER_NEW not in mm_text or MM_NAME_NEW not in mm_text:
        if mm_text.count(MM_LOADER_OLD) != 1 or mm_text.count(MM_NAME_OLD) != 1:
            raise RuntimeError("frozen MLP multimodal loader target is not unique")
        MM_SOURCE.write_text(mm_text.replace(MM_LOADER_OLD, MM_LOADER_NEW).replace(MM_NAME_OLD, MM_NAME_NEW))


if os.environ.get("STACKED_FRONTIER_ARM") == "candidate":
    install_qkv_and_frontier()
    if os.environ.get("MLP_WIDTH16384_ARM") == "candidate":
        install_width()
    if os.environ.get("RING_CACHE_ARM") == "candidate":
        importlib.import_module("endpoint_ring_patch").install()
