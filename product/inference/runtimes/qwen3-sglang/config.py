from pathlib import Path
import re
import subprocess
import sys

# The public model ID is the Hugging Face ID grad trains on, so adapters name it as their base.
MODEL_ID = 'Qwen/Qwen3-8B'
MODEL = 'Qwen/Qwen3-8B'
# The revision grad pins for training (MODEL_CATALOG); served adapters must match it.
REVISION = 'b968826d9c46dd6066d109eabc6255188de91218'
SGLANG_SOURCE = 'f171859219b54e1dad45dda60028034490836974'
TENSOR_PARALLEL_SIZE = 1
# The checkpoint's max_position_embeddings.
CONTEXT_TOKENS = 40960
ACTIVE_REQUESTS = 64
QUEUED_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 10
BUNDLE_ROOT = Path(__file__).resolve().parents[1]
# grad's default LoRA targets: every linear projection of a Qwen3 decoder layer.
LORA_TARGETS = ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'gate_proj', 'up_proj', 'down_proj']
# Dense BF16 on one GPU: 16 GiB of weights leaves most of a B300 for KV cache.
PROFILES = {
    'b300-tp1': {'gpu_product': 'B300', 'active_requests': ACTIVE_REQUESTS, 'prefill_tokens': 16384,
                 'memory_fraction': 0.85},
}
GPU_PROFILES = {'B300': 'b300-tp1'}


def cache_root(environment):
    base = Path(environment.get('XDG_CACHE_HOME') or str(Path(environment.get('HOME', '/home/runtime')) / '.cache'))
    return base / Path(__file__).resolve().parent.name


def qualification_identity(config, bundle_root=BUNDLE_ROOT):
    """What a recorded qualification must match beyond the GPUs, or None outside a verified bundle."""
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
    profile = environment.get('QWEN3_SGLANG_PROFILE', 'b300-tp1')
    if profile not in PROFILES:
        raise ValueError('Unknown Qwen3 SGLang hardware profile')
    root = Path(environment['GRADIATED_RUNTIME_ROOT'])
    if not root.is_absolute():
        raise ValueError('Runtime root must be absolute')
    if environment.get('MODEL_ID', MODEL_ID) != MODEL_ID:
        raise ValueError('This runtime serves only Qwen3 8B')
    lora = environment.get('LORA_ENABLED', 'false')
    if lora not in {'true', 'false'}:
        raise ValueError('LORA_ENABLED must be true or false')
    if 'CARTRIDGE_POOL_BYTES' in environment:
        raise ValueError('Qwen3 SGLang does not serve cartridges')
    if environment.get('TENSOR_PARALLEL_SIZE', str(TENSOR_PARALLEL_SIZE)) != str(TENSOR_PARALLEL_SIZE):
        raise ValueError('Qwen3 SGLang profiles require TP1')
    if environment.get('MAX_QUEUED_REQUESTS') or environment.get('MAX_QUEUED_TOKENS'):
        raise ValueError('vLLM queue environment variables are not the SMG admission contract')
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if len(devices) != TENSOR_PARALLEL_SIZE or any(not d.startswith('GPU-') for d in devices):
        raise ValueError('Qwen3 SGLang requires exactly one assigned GPU UUID')
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


def gpu_names(environment):
    return subprocess.run(['nvidia-smi', '--id=' + environment['NVIDIA_VISIBLE_DEVICES'],
                           '--query-gpu=name', '--format=csv,noheader'],
                          capture_output=True, text=True, check=True, timeout=30).stdout.splitlines()


def detect_profile(environment):
    # Host agents reject unlisted runtime environment variables, so select the profile from the GPU.
    if environment.get('QWEN3_SGLANG_PROFILE'):
        return environment
    names = gpu_names(environment)
    products = {product for name in names for product in GPU_PROFILES if re.search(r'\b' + product + r'\b', name)}
    if not names or len(products) != 1:
        raise ValueError('Assigned GPUs do not match a Qwen3 SGLang hardware profile')
    return {**environment, 'QWEN3_SGLANG_PROFILE': GPU_PROFILES[products.pop()]}


def validate_hardware(environment):
    config = settings(environment)
    names = gpu_names(environment)
    if len(names) != TENSOR_PARALLEL_SIZE or any(
            not re.search(r'\b' + config['gpu_product'] + r'\b', name) for name in names):
        raise ValueError('Assigned GPUs do not match the selected Qwen3 SGLang hardware profile')


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
    backend = [python, str(config['root'] / 'energy/launch.py'), '--model-path', MODEL, '--revision', REVISION,
               '--served-model-name', MODEL, '--tp-size', str(TENSOR_PARALLEL_SIZE),
               '--context-length', str(CONTEXT_TOKENS),
               '--mem-fraction-static', str(config['memory_fraction']),
               '--max-running-requests', str(active), '--cuda-graph-max-bs-decode', str(active),
               '--chunked-prefill-size', str(config['prefill_tokens']),
               '--max-prefill-tokens', str(config['prefill_tokens']),
               '--reasoning-parser', 'qwen3', '--tool-call-parser', 'qwen25',
               '--enable-metrics', '--enable-cache-report', '--random-seed', '42',
               '--host', '127.0.0.1', '--port', str(config['backend']), '--watchdog-timeout', '3600']
    if config['lora']:
        backend += lora_arguments(environment)
    router = [python, '-m', 'smg.launch_router', '--worker-urls',
              f"http://127.0.0.1:{config['backend']}", '--policy', 'round_robin',
              '--host', '127.0.0.1', '--port', str(config['front']),
              '--prometheus-host', '127.0.0.1', '--prometheus-port', str(config['metrics']),
              '--max-concurrent-requests', str(active), '--queue-size', str(QUEUED_REQUESTS),
              '--queue-timeout-secs', str(QUEUE_TIMEOUT_SECONDS),
              '--rate-limit-tokens-per-second', '0', '--request-timeout-secs', '900',
              '--worker-startup-timeout-secs', '1200', '--disable-retries']
    return config, backend, router
