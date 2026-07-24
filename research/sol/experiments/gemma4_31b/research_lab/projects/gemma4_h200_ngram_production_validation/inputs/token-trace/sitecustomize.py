import hashlib
import inspect
import json
import os
import pathlib


def append(path, row):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")


def patch_qkv():
    if os.environ.get("QKV_STACK_ARM") != "candidate":
        return
    from install_endpoint_patch import EXPECTED_SHA256, NEW, OLD
    path = pathlib.Path("/sgl-workspace/sglang/python/sglang/srt/models/gemma4_causal.py")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256:
        if raw.decode().count(OLD) != 1:
            raise RuntimeError("QKV stack patch target is not unique")
        path.write_text(raw.decode().replace(OLD, NEW))
    elif "qkv_norm_rope_inplace" not in raw.decode():
        raise RuntimeError("QKV stack source identity mismatch")


def install_fp8_audit():
    from sglang.srt.layers.quantization import fp8_utils
    from sglang.srt.layers.quantization.fp8 import Fp8Config, Fp8LinearMethod
    modules = os.environ["FP8_STACK_MODULE_AUDIT"]
    consumers = os.environ["FP8_STACK_CONSUMER_AUDIT"]
    original_get = Fp8Config.get_quant_method
    original_process = Fp8LinearMethod.process_weights_after_loading
    original_scaled = fp8_utils.fp8_scaled_mm

    def get(self, layer, prefix):
        method = original_get(self, layer, prefix)
        if isinstance(method, Fp8LinearMethod):
            method._stack_prefix = prefix
        return method

    def process(self, layer):
        original_process(self, layer)
        append(modules, {"prefix": getattr(self, "_stack_prefix", None), "dtype": str(layer.weight.dtype)})

    seen = False
    def scaled(*args, **kwargs):
        nonlocal seen
        if not seen:
            append(consumers, {"consumer": "sglang.srt.layers.quantization.fp8_utils.fp8_scaled_mm", "pid": os.getpid(), "out_dtype": str(kwargs.get("out_dtype"))})
            seen = True
        return original_scaled(*args, **kwargs)

    Fp8Config.get_quant_method = get
    Fp8LinearMethod.process_weights_after_loading = process
    fp8_utils.fp8_scaled_mm = scaled


patch_qkv()
install_fp8_audit()

if os.environ.get("TOKEN_TRACE_EVENTS"):
    from token_trace_hook import install as install_token_trace

    install_token_trace()
