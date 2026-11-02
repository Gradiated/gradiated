import json
import hashlib
from pathlib import Path

MODEL = 'dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4'
REVISION = '745aac2ff0f10acf961f396df3f9418598aa7327'
SGLANG_SOURCE = 'f171859219b54e1dad45dda60028034490836974'
SMG_VERSION = '1.13.0'
ACTIVE_REQUESTS = 16
QUEUED_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 60


def settings(environment):
    root = Path(environment['GRADIATED_RUNTIME_ROOT'])
    if not root.is_absolute():
        raise ValueError('Runtime root must be absolute')
    if environment.get('LORA_ENABLED', 'false') != 'false':
        raise ValueError('This checkpoint has no qualified adapters')
    if environment.get('TENSOR_PARALLEL_SIZE', '2') != '2':
        raise ValueError('Qualified PCP2 profile requires TP2')
    if environment.get('MAX_QUEUED_REQUESTS') or environment.get('MAX_QUEUED_TOKENS'):
        raise ValueError('vLLM queue environment variables are not the SMG admission contract')
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if len(devices) != 2 or len(set(devices)) != 2 or any(not d.startswith('GPU-') for d in devices):
        raise ValueError('PCP2 requires exactly two assigned GPU UUIDs')
    front = int(environment['RUNTIME_PORT'])
    warmup = int(environment['WARMUP_PORT'])
    backend, metrics = front + 4, front + 5
    if not all(1024 <= p <= 65535 for p in [front, warmup, backend, metrics]):
        raise ValueError('Runtime ports are out of range')
    if len({front, warmup, backend, metrics}) != 4 or warmup in [front + 1, front + 2]:
        raise ValueError('Runtime ports overlap reserved host services')
    return {'root': root, 'front': front, 'warmup': warmup, 'backend': backend, 'metrics': metrics}


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
               '--dsa-prefill-backend', 'trtllm', '--dsa-decode-backend', 'trtllm',
               '--kv-cache-dtype', 'fp8_e4m3', '--max-running-requests', str(ACTIVE_REQUESTS),
               '--chunked-prefill-size', '16384', '--max-prefill-tokens', '16384',
               '--context-length', '1048576', '--mem-fraction-static', '0.85',
               '--cuda-graph-max-bs-decode', str(ACTIVE_REQUESTS), '--speculative-algorithm', 'EAGLE',
               '--speculative-num-steps', '2', '--speculative-eagle-topk', '1',
               '--speculative-num-draft-tokens', '3', '--reasoning-parser', 'glm45',
               '--tool-call-parser', 'glm47', '--enable-metrics', '--enable-cache-report',
               '--random-seed', '42', '--host', '127.0.0.1', '--port', str(config['backend']),
               '--cuda-graph-backend-prefill', 'disabled', '--attn-cp-size', '2',
               '--enable-prefill-cp', '--cp-strategy', 'interleave',
               '--schedule-policy', 'shortest-prefill-first', '--prefill-decode-interval', '64',
               '--prefill-decode-interval-min-bs', '0']
    router = [python, '-m', 'smg.launch_router', '--worker-urls',
              f"http://127.0.0.1:{config['backend']}", '--policy', 'round_robin',
              '--host', '127.0.0.1', '--port', str(config['front']),
              '--prometheus-host', '127.0.0.1', '--prometheus-port', str(config['metrics']),
              '--max-concurrent-requests', str(ACTIVE_REQUESTS), '--queue-size', str(QUEUED_REQUESTS),
              '--queue-timeout-secs', str(QUEUE_TIMEOUT_SECONDS),
              '--rate-limit-tokens-per-second', '0', '--request-timeout-secs', '900',
              '--worker-startup-timeout-secs', '1200', '--disable-retries']
    return config, backend, router
