import csv
from pathlib import Path
import re
import subprocess
import sys

MODEL_ID = 'deepseek/deepseek-v4.1-flash-1017'
MODEL = 'deepseek-ai/DeepSeek-V4.1-Flash-1017'
# The native checkpoint: FP8 (block-32, ue8m0 scales) attention and shared experts, MXFP4 routed experts.
REVISION = '1bae0e1088993b9b82de08f59de5be5a34e42170'
SGLANG_SOURCE = 'f171859219b54e1dad45dda60028034490836974'
TENSOR_PARALLEL_SIZE = 4
ACTIVE_REQUESTS = 32
QUEUED_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 10
BUNDLE_ROOT = Path(__file__).resolve().parents[1]
# The bundle's port of sgl-project/sglang#45231 adapts the five attention projections and the shared
# expert (w1/w2/w3); routed-expert adapters are rejected at load because neither FP4 MoE kernel exposes
# LoRA hooks. Names are the checkpoint's module leaves.
LORA_TARGETS = ['wq_a', 'wq_b', 'wkv', 'wo_a', 'wo_b', 'w1', 'w2', 'w3', 'lm_head']
PROFILES = {
    'b300-tp4': {'gpu_product': 'B300', 'active_requests': ACTIVE_REQUESTS, 'prefill_tokens': 16384,
                 'memory_fraction': 0.80, 'dspark_block_size': 5},
}
GPU_PROFILES = {'B300': 'b300-tp4'}


def cache_root(environment):
    base = Path(environment.get('XDG_CACHE_HOME') or str(Path(environment.get('HOME', '/home/runtime')) / '.cache'))
    return base / Path(__file__).resolve().parent.name


def qualification_identity(config, bundle_root=BUNDLE_ROOT):
    try:
        digest = (bundle_root / '.bundle-sha256').read_text().strip()
    except OSError:
        return None
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        return None
    placement = {'root', 'front', 'warmup', 'backend', 'metrics'}
    return {'bundle': digest, 'config': {key: value for key, value in config.items() if key not in placement}}


def backend_environment(environment, config):
    return dict(environment)


def settings(environment):
    profile = environment.get('DEEPSEEK_SGLANG_PROFILE', 'b300-tp4')
    if profile not in PROFILES:
        raise ValueError('Unknown DeepSeek SGLang hardware profile')
    root = Path(environment['GRADIATED_RUNTIME_ROOT'])
    if not root.is_absolute():
        raise ValueError('Runtime root must be absolute')
    if environment.get('MODEL_ID', MODEL_ID) != MODEL_ID:
        raise ValueError('This runtime serves only DeepSeek V4.1 Flash 1017')
    lora = environment.get('LORA_ENABLED', 'false')
    if lora not in {'true', 'false'}:
        raise ValueError('LORA_ENABLED must be true or false')
    if environment.get('TENSOR_PARALLEL_SIZE', str(TENSOR_PARALLEL_SIZE)) != str(TENSOR_PARALLEL_SIZE):
        raise ValueError('DeepSeek SGLang profiles require TP4')
    if environment.get('MAX_QUEUED_REQUESTS') or environment.get('MAX_QUEUED_TOKENS'):
        raise ValueError('vLLM queue environment variables are not the SMG admission contract')
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if (len(devices) != TENSOR_PARALLEL_SIZE or len(set(devices)) != TENSOR_PARALLEL_SIZE
            or any(not d.startswith('GPU-') for d in devices)):
        raise ValueError('DeepSeek SGLang requires exactly four assigned GPU UUIDs')
    front = int(environment['RUNTIME_PORT'])
    warmup = int(environment['WARMUP_PORT'])
    backend, metrics = front + 4, front + 5
    if not all(1024 <= p <= 65535 for p in [front, warmup, backend, metrics]):
        raise ValueError('Runtime ports are out of range')
    if len({front, warmup, backend, metrics}) != 4 or warmup in [front + 1, front + 2]:
        raise ValueError('Runtime ports overlap reserved host services')
    return {'root': root, 'front': front, 'warmup': warmup, 'backend': backend, 'metrics': metrics,
            'profile': profile, **PROFILES[profile], 'model_id': MODEL_ID, 'lora': lora == 'true',
            'model': MODEL, 'revision': REVISION, 'served_model_name': MODEL, 'tp': TENSOR_PARALLEL_SIZE}


def cuda_visible_devices(environment):
    """Physical indices for the assigned GPU UUIDs, in assignment order.

    SGLang's Engram and custom all-reduce NVLink checks parse CUDA_VISIBLE_DEVICES
    as integers, so the UUIDs the host agent assigns are mapped as the Kimi runtime does.
    """
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if (len(devices) != TENSOR_PARALLEL_SIZE or len(set(devices)) != TENSOR_PARALLEL_SIZE
            or any(not d.startswith('GPU-') for d in devices)):
        raise ValueError('DeepSeek SGLang requires exactly four assigned GPU UUIDs')
    result = subprocess.run(['nvidia-smi', '--id=' + ','.join(devices), '--query-gpu=index,uuid',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True, timeout=30)
    indices, seen = {}, set()
    for row in csv.reader(result.stdout.splitlines()):
        if len(row) != 2:
            raise ValueError('GPU inventory must contain an index and UUID')
        index, uuid = (value.strip() for value in row)
        if not re.fullmatch('[0-9]+', index) or uuid not in devices or uuid in indices or int(index) in seen:
            raise ValueError('GPU inventory has an invalid or duplicate assignment')
        indices[uuid] = str(int(index))
        seen.add(int(index))
    if set(indices) != set(devices):
        raise ValueError('GPU inventory does not cover every assigned UUID')
    return ','.join(indices[uuid] for uuid in devices)


def gpu_names(environment):
    return subprocess.run(['nvidia-smi', '--id=' + environment['NVIDIA_VISIBLE_DEVICES'],
                           '--query-gpu=name', '--format=csv,noheader'],
                          capture_output=True, text=True, check=True, timeout=30).stdout.splitlines()


def detect_profile(environment):
    # Host agents reject unlisted runtime environment variables, so select the profile from the GPUs.
    if environment.get('DEEPSEEK_SGLANG_PROFILE'):
        return environment
    names = gpu_names(environment)
    products = {product for name in names for product in GPU_PROFILES if re.search(r'\b' + product + r'\b', name)}
    if not names or len(products) != 1:
        raise ValueError('Assigned GPUs do not match a DeepSeek SGLang hardware profile')
    return {**environment, 'DEEPSEEK_SGLANG_PROFILE': GPU_PROFILES[products.pop()]}


def validate_hardware(environment):
    config = settings(environment)
    names = gpu_names(environment)
    if len(names) != TENSOR_PARALLEL_SIZE or any(
            not re.search(r'\b' + config['gpu_product'] + r'\b', name) for name in names):
        raise ValueError('Assigned GPUs do not match the selected DeepSeek SGLang hardware profile')


def lora_arguments(environment):
    for candidate in [Path(__file__).resolve().parents[1] / 'lora', Path(__file__).resolve().parents[2] / 'lora']:
        if (candidate / 'adapter_service.py').is_file() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    from adapter_service import engine_arguments, engine_settings
    return engine_arguments(engine_settings(environment, '', TENSOR_PARALLEL_SIZE, {}), LORA_TARGETS)


def commands(environment):
    config = settings(environment)
    python = str(config['root'] / 'python/bin/python3')
    active = config['active_requests']
    backend = [python, '-m', 'sglang.launch_server', '--model-path', MODEL, '--revision', REVISION,
               '--served-model-name', MODEL, '--tp-size', str(TENSOR_PARALLEL_SIZE),
               '--ep-size', str(TENSOR_PARALLEL_SIZE), '--context-length', '1048576',
               '--mem-fraction-static', str(config['memory_fraction']),
               '--max-running-requests', str(active), '--cuda-graph-max-bs-decode', str(active),
               '--chunked-prefill-size', str(config['prefill_tokens']),
               '--max-prefill-tokens', str(config['prefill_tokens']),
               '--speculative-algorithm', 'DSPARK',
               '--speculative-dspark-block-size', str(config['dspark_block_size']),
               '--reasoning-parser', 'deepseek-v41', '--tool-call-parser', 'deepseekv41',
               '--enable-metrics', '--enable-cache-report', '--random-seed', '42',
               '--host', '127.0.0.1', '--port', str(config['backend']), '--watchdog-timeout', '3600']
    if config['lora']:
        # Only the Triton LoRA backend implements the grouped wo_a adapter; LoRA keeps the
        # FlashMLA (not MegaAttention) decode backend that the patched hook requires.
        backend += ['--lora-backend', 'triton', *lora_arguments(environment)]
    router = [python, '-m', 'smg.launch_router', '--worker-urls',
              f"http://127.0.0.1:{config['backend']}", '--policy', 'round_robin',
              '--host', '127.0.0.1', '--port', str(config['front']),
              '--prometheus-host', '127.0.0.1', '--prometheus-port', str(config['metrics']),
              '--max-concurrent-requests', str(active), '--queue-size', str(QUEUED_REQUESTS),
              '--queue-timeout-secs', str(QUEUE_TIMEOUT_SECONDS),
              '--rate-limit-tokens-per-second', '0', '--request-timeout-secs', '900',
              '--worker-startup-timeout-secs', '3000', '--disable-retries']
    return config, backend, router


if __name__ == '__main__':
    import os
    if sys.argv[1:] != ['--cuda-visible-devices']:
        raise SystemExit('usage: config.py --cuda-visible-devices')
    print(cuda_visible_devices(os.environ))
