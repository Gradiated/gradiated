import argparse
import hashlib
import json
from pathlib import Path


OLD = """                            fused_weight = torch.cat(
                                [q_a_proj_weight, kv_a_proj_weight], dim=0
                            )
"""

GLM_OLD_MAPPING = """class Glm4MoeLiteForCausalLM(nn.Module, DeepseekV2WeightLoaderMixin):
    # for quark model load
    packed_modules_mapping = {}
"""

GLM_NEW_MAPPING = """class Glm4MoeLiteForCausalLM(nn.Module, DeepseekV2WeightLoaderMixin):
    # for quark model load
    packed_modules_mapping = {
        \"fused_qkv_a_proj_with_mqa\": [\"q_a_proj\", \"kv_a_proj_with_mqa\"]
    }
"""

GLM_OLD_QUANT_INIT = """        self.quant_config = quant_config
        self.pp_group = get_pp_group()
"""

GLM_NEW_QUANT_INIT = """        self.quant_config = quant_config
        if quant_config is not None:
            quant_config.update_packed_modules_mapping(self.packed_modules_mapping)
        self.pp_group = get_pp_group()
"""

DEEPSEEK_OLD_PACKED = """        self.is_packed_weight = (
            self.has_fused_proj
            and hasattr(self.fused_qkv_a_proj_with_mqa.quant_method, \"quant_config\")
            and self.fused_qkv_a_proj_with_mqa.quant_method.quant_config.get_name()
            in {\"awq\", \"awq_marlin\", \"moe_wna16\"}
        )
"""

DEEPSEEK_NEW_PACKED = """        self.is_packed_weight = self.has_fused_proj and (
            hasattr(self.fused_qkv_a_proj_with_mqa, \"weight_packed\")
            or (
                hasattr(self.fused_qkv_a_proj_with_mqa.quant_method, \"quant_config\")
                and self.fused_qkv_a_proj_with_mqa.quant_method.quant_config.get_name()
                in {\"awq\", \"awq_marlin\", \"moe_wna16\"}
            )
        )
"""

WEIGHT_LOADER_OLD = '''            if hasattr(self_attn.kv_b_proj, "qweight"):
                # awq compatible, dequantize the weight if supported
                awq_dequantize_f = awq_dequantize_func()
                if awq_dequantize_f is not None:
                    w = awq_dequantize_f(
                        self_attn.kv_b_proj.qweight,
                        self_attn.kv_b_proj.scales,
                        self_attn.kv_b_proj.qzeros,
                    ).T
                else:
                    raise ValueError(
                        "AWQ dequantize function is not supported for the current device"
                    )
            else:
                w = self_attn.kv_b_proj.weight
'''

WEIGHT_LOADER_NEW = '''            if hasattr(self_attn.kv_b_proj, "qweight"):
                # awq compatible, dequantize the weight if supported
                awq_dequantize_f = awq_dequantize_func()
                if awq_dequantize_f is not None:
                    w = awq_dequantize_f(
                        self_attn.kv_b_proj.qweight,
                        self_attn.kv_b_proj.scales,
                        self_attn.kv_b_proj.qzeros,
                    ).T
                else:
                    raise ValueError(
                        "AWQ dequantize function is not supported for the current device"
                    )
            elif hasattr(self_attn.kv_b_proj, "weight_packed"):
                # compressed-tensors W4A16 retains its checkpoint representation
                # until process_weights_after_loading. MLA needs the dense matrix
                # here to derive w_kc/w_vc, so use the library's canonical inverse.
                from compressed_tensors.compressors.pack_quantized.helpers import (
                    unpack_from_int32,
                )
                from compressed_tensors.quantization.lifecycle.forward import dequantize

                kv_b_proj = self_attn.kv_b_proj
                scheme = kv_b_proj.scheme
                if scheme.quant_type.size_bits != 4:
                    raise ValueError("compressed kv_b_proj must be int4")
                if not scheme.symmetric or scheme.has_g_idx:
                    raise ValueError(
                        "compressed kv_b_proj requires symmetric, non-actorder weights"
                    )
                shape = kv_b_proj.weight_shape
                if shape.numel() != 2 or torch.any(shape <= 0):
                    raise ValueError("compressed kv_b_proj weight_shape must be [out, in]")
                unpacked = unpack_from_int32(
                    kv_b_proj.weight_packed,
                    scheme.quant_type.size_bits,
                    shape,
                )
                w = dequantize(
                    x_q=unpacked,
                    scale=kv_b_proj.weight_scale,
                    zero_point=None,
                    g_idx=None,
                )
                if tuple(w.shape) != tuple(shape.tolist()):
                    raise ValueError("compressed kv_b_proj dequantized shape mismatch")
            else:
                w = self_attn.kv_b_proj.weight
'''

NEW = """                            if name.endswith(\".weight_shape\"):
                                if (
                                    q_a_proj_weight.dim() != 1
                                    or kv_a_proj_weight.dim() != 1
                                    or q_a_proj_weight.numel() != 2
                                    or kv_a_proj_weight.numel() != 2
                                ):
                                    raise ValueError(
                                        \"fused q_a/kv_a weight_shape must contain two integers\"
                                    )
                                if not torch.equal(
                                    q_a_proj_weight[1:], kv_a_proj_weight[1:]
                                ):
                                    raise ValueError(
                                        \"fused q_a/kv_a projections must have equal input features\"
                                    )
                                fused_weight = torch.stack(
                                    (
                                        q_a_proj_weight[0] + kv_a_proj_weight[0],
                                        q_a_proj_weight[1],
                                    )
                                )
                            else:
                                fused_weight = torch.cat(
                                    [q_a_proj_weight, kv_a_proj_weight], dim=0
                                )
"""


def patch_source(source: str) -> str:
    matches = source.count(OLD)
    if matches != 1:
        raise ValueError(f"expected exactly one pinned fusion block, found {matches}")
    return source.replace(OLD, NEW)


def replace_once(source: str, old: str, new: str, label: str) -> str:
    matches = source.count(old)
    if matches != 1:
        raise ValueError(f"expected exactly one {label}, found {matches}")
    return source.replace(old, new)


def patch_glm_source(source: str) -> str:
    source = replace_once(source, GLM_OLD_MAPPING, GLM_NEW_MAPPING, "GLM mapping block")
    source = replace_once(
        source, GLM_OLD_QUANT_INIT, GLM_NEW_QUANT_INIT, "GLM quant init block"
    )
    return patch_source(source)


def patch_deepseek_source(source: str) -> str:
    return replace_once(
        source,
        DEEPSEEK_OLD_PACKED,
        DEEPSEEK_NEW_PACKED,
        "DeepSeek packed detection block",
    )


def patch_deepseek_weight_loader_source(source: str) -> str:
    return replace_once(
        source,
        WEIGHT_LOADER_OLD,
        WEIGHT_LOADER_NEW,
        "DeepSeek compressed kv_b post-load block",
    )


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("sglang_root", type=Path)
    args = parser.parse_args()
    files = [
        (
            args.sglang_root / "python/sglang/srt/models/glm4_moe_lite.py",
            patch_glm_source,
            "register fused mapping and compose weight_shape metadata",
        ),
        (
            args.sglang_root / "python/sglang/srt/models/deepseek_v2.py",
            patch_deepseek_source,
            "recognize compressed-tensors weight_packed projections",
        ),
        (
            args.sglang_root
            / "python/sglang/srt/models/deepseek_common/deepseek_weight_loader.py",
            patch_deepseek_weight_loader_source,
            "dequantize compressed kv_b before MLA post-load decomposition",
        ),
    ]
    records = []
    for path, transform, purpose in files:
        before = path.read_bytes()
        after = transform(before.decode()).encode()
        path.write_bytes(after)
        records.append(
            {
                "path": str(path),
                "purpose": purpose,
                "before_sha256": sha256(before),
                "after_sha256": sha256(after),
            }
        )
    print(json.dumps({"patches": records}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
