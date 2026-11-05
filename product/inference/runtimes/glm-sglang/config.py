import json
import hashlib
from pathlib import Path
import re
import subprocess

MODEL = 'dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4'
REVISION = '745aac2ff0f10acf961f396df3f9418598aa7327'
SGLANG_SOURCE = 'f171859219b54e1dad45dda60028034490836974'
SMG_VERSION = '1.13.0'
ACTIVE_REQUESTS = 16
QUEUED_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 60
PROFILES = {
    'b300-pcp2': {'gpu_product': 'B300', 'active_requests': ACTIVE_REQUESTS,
                  'prefill_tokens': 16384, 'dsa_backend': 'trtllm', 'context_parallel': True},
    # Same Blackwell kernels as B300 with about two thirds of the HBM, so half the active requests.
    'b200-pcp2': {'gpu_product': 'B200', 'active_requests': 8,
                  'prefill_tokens': 16384, 'dsa_backend': 'trtllm', 'context_parallel': True},
    'h200-tp2': {'gpu_product': 'H200', 'active_requests': 4,
                 'prefill_tokens': 4096, 'dsa_backend': 'tilelang', 'dsa_prefill': 'flashmla_sparse_q8', 'kv_dtype': 'fp8_e4m3',
                 'speculative_steps': 3, 'mamba_memory_ratio': 1.8, 'memory_fraction': 0.90,
                 'context_parallel': False},
}


def settings(environment):
    profile = environment.get('GLM_SGLANG_PROFILE', 'b300-pcp2')
    if profile not in PROFILES:
        raise ValueError('Unknown GLM SGLang hardware profile')
    root = Path(environment['GRADIATED_RUNTIME_ROOT'])
    if not root.is_absolute():
        raise ValueError('Runtime root must be absolute')
    if environment.get('LORA_ENABLED', 'false') != 'false':
        raise ValueError('This checkpoint has no qualified adapters')
    if environment.get('TENSOR_PARALLEL_SIZE', '2') != '2':
        raise ValueError('GLM SGLang profiles require TP2')
    if environment.get('MAX_QUEUED_REQUESTS') or environment.get('MAX_QUEUED_TOKENS'):
        raise ValueError('vLLM queue environment variables are not the SMG admission contract')
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if len(devices) != 2 or len(set(devices)) != 2 or any(not d.startswith('GPU-') for d in devices):
        raise ValueError('GLM SGLang requires exactly two assigned GPU UUIDs')
    front = int(environment['RUNTIME_PORT'])
    warmup = int(environment['WARMUP_PORT'])
    backend, metrics = front + 4, front + 5
    if not all(1024 <= p <= 65535 for p in [front, warmup, backend, metrics]):
        raise ValueError('Runtime ports are out of range')
    if len({front, warmup, backend, metrics}) != 4 or warmup in [front + 1, front + 2]:
        raise ValueError('Runtime ports overlap reserved host services')
    return {'root': root, 'front': front, 'warmup': warmup, 'backend': backend, 'metrics': metrics,
            'profile': profile, **PROFILES[profile]}


GPU_PROFILES = {'B200': 'b200-pcp2', 'B300': 'b300-pcp2', 'H200': 'h200-tp2'}


def gpu_names(environment):
    return subprocess.run(['nvidia-smi', '--id=' + environment['NVIDIA_VISIBLE_DEVICES'],
                           '--query-gpu=name', '--format=csv,noheader'],
                          capture_output=True, text=True, check=True, timeout=30).stdout.splitlines()


def detect_profile(environment):
    # Host agents reject unlisted runtime environment variables, so a runtime may
    # arrive without GLM_SGLANG_PROFILE; select it from the assigned GPUs instead.
    if environment.get('GLM_SGLANG_PROFILE'):
        return environment
    names = gpu_names(environment)
    products = {product for name in names for product in GPU_PROFILES if re.search(r'\b' + product + r'\b', name)}
    if not names or len(products) != 1:
        raise ValueError('Assigned GPUs do not match a GLM SGLang hardware profile')
    return {**environment, 'GLM_SGLANG_PROFILE': GPU_PROFILES[products.pop()]}


def validate_hardware(environment):
    config = settings(environment)
    names = gpu_names(environment)
    if len(names) != 2 or any(not re.search(r'\b' + config['gpu_product'] + r'\b', name) for name in names):
        raise ValueError('Assigned GPUs do not match the selected GLM SGLang hardware profile')


def commands(environment):
    config = settings(environment)
    root = config['root']
    python = str(root / 'python/bin/python3')
    model_config = json.loads((root / 'model-config.json').read_text())
    encoded = json.dumps(model_config, sort_keys=True, separators=(',', ':')).encode()
    if hashlib.sha256(encoded).hexdigest() != '08d31c499953794bcf83669497c69c856160927ce29c7df037b8ae315f4f5bdd':
        raise ValueError('Qualified GLM quantization overrides changed')
    backend = [python, '-m', 'sglang.launch_server', '--model-path', MODEL,
               '--revision', REVISION, '--served-model-name', MODEL, '--tp-size', '2',
               '--ep-size', '1', '--moe-dense-tp-size', '2', '--quantization', 'modelopt_fp4',
               '--json-model-override-args', json.dumps(model_config, separators=(',', ':')),
               '--moe-runner-backend', 'marlin', '--disable-shared-experts-fusion',
               '--dsa-prefill-backend', config.get('dsa_prefill', config['dsa_backend']), '--dsa-decode-backend', config['dsa_backend'],
               '--kv-cache-dtype', config.get('kv_dtype', 'fp8_e4m3'), '--max-running-requests', str(config['active_requests']),
               '--chunked-prefill-size', str(config['prefill_tokens']), '--max-prefill-tokens', str(config['prefill_tokens']),
               '--context-length', '1048576', '--mem-fraction-static', str(config.get('memory_fraction', 0.85)),
               '--cuda-graph-max-bs-decode', str(config['active_requests']), '--reasoning-parser', 'glm45',
               '--tool-call-parser', 'glm47', '--enable-metrics', '--enable-cache-report',
               '--random-seed', '42', '--host', '127.0.0.1', '--port', str(config['backend']),
               '--cuda-graph-backend-prefill', 'disabled',
               '--schedule-policy', 'shortest-prefill-first', '--prefill-decode-interval', '64',
               '--prefill-decode-interval-min-bs', '0']
    steps = config.get('speculative_steps', 2)
    backend += ['--speculative-algorithm', 'EAGLE', '--speculative-num-steps', str(steps),
                '--speculative-eagle-topk', '1', '--speculative-num-draft-tokens', str(steps + 1)]
    if 'mamba_memory_ratio' in config:
        backend += ['--mamba-full-memory-ratio', str(config['mamba_memory_ratio'])]
    if config['context_parallel']:
        backend += ['--attn-cp-size', '2', '--enable-prefill-cp', '--cp-strategy', 'interleave']
    else:
        # GLM pools four logical tokens per key; FlashMLA needs 64 physical slots per page.
        backend += ['--page-size', '256']
    router = [python, '-m', 'smg.launch_router', '--worker-urls',
              f"http://127.0.0.1:{config['backend']}", '--policy', 'round_robin',
              '--host', '127.0.0.1', '--port', str(config['front']),
              '--prometheus-host', '127.0.0.1', '--prometheus-port', str(config['metrics']),
              '--max-concurrent-requests', str(config['active_requests']), '--queue-size', str(QUEUED_REQUESTS),
              '--queue-timeout-secs', str(QUEUE_TIMEOUT_SECONDS),
              '--rate-limit-tokens-per-second', '0', '--request-timeout-secs', '900',
              '--worker-startup-timeout-secs', '1200', '--disable-retries']
    return config, backend, router
