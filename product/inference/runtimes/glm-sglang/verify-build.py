import argparse
import compileall
import hashlib
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

from config import MODEL, REVISION, SGLANG_SOURCE, commands


def verify(root):
    if os.environ.get('CUDA_VISIBLE_DEVICES') != '' or os.environ.get('NVIDIA_VISIBLE_DEVICES') != '':
        raise RuntimeError('Build verification requires hidden GPUs')
    import torch
    if torch.cuda.is_available() or torch.cuda.device_count():
        raise RuntimeError('Build verification must not construct GPU state')
    expected = {'torch': '2.14.1', 'transformers': '5.19.0', 'flashinfer-python': '0.7.2',
                'sglang': '0.0.0.dev0+gf171859219b54', 'smg': '1.13.0',
                'nvidia-cuda-nvcc': '13.0.88', 'nvidia-nvjitlink': '13.0.88', 'nvidia-nvvm': '13.0.88'}
    for name, version in expected.items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError('Qualified dependency changed: ' + name)
    if torch.version.cuda != '13.0' or (torch.tensor([1]) + 2).item() != 3:
        raise RuntimeError('Qualified torch binary is not usable')
    temporary = tempfile.TemporaryDirectory()
    seed_spec = importlib.util.spec_from_file_location('verified_artifact_seed', root / 'glm-sglang/artifact-cache.py')
    seed = importlib.util.module_from_spec(seed_spec)
    seed_spec.loader.exec_module(seed)
    seed.seed(root, Path(temporary.name))
    os.environ['FLASHINFER_CUBIN_DIR'] = temporary.name
    os.environ['FLASHINFER_NO_DOWNLOAD'] = '1'
    import flashinfer
    from flashinfer.jit.cubin_loader import get_artifact
    for item in json.loads((root / 'artifacts.json').read_text())['files']:
        if len(get_artifact(item['path'], item['sha256'])) != item['size']:
            raise RuntimeError('Native FlashInfer cannot read bundled artifact')
    import sglang
    from sglang.srt.configs.glm5_next import Glm5NextConfig
    from sglang.srt.server_args import ServerArgs
    from smg.launch_router import Router, parse_router_args
    from smg.smg_rs import GRADIATED_REFUSED_UPLOAD_DRAIN_VERSION
    if GRADIATED_REFUSED_UPLOAD_DRAIN_VERSION != 1:
        raise RuntimeError('Native SMG upload rejection fix is missing')
    smg_manifest = json.loads((root / 'smg-patches.json').read_text())
    if smg_manifest['upstream_sha'] != '91b3e0c440f9ab7971aa3ba48b049d951bd963de':
        raise RuntimeError('Qualified SMG source pin changed')
    if Router is None:
        raise RuntimeError('Compiled official SMG extension unavailable')
    site = Path(sglang.__file__).parent.parent
    manifest = json.loads((root / 'patches.json').read_text())
    if manifest['upstream_sha'] != SGLANG_SOURCE:
        raise RuntimeError('Qualified source pin changed')
    for item in manifest['files']:
        if hashlib.sha256((site / item['path']).read_bytes()).hexdigest() != item['overlay_sha256']:
            raise RuntimeError('Qualified source overlay changed: ' + item['path'])
    env = {'GRADIATED_RUNTIME_ROOT': str(root), 'NVIDIA_VISIBLE_DEVICES': 'GPU-cpu-check-a,GPU-cpu-check-b',
           'RUNTIME_PORT': '28080', 'WARMUP_PORT': '28083'}
    _, backend, router = commands(env)
    parser = argparse.ArgumentParser()
    ServerArgs.add_cli_args(parser)
    native = parser.parse_args(backend[3:])
    assert native.tp_size == native.attn_cp_size == 2 and native.enable_prefill_cp
    assert native.moe_runner_backend == 'marlin' and native.max_running_requests == 16
    assert native.mem_fraction_static == 0.85
    assert native.max_queued_requests is None and native.speculative_num_steps == 2
    assert native.speculative_num_draft_tokens == 3 and native.prefill_decode_interval == 64
    front = parse_router_args(router[3:])
    assert front.max_concurrent_requests == 16 and front.queue_size == 2
    assert front.queue_timeout_secs == 60 and front.rate_limit_tokens_per_second == 0
    assert front.worker_urls == ['http://127.0.0.1:28084'] and front.disable_retries
    _, hopper_backend, hopper_router = commands({**env, 'GLM_SGLANG_PROFILE': 'h200-tp2'})
    hopper = parser.parse_args(hopper_backend[3:])
    assert hopper.tp_size == 2 and not hopper.enable_prefill_cp
    assert hopper.dsa_prefill_backend == 'flashmla_sparse_q8' and hopper.dsa_decode_backend == 'tilelang'
    assert hopper.kv_cache_dtype == 'fp8_e4m3'
    assert hopper.speculative_algorithm == 'EAGLE'
    assert hopper.speculative_num_steps == 3 and hopper.speculative_num_draft_tokens == 4
    assert hopper.mem_fraction_static == 0.90 and hopper.mamba_full_memory_ratio == 1.8
    assert hopper.page_size == 256 and hopper.moe_runner_backend == 'marlin'
    assert hopper.max_running_requests == hopper.cuda_graph_max_bs_decode == 4
    assert hopper.chunked_prefill_size == hopper.max_prefill_tokens == 4096
    hopper_front = parse_router_args(hopper_router[3:])
    assert hopper_front.max_concurrent_requests == 4 and hopper_front.queue_size == 2
    _, b200_backend, b200_router = commands({**env, 'GLM_SGLANG_PROFILE': 'b200-pcp2'})
    b200 = parser.parse_args(b200_backend[3:])
    assert b200.tp_size == 2 and b200.enable_prefill_cp and b200.attn_cp_size == 2
    assert b200.dsa_prefill_backend == b200.dsa_decode_backend == 'trtllm'
    assert b200.max_running_requests == b200.cuda_graph_max_bs_decode == 8
    assert b200.mem_fraction_static == 0.85
    assert parse_router_args(b200_router[3:]).max_concurrent_requests == 8
    assert compileall.compile_dir(site / 'sglang', quiet=1)
    assert compileall.compile_dir(root / 'glm-sglang', quiet=1)
    temporary.cleanup()
    print(json.dumps({'cpu_artifact_verified': True, 'source': SGLANG_SOURCE, 'model': MODEL,
                      'revision': REVISION, 'versions': expected,
                      'qualification_required': 'Actual packaged runtime GPU, gateway, capacity, drain and cache checks'}))


if __name__ == '__main__':
    verify(Path(sys.argv[1]))
