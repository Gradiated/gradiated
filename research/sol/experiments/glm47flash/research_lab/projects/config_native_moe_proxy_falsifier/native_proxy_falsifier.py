"""Bounded, CPU/meta-only falsifier for stock GLM4-MoE-Lite semantics."""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys

import torch
from safetensors import safe_open
from transformers import AutoConfig, __version__ as transformers_version
from transformers.models.glm4_moe_lite.modeling_glm4_moe_lite import (
    Glm4MoeLiteForCausalLM,
)


ROOT = pathlib.Path("/root/.cache/glm47flash-awq-ab31d120")
OUT = pathlib.Path(__file__).with_name("NATIVE_PROXY_FALSIFIER_2026-07-16.json")


def sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def construct(changes: dict[str, int]):
    config = AutoConfig.from_pretrained(ROOT, local_files_only=True)
    for key, value in changes.items():
        setattr(config, key, value)
    with torch.device("meta"):
        model = Glm4MoeLiteForCausalLM(config)
    return config, model


def main() -> None:
    index = json.loads((ROOT / "model.safetensors.index.json").read_text())
    index_keys = set(index["weight_map"])
    config, stock = construct({})
    candidate_config, candidate = construct({"num_experts_per_tok": 2, "n_shared_experts": 0})
    stock_keys = set(stock.state_dict())
    candidate_keys = set(candidate.state_dict())
    shared_key = "model.layers.1.mlp.shared_experts.gate_proj.weight"
    shard = ROOT / index["weight_map"][shared_key]
    with safe_open(str(shard), framework="pt", device="cpu") as handle:
        checkpoint_shape = list(handle.get_slice(shared_key).get_shape())
        checkpoint_dtype = str(handle.get_slice(shared_key).get_dtype())
    expected_shape = list(candidate.state_dict()[shared_key].shape)
    load_error = None
    try:
        candidate.load_state_dict({shared_key: torch.empty(checkpoint_shape)}, strict=False)
    except RuntimeError as exc:
        load_error = str(exc).splitlines()[0]

    proxy = 617.3154342551707
    current = 552.1710554232396
    old = 535.2861037029285
    transfer = proxy / old
    endpoint_transfer = current * transfer
    result = {
        "schema_version": 1,
        "evidence_label": "measured_constructor_loader_plus_derived_endpoint_transfer",
        "decision": "RUNTIME_CLOSE",
        "runtime": {
            "transformers_version": transformers_version,
            "torch_version": torch.__version__,
            "source_sha256": sha256(pathlib.Path(__file__).parent / "native_proxy_falsifier.py"),
        },
        "checkpoint": {
            "path": str(ROOT),
            "config_sha256": sha256(ROOT / "config.json"),
            "index_sha256": sha256(ROOT / "model.safetensors.index.json"),
            "revision": "ab31d120fbe79988fe2a0259993cf3c222aa8881",
        },
        "constructor": {
            "stock": {"construct": "PASS", "top_k": config.num_experts_per_tok, "n_shared_experts": config.n_shared_experts},
            "candidate": {"construct": "PASS", "top_k": candidate_config.num_experts_per_tok, "n_shared_experts": candidate_config.n_shared_experts},
            "candidate_shared_module": {"present": shared_key in candidate_keys, "expected_shape": expected_shape},
        },
        "loader": {
            "checkpoint_shared_key": shared_key in index_keys,
            "checkpoint_shape": checkpoint_shape,
            "checkpoint_dtype": checkpoint_dtype,
            "candidate_key_set_sha256": hashlib.sha256("\n".join(sorted(candidate_keys)).encode()).hexdigest(),
            "checkpoint_key_set_sha256": hashlib.sha256("\n".join(sorted(index_keys)).encode()).hexdigest(),
            "candidate_key_count": len(candidate_keys),
            "checkpoint_key_count": len(index_keys),
            "candidate_shared_key_count": sum("shared_experts" in key for key in candidate_keys),
            "candidate_shared_shape_mismatch": expected_shape != checkpoint_shape,
            "load_error": load_error,
            "silent_drop_required": True,
        },
        "endpoint_transfer": {
            "proxy_tok_per_s": proxy,
            "current_same_stack_tok_per_s": current,
            "older_proxy_denominator_tok_per_s": old,
            "derived_transfer_ratio": transfer,
            "derived_endpoint_tok_per_s": endpoint_transfer,
            "gate_tok_per_s": 594.466,
            "admissible": False,
            "note": "Transfer is not promotable because native loader semantics fail; summed-kernel proxy is not wall-time evidence.",
        },
        "terminal_reason": "n_shared_experts=0 constructs zero-width shared Linear modules but retains shared state keys; exact checkpoint shared tensors are nonzero and load raises a shape mismatch. Omitting those keys requires silent unexpected-key drops or a runtime/source forward-loader change.",
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
