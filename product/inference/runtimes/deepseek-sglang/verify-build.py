import argparse
import compileall
import hashlib
import importlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from config import MODEL, REVISION, SGLANG_SOURCE, commands


def verify(root):
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '' or os.environ.get('NVIDIA_VISIBLE_DEVICES') != '':
        raise RuntimeError('Build verification requires hidden GPUs')
    import torch
    if torch.cuda.is_available() or torch.cuda.device_count():
        raise RuntimeError('Build verification must not construct GPU state')
    for name in ['launch', 'service']:
        module = importlib.import_module(name)
        if Path(module.__file__).resolve().parent != root / 'deepseek-sglang':
            raise RuntimeError('Packaged launcher import resolved outside the runtime: ' + name)
    expected = {'torch': '2.14.1', 'transformers': '5.19.0', 'flashinfer-python': '0.7.2',
                'sglang': '0.0.0.dev0+gf171859219b54', 'smg': '1.13.0'}
    for name, version in expected.items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError('Qualified dependency changed: ' + name)
    import flashinfer_jit_cache
    providers = {p.provider_id: p for p in flashinfer_jit_cache.get_jit_cache_providers()}
    if 'fused_moe_trtllm_sm100' not in getattr(providers.get('sm103a'), 'modules', ()):
        raise RuntimeError('Prebuilt B300 FlashInfer MoE op is missing')
    import sglang
    from sglang.srt.server_args import ServerArgs
    from sglang.srt.models.deepseek_v4 import DeepseekV4ForCausalLM  # noqa: F401
    from smg.launch_router import Router, parse_router_args
    if Router is None:
        raise RuntimeError('Compiled official SMG extension unavailable')
    site = Path(sglang.__file__).parent.parent
    manifest = json.loads((root / 'patches.json').read_text())
    if manifest['upstream_sha'] != SGLANG_SOURCE:
        raise RuntimeError('Qualified source pin changed')
    # A path may carry stacked overlays; the installed file must match the last one.
    final = {item['path']: item['overlay_sha256'] for item in manifest['files']}
    for path, digest in final.items():
        if hashlib.sha256((site / path).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Qualified source overlay changed: ' + path)
    env = {'GRADIATED_RUNTIME_ROOT': str(root), 'RUNTIME_PORT': '28080', 'WARMUP_PORT': '28083',
           'NVIDIA_VISIBLE_DEVICES': ','.join(f'GPU-cpu-check-{index}' for index in range(4))}
    parser = argparse.ArgumentParser()
    ServerArgs.add_cli_args(parser)
    _, backend, router = commands(env)
    native = parser.parse_args(backend[3:])
    assert native.tp_size == native.ep_size == 4 and native.speculative_algorithm == 'DSPARK'
    assert native.max_running_requests == native.cuda_graph_max_bs_decode
    assert native.reasoning_parser == 'deepseek-v41' and native.tool_call_parser == 'deepseekv41'
    front = parse_router_args(router[3:])
    assert front.max_concurrent_requests == native.max_running_requests and front.disable_retries
    lora = {**env, 'LORA_ENABLED': 'true', 'MODEL_ID': 'deepseek/deepseek-v4.1-flash-1017',
            'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64', 'LORA_MAX_RANK': '8',
            'LORA_DISK_CACHE_BYTES': '1073741824', 'LORA_DOWNLOAD_HOSTS': 'artifacts.s3.amazonaws.com'}
    adapted = parser.parse_args(commands(lora)[1][3:])
    assert adapted.enable_lora and adapted.max_loras_per_batch == 8 and adapted.max_loaded_loras == 64
    assert compileall.compile_dir(site / 'sglang', quiet=1)
    assert compileall.compile_dir(root / 'deepseek-sglang', quiet=1)
    print(json.dumps({'cpu_artifact_verified': True, 'source': SGLANG_SOURCE, 'model': MODEL,
                      'revision': REVISION, 'versions': expected,
                      'qualification_required': 'Packaged runtime GPU, gateway, LoRA and capacity checks'}))


if __name__ == '__main__':
    verify(Path(sys.argv[1]))
