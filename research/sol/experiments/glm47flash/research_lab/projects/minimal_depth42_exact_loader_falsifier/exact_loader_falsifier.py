#!/usr/bin/env python3
"""One bounded, header-only exact constructor/loader falsifier."""
from __future__ import annotations
import hashlib, json, os, resource, subprocess, time
from pathlib import Path

ROOT = Path("/root/.cache/glm47flash-awq-minimal-depth42-v2-5dbf26dc16a1")
IMAGE = "glm-vllm:0.15.0-transformers-1618d44"
OUT = Path(__file__).with_name("minimal_depth42_exact_loader_falsifier_r1.json")

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

PROBE = r'''
import hashlib, json, resource, time
from pathlib import Path
import torch
from safetensors import safe_open
from vllm.config import ModelConfig, ParallelConfig, VllmConfig, DeviceConfig
from vllm.model_executor.models import ModelRegistry

root = Path("/model")
index = json.loads((root/"model.safetensors.index.json").read_text())
names = sorted(index["weight_map"])
files = sorted(set(index["weight_map"].values()))
dtype_map = {"F64": torch.float64, "F32": torch.float32, "F16": torch.float16,
             "BF16": torch.bfloat16, "I64": torch.int64, "I32": torch.int32,
             "I16": torch.int16, "I8": torch.int8, "U8": torch.uint8, "BOOL": torch.bool}
headers = {}
for filename in files:
    with safe_open(str(root/filename), framework="pt", device="cpu") as sf:
        for name in sf.keys():
            view = sf.get_slice(name)
            headers[name] = (list(view.get_shape()), view.get_dtype())
assert set(headers) == set(names), (len(headers), len(names))

def fake_items(drop=None, foreign=False):
    items = []
    for name in names:
        if name == drop:
            continue
        shape, dtype_name = headers[name]
        items.append((name, torch.empty(shape, dtype=dtype_map[dtype_name], device="meta")))
    if foreign:
        items.append(("foreign.control.key", torch.empty((1,), dtype=torch.float32, device="meta")))
    return items

def construct():
    mc = ModelConfig(model="/model", tokenizer="/model", max_model_len=16384,
                     quantization="compressed-tensors", dtype="bfloat16")
    pc = ParallelConfig(tensor_parallel_size=1)
    vc = VllmConfig(model_config=mc, parallel_config=pc, device_config=DeviceConfig("cpu"))
    cls, _ = ModelRegistry.resolve_model_cls(mc.architectures, mc)
    with torch.device("meta"):
        model = cls(vllm_config=vc)
    return mc, vc, cls, model

result = {"header_key_count": len(names),
          "header_sha256": hashlib.sha256("\n".join(names).encode()).hexdigest(),
          "files": files, "controls": {}, "loaded": None}
t0 = time.monotonic()
try:
    mc, vc, cls, model = construct()
    result["constructor"] = {"class": cls.__name__,
        "registry": str(ModelRegistry.models["Glm4MoeLiteForCausalLM"]),
        "layers": mc.hf_config.num_hidden_layers, "quantization": mc.quantization,
        "quant_config": type(vc.quant_config).__name__,
        "parameter_count": sum(1 for _ in model.named_parameters())}
    loaded = sorted(model.load_weights(fake_items()))
    result["loaded"] = {"count": len(loaded),
        "sha256": hashlib.sha256("\n".join(loaded).encode()).hexdigest(),
        "missing": sorted(set(names)-set(loaded)),
        "unexpected": sorted(set(loaded)-set(names))}
    missing_name = names[len(names)//2]
    try:
        model.load_weights(fake_items(drop=missing_name))
        result["controls"]["missing"] = {"removed": missing_name, "outcome": "NO_FAILURE"}
    except Exception as exc:
        result["controls"]["missing"] = {"removed": missing_name, "outcome": "TYPED_FAILURE",
                                         "type": type(exc).__name__, "message": str(exc)[:500]}
    try:
        model.load_weights(fake_items(foreign=True))
        result["controls"]["foreign"] = {"outcome": "NO_FAILURE"}
    except Exception as exc:
        result["controls"]["foreign"] = {"outcome": "TYPED_FAILURE",
                                         "type": type(exc).__name__, "message": str(exc)[:500]}
    result["decision"] = ("PASS" if not result["loaded"]["missing"] and not result["loaded"]["unexpected"]
                          and result["controls"]["missing"]["outcome"] == "TYPED_FAILURE"
                          and result["controls"]["foreign"]["outcome"] == "TYPED_FAILURE" else "LOADER_MISMATCH")
except Exception as exc:
    result["decision"] = "GPU_REQUIRED" if ("cuda" in str(exc).lower() or "device" in str(exc).lower()) else "RESOURCE_OR_RUNTIME_BOUND"
    result["exception"] = {"type": type(exc).__name__, "message": str(exc)[:2000]}
result["elapsed_seconds"] = time.monotonic() - t0
result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print("RESULT=" + json.dumps(result, sort_keys=True))
'''

def main() -> None:
    started = time.monotonic()
    command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "bash",
               "-v", f"{ROOT}:/model:ro", IMAGE, "-lc", "python3 - <<'PY'\n" + PROBE + "\nPY"]
    env = {**os.environ, "VLLM_TARGET_DEVICE": "cpu", "CUDA_VISIBLE_DEVICES": ""}
    p = subprocess.run(command, capture_output=True, text=True, timeout=840, env=env)
    parsed = None
    if "RESULT=" in p.stdout:
        try:
            parsed = json.loads(p.stdout.rsplit("RESULT=", 1)[1].strip())
        except json.JSONDecodeError:
            pass
    result = {
        "schema_version": 1, "decision": parsed.get("decision") if parsed else "RESOURCE_OR_RUNTIME_BOUND",
        "image": IMAGE, "candidate_root": str(ROOT),
        "config_sha256": sha256(ROOT/"config.json"), "index_sha256": sha256(ROOT/"model.safetensors.index.json"),
        "manifest_sha256": sha256(ROOT/"model-files-manifest.json"),
        "contract_sha256": "5dbf26dc16a1cabbdb36eb256a996a11cf44c71c702b72686806a68a3bb1a290",
        "elapsed_seconds": time.monotonic()-started, "exit_code": p.returncode, "probe": parsed,
        "stdout_tail": p.stdout[-4000:], "stderr_tail": p.stderr[-4000:],
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
