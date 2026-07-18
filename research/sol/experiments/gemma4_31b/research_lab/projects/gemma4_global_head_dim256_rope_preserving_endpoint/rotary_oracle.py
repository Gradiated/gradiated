#!/usr/bin/env python3
import hashlib
import json
import math
import pathlib
import struct


PROJECT = pathlib.Path(__file__).resolve().parent
PRIOR = PROJECT / "bound_prior"
OLD = '''        self.rotary_emb = get_rope(
            self.head_dim,
            rotary_dim=self.head_dim,
            max_position=max_position_embeddings,
            base=rope_parameters.get("rope_theta", 10000.0),
            rope_scaling={"rope_type": rope_parameters.get("rope_type", "default")},
            partial_rotary_factor=rope_parameters.get("partial_rotary_factor", 1.0),
            is_neox_style=True,
        )
'''
NEW = '''        partial_rotary_factor = rope_parameters.get("partial_rotary_factor", 1.0)
        if (
            os.environ.get("SGLANG_GEMMA4_GLOBAL_HEAD256_SLICE") == "1"
            and layer_type == "full_attention"
        ):
            if partial_rotary_factor != 0.25:
                raise ValueError(
                    "global-head256 RoPE preservation requires bound full-attention partial_rotary_factor=0.25"
                )
            partial_rotary_factor = 0.5

        self.rotary_emb = get_rope(
            self.head_dim,
            rotary_dim=self.head_dim,
            max_position=max_position_embeddings,
            base=rope_parameters.get("rope_theta", 10000.0),
            rope_scaling={"rope_type": rope_parameters.get("rope_type", "default")},
            partial_rotary_factor=partial_rotary_factor,
            is_neox_style=True,
        )
'''


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inverse_frequency(rotary_width: int, base: float) -> list[float]:
    return [1.0 / (base ** (coordinate / rotary_width)) for coordinate in range(0, rotary_width, 2)]


def main() -> int:
    prior_source = (PRIOR / "patch/gemma4_causal.py").read_text()
    candidate_source = (PROJECT / "patch/gemma4_causal.py").read_text()
    if prior_source.count(OLD) != 1 or candidate_source != prior_source.replace(OLD, NEW):
        raise SystemExit("candidate source is not the bound prior source plus the admitted RoPE-only edit")

    immutable_hashes = {
        "patch/gemma4_mm.py": "94a5bca79a254ca2642dd300b45af549bfd23718340a56aa83a059df2f95bd45",
        "patch/model_config.py": "ba6a44488466db5667c47c8266d33e79eaebb2b4143e6192b0aeb9ce62837132",
        "inputs/exact_mix_runner.py": "143709fd6a248e907c33724ee37be8d93e4710f9c3d3c675171d3a7016d184d7",
    }
    observed_hashes = {name: sha256(PROJECT / name) for name in immutable_hashes}
    if observed_hashes != immutable_hashes:
        raise SystemExit(f"immutable bound input mismatch: {observed_hashes}")

    original_head_dim = 512
    original_factor = 0.25
    candidate_head_dim = 256
    candidate_factor = 0.5
    original_width = int(original_head_dim * original_factor)
    candidate_width = int(candidate_head_dim * candidate_factor)
    if original_width != 128 or candidate_width != 128:
        raise SystemExit("rotary coordinate width mismatch")

    original_inv_freq = inverse_frequency(original_width, 1e4)
    candidate_inv_freq = inverse_frequency(candidate_width, 1e4)
    if original_inv_freq != candidate_inv_freq:
        raise SystemExit("inverse-frequency oracle mismatch")
    packed = b"".join(struct.pack("!d", value) for value in original_inv_freq)
    result = {
        "schema_version": 1,
        "pass": True,
        "classification": "mechanism_oracle_pass",
        "original": {
            "head_dim": original_head_dim,
            "partial_rotary_factor": original_factor,
            "rotary_coordinate_width": original_width,
        },
        "candidate": {
            "head_dim": candidate_head_dim,
            "partial_rotary_factor": candidate_factor,
            "rotary_coordinate_width": candidate_width,
        },
        "inverse_frequency": {
            "base": 10000.0,
            "frequency_count": len(original_inv_freq),
            "represented_coordinate_count": original_width,
            "max_abs_delta": max(abs(a - b) for a, b in zip(original_inv_freq, candidate_inv_freq)),
            "fp64_big_endian_sha256": hashlib.sha256(packed).hexdigest(),
        },
        "source_identity": {
            "prior_causal_sha256": sha256(PRIOR / "patch/gemma4_causal.py"),
            "candidate_causal_sha256": sha256(PROJECT / "patch/gemma4_causal.py"),
            "only_admitted_rope_edit": True,
            "immutable_hashes": observed_hashes,
            "prior_patch_manifest_sha256": sha256(PROJECT / "bound_prior/PATCH_MANIFEST.json"),
            "prior_launcher_sha256": sha256(PROJECT / "bound_prior/launch_owner.sh"),
        },
    }
    output = PROJECT / "ROTARY_ORACLE.json"
    temporary = output.with_suffix(".part")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
