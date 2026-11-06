from pathlib import Path
import csv
import os
import re
import subprocess
import sys

MODEL = 'moonshotai/Kimi-K3.1-Pro'
REVISION = 'd9e99b0792a5e93b78ea9bea62a68167e36ddd9e'
SGLANG_SOURCE = 'afcd7d6b487a9cbe73e25941971b4cc107e6f9ae'
KIMI_OVERLAY_FINGERPRINT = '6509efad47e02e681caa9cdb49bb9b9375fb94aa30276fcfa5a082e9bfcdab3e'
DRAFT_MODEL = 'RadixArk/Kimi-K3.1-Dflash2-Preview'
DRAFT_REVISION = 'd0d8bc2e3c6d0a195d2e00a49017e71ca8d881f1'
ACTIVE_REQUESTS = 2
QUEUED_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 60


def cuda_visible_devices(environment):
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if len(devices) != 8 or len(set(devices)) != 8 or any(not d.startswith('GPU-') for d in devices):
        raise ValueError('Kimi K3.1 Pro requires eight distinct assigned GPU UUIDs')
    result = subprocess.run(['nvidia-smi', '--id=' + ','.join(devices),
                             '--query-gpu=index,uuid', '--format=csv,noheader,nounits'],
                            capture_output=True, text=True, check=True, timeout=30)
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


def settings(environment):
    root = Path(environment['GRADIATED_RUNTIME_ROOT'])
    if not root.is_absolute():
        raise ValueError('Runtime root must be absolute')
    if environment.get('LORA_ENABLED', 'false') != 'false':
        raise ValueError('Kimi K3.1 Pro has no qualified adapters')
    if environment.get('TENSOR_PARALLEL_SIZE', '8') != '8':
        raise ValueError('Kimi K3.1 Pro requires TP8')
    devices = environment['NVIDIA_VISIBLE_DEVICES'].split(',')
    if len(devices) != 8 or len(set(devices)) != 8 or any(not d.startswith('GPU-') for d in devices):
        raise ValueError('Kimi K3.1 Pro requires eight distinct assigned GPU UUIDs')
    if environment.get('MAX_QUEUED_REQUESTS') or environment.get('MAX_QUEUED_TOKENS'):
        raise ValueError('Kimi admission is owned by the immutable SMG configuration')
    front, warmup = int(environment['RUNTIME_PORT']), int(environment['WARMUP_PORT'])
    backend, metrics = front + 4, front + 5
    ports = [front, warmup, backend, metrics]
    if not all(1024 <= p <= 65535 for p in ports) or len(set(ports)) != 4 or warmup in [front + 1, front + 2]:
        raise ValueError('Runtime ports overlap or are outside the host allocation')
    return {'root': root, 'front': front, 'warmup': warmup, 'backend': backend,
            'metrics': metrics, 'active_requests': ACTIVE_REQUESTS}


def validate_hardware(environment):
    names = subprocess.run(['nvidia-smi', '--id=' + environment['NVIDIA_VISIBLE_DEVICES'],
                            '--query-gpu=name', '--format=csv,noheader'],
                           capture_output=True, text=True, check=True, timeout=30).stdout.splitlines()
    if len(names) != 8 or any(not re.search(r'\bB300\b', name) for name in names):
        raise ValueError('Kimi K3.1 Pro requires eight B300 GPUs')


def commands(environment):
    config = settings(environment)
    python = str(config['root'] / 'python/bin/python3')
    backend = [python, '-m', 'sglang.launch_server', '--model-path', MODEL,
               '--revision', REVISION, '--served-model-name', MODEL, '--tp-size', '8', '--trust-remote-code',
               '--reasoning-parser', 'kimi_k3', '--tool-call-parser', 'kimi_k3',
               '--moe-runner-backend', 'flashinfer_mxfp4', '--flashinfer-mxfp4-moe-precision', 'default',
               '--speculative-algorithm', 'DFLASH', '--speculative-draft-model-path',
               str(config['root'] / 'models/kimi-dflash'),
               '--speculative-draft-model-revision', DRAFT_REVISION,
               '--speculative-draft-attention-backend', 'cutedsl_mla',
               '--speculative-dflash-block-size', '5', '--disable-overlap-schedule',
               '--enable-linear-replayssm-spec', '--mamba-ssm-dtype', 'float32',
               '--max-running-requests', str(ACTIVE_REQUESTS), '--context-length', '1048576',
               '--mem-fraction-static', '0.85', '--chunked-prefill-size', '8192',
               '--mamba-full-memory-ratio', '0.45', '--prefill-decode-interval', '0',
               '--max-prefill-tokens', '8192', '--cuda-graph-max-bs-decode', str(ACTIVE_REQUESTS),
               '--enable-metrics', '--random-seed', '42',
               '--host', '127.0.0.1', '--port', str(config['backend'])]
    router = [python, '-m', 'smg.launch_router', '--worker-urls',
              f"http://127.0.0.1:{config['backend']}", '--policy', 'round_robin',
              '--host', '127.0.0.1', '--port', str(config['front']),
              '--prometheus-host', '127.0.0.1', '--prometheus-port', str(config['metrics']),
              '--max-concurrent-requests', str(ACTIVE_REQUESTS), '--queue-size', str(QUEUED_REQUESTS),
              '--queue-timeout-secs', str(QUEUE_TIMEOUT_SECONDS),
              '--rate-limit-tokens-per-second', '0', '--request-timeout-secs', '3600',
              '--worker-startup-timeout-secs', '3600', '--disable-retries']
    return config, backend, router


if __name__ == '__main__':
    if sys.argv[1:] != ['--cuda-visible-devices']:
        raise SystemExit('usage: config.py --cuda-visible-devices')
    print(cuda_visible_devices(os.environ))
