import fcntl
import json
import os
import hashlib
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time

MODEL = 'dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4'
REVISION = '745aac2ff0f10acf961f396df3f9418598aa7327'
UNCENSORED = 'dealignai/glm-5.3-flash-uncensored'
# Public model ID (MODEL_ID) -> served checkpoint. Runtimes without MODEL_ID serve the uncensored model.
MODELS = {
    UNCENSORED: {'model': MODEL, 'revision': REVISION, 'served_model_name': MODEL,
                 'model_config_sha256': '08d31c499953794bcf83669497c69c856160927ce29c7df037b8ae315f4f5bdd',
                 'moe_runner': 'marlin', 'lora_targets': None, 'hicache': True},
    # NVIDIA's NVFP4 export keeps attention, shared experts and the router in BF16 and
    # quantizes routed experts W4A4. Adapters train on the BF16 base (LORA_BASE_MODEL_REVISION).
    'z-ai/glm-5.3-flash': {'model': 'nvidia/GLM-5.3-Flash-NVFP4', 'revision': '1d00738646cbb0c6d0a9eb403dac5f366f1473a7',
                           'served_model_name': 'zai-org/GLM-5.3-Flash', 'model_config_sha256': None,
                           'moe_runner': 'flashinfer_trtllm',
                           # SGLang's LoRA wrappers shard by the global TP, so attention context
                           # parallelism (attention TP 1) breaks the linear-attention o_proj adapter.
                           'profile_overrides': {'context_parallel': False},
                           'lora_targets': ['q_proj', 'k_proj', 'v_proj', 'o_proj', 'q_a_proj', 'q_b_proj',
                                            'kv_a_proj_with_mqa', 'kv_b_proj']},
}
SGLANG_SOURCE = 'f171859219b54e1dad45dda60028034490836974'
SMG_VERSION = '1.13.0'
ACTIVE_REQUESTS = 12
QUEUED_REQUESTS = 2
QUEUE_TIMEOUT_SECONDS = 10
# A replica is limited to 400 GiB RAM; 2 x 48 GB pinned plus ~25 GiB RSS per rank leaves room for weight page cache.
HICACHE_HOST_GB_PER_RANK = 48
# Request-derived pages must stay in memory (data-retention policy), so the file tier is tmpfs, charged
# to the replica's 400 GiB limit: 2 x 50G per replica; writes stop below 30G free in /dev/shm.
HICACHE_FILE_CONFIG = {'max_size': '50G', 'min_free_space': '30G'}
HICACHE_ROOT = Path('/dev/shm/gradiated-hicache')
HICACHE_IDLE_SECONDS = 3600
# The host agent runs replicas on the host's /dev/shm (~half its RAM); a smaller one gets no file tier.
HICACHE_MIN_TMPFS_BYTES = 64 << 30
BUNDLE_ROOT = Path(__file__).resolve().parents[1]
PROFILES = {
    'b300-pcp2': {'gpu_product': 'B300', 'active_requests': ACTIVE_REQUESTS,
                  # HiCache also needs the model to opt in; it is unqualified with LoRA.
                  'prefill_tokens': 16384, 'dsa_backend': 'trtllm', 'context_parallel': True, 'hicache': True},
    # Same Blackwell kernels as B300 with about two thirds of the HBM, so half the active requests.
    'b200-pcp2': {'gpu_product': 'B200', 'active_requests': 6,
                  'prefill_tokens': 16384, 'dsa_backend': 'trtllm', 'context_parallel': True},
    'h200-tp2': {'gpu_product': 'H200', 'active_requests': 3,
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
    model_id = environment.get('MODEL_ID', UNCENSORED)
    if model_id not in MODELS:
        raise ValueError('Unknown GLM SGLang model')
    model = MODELS[model_id]
    lora = environment.get('LORA_ENABLED', 'false')
    if lora not in {'true', 'false'} or (lora == 'true' and not model['lora_targets']):
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
            'profile': profile, **PROFILES[profile], **model.get('profile_overrides', {}),
            'model_id': model_id, 'lora': lora == 'true',
            'hicache': bool(PROFILES[profile].get('hicache') and model.get('hicache')) and lora != 'true',
            **{key: model[key] for key in ('model', 'revision', 'served_model_name', 'moe_runner')}}


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


def lora_arguments(environment, targets):
    # The adapter package ships beside this runtime in the bundle and in the repository.
    import sys
    for candidate in [Path(__file__).resolve().parents[1] / 'lora', Path(__file__).resolve().parents[2] / 'lora']:
        if (candidate / 'adapter_service.py').is_file() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
    from adapter_service import engine_arguments, engine_settings
    settings = engine_settings(environment, '', int(environment.get('TENSOR_PARALLEL_SIZE', '2')), {})
    return engine_arguments(settings, targets)




def qualification_identity(config, bundle_root=BUNDLE_ROOT):
    """What a recorded qualification must match beyond the GPUs, or None outside a verified bundle."""
    try:
        digest = (bundle_root / '.bundle-sha256').read_text().strip()
    except OSError:
        return None
    if not re.fullmatch(r'[0-9a-f]{64}', digest):
        return None
    # Ports and the bundle path vary between pods on one host and do not change what qualified.
    placement = {'root', 'front', 'warmup', 'backend', 'metrics'}
    return {'bundle': digest, 'config': {name: value for name, value in config.items() if name not in placement}}


def cache_root(environment):
    base = Path(environment.get('XDG_CACHE_HOME') or str(Path(environment.get('HOME', '/home/runtime')) / '.cache'))
    # Bundles that reuse this runtime keep their caches under their own runtime directory name.
    return base / Path(__file__).resolve().parent.name


def hicache_directory(environment, config, bundle_root=BUNDLE_ROOT):
    identity = qualification_identity(config, bundle_root)
    root = hicache_root(environment)
    if identity is None or not tmpfs_large_enough(root):
        return None
    # File pages carry no dtype or layout, so only one bundle and config may read a directory.
    digest = hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    base = Path(environment.get('GRADIATED_HICACHE_ROOT', str(HICACHE_ROOT))).parent
    if not private_tmpfs_tree(base, root / digest):
        return None
    return root / digest / '_'.join(environment['NVIDIA_VISIBLE_DEVICES'].split(','))


def private_tmpfs_tree(base, path):
    """Create path below base one level at a time; refuse links, other owners or other devices."""
    try:
        device = os.stat(base).st_dev
    except OSError:
        return False
    current = base
    for part in path.relative_to(base).parts:
        current = current / part
        try:
            os.mkdir(current, 0o700)
        except FileExistsError:
            pass
        except OSError:
            return False
        try:
            status = os.lstat(current)
        except OSError:
            return False
        # /dev/shm is world-writable: a pre-created link could send request pages to disk.
        if (not stat.S_ISDIR(status.st_mode) or status.st_uid != os.getuid()
                or status.st_dev != device or status.st_mode & 0o077):
            return False
    return True


def tmpfs_large_enough(root, mounts=Path('/proc/self/mounts')):
    """True only when root sits on a tmpfs of at least HICACHE_MIN_TMPFS_BYTES; pages must never reach disk."""
    try:
        entries = [line.split()[1:3] for line in mounts.read_text().splitlines()]
    except OSError:
        return False
    path = str(root)
    covering = [(point, kind) for point, kind in entries
                if path == point or path.startswith(point.rstrip('/') + '/')]
    if not covering or max(covering, key=lambda item: len(item[0]))[1] != 'tmpfs':
        return False
    point = max(covering, key=lambda item: len(item[0]))[0]
    try:
        return shutil.disk_usage(point).total >= HICACHE_MIN_TMPFS_BYTES
    except OSError:
        return False


def hicache_root(environment):
    # tmpfs survives a process restart on the host but never reaches disk; one tree per runtime directory.
    return Path(environment.get('GRADIATED_HICACHE_ROOT', str(HICACHE_ROOT))) / Path(__file__).resolve().parent.name


def hold_hicache(directory):
    """Hold a shared lock on the leaf's sibling lock file for the life of the service."""
    # hicache_directory created and checked the private tree; never follow a link to the lock.
    descriptor = os.open(directory.with_name(directory.name + '.lock'), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
    handle = os.fdopen(descriptor, 'a')
    fcntl.flock(handle, fcntl.LOCK_SH)
    return handle


def prune_hicache(environment, keep, idle_seconds=HICACHE_IDLE_SECONDS):
    """Delete unlocked leaves of other identities at once and this identity's after idle_seconds."""
    cutoff = time.time() - idle_seconds
    for leaf in hicache_root(environment).glob('*/*'):
        if leaf == keep or not leaf.is_dir():
            continue
        # Another bundle or setting can never read these pages again.
        if leaf.parent != keep.parent:
            cutoff_for_leaf = float('inf')
        else:
            cutoff_for_leaf = cutoff
        try:
            descriptor = os.open(leaf.with_name(leaf.name + '.lock'), os.O_WRONLY | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        except OSError:
            continue
        with os.fdopen(descriptor, 'a') as lock:
            try:
                # A running replica holds its leaf's lock; another start or an evictor may delete files mid-scan.
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                newest = max([leaf.stat().st_mtime, *(f.stat().st_mtime for f in leaf.iterdir())])
            except OSError:
                continue
            if newest < cutoff_for_leaf:
                shutil.rmtree(leaf, ignore_errors=True)


def backend_environment(environment, config):
    # HiCache needs the prompt-end recurrent state on host and disk to serve a hit (live-tested
    # together); '0' keeps an inherited value from switching the overlay on without HiCache.
    return {**environment, 'GRADIATED_MAMBA_PROMPT_END_CHECKPOINT': '1' if config.get('hicache') else '0'}


def commands(environment, bundle_root=BUNDLE_ROOT):
    config = settings(environment)
    root = config['root']
    python = str(root / 'python/bin/python3')
    model = MODELS[config['model_id']]
    overrides = []
    if model['model_config_sha256']:
        model_config = json.loads((root / 'model-config.json').read_text())
        encoded = json.dumps(model_config, sort_keys=True, separators=(',', ':')).encode()
        if hashlib.sha256(encoded).hexdigest() != model['model_config_sha256']:
            raise ValueError('Qualified GLM quantization overrides changed')
        overrides = ['--json-model-override-args', json.dumps(model_config, separators=(',', ':'))]
    backend = [python, str(root / 'energy/launch.py'), '--model-path', config['model'],
               '--revision', config['revision'], '--served-model-name', config['served_model_name'], '--tp-size', '2',
               '--ep-size', '1', '--moe-dense-tp-size', '2', '--quantization', 'modelopt_fp4', *overrides,
               '--moe-runner-backend', config['moe_runner'], '--disable-shared-experts-fusion',
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
    if config.get('hicache'):
        backend += ['--enable-hierarchical-cache', '--hicache-size', str(HICACHE_HOST_GB_PER_RANK),
                    '--hicache-write-policy', 'write_through']
        directory = hicache_directory(environment, config, bundle_root)
        # Without a bundle digest no identity separates file pages, so only the host tier runs.
        if directory is not None:
            backend += ['--hicache-storage-backend', 'file', '--hicache-storage-backend-extra-config',
                        json.dumps({'file_storage_path': str(directory), **HICACHE_FILE_CONFIG}, separators=(',', ':'))]
    if config['lora']:
        backend += lora_arguments(environment, model['lora_targets'])
    router = [python, '-m', 'smg.launch_router', '--worker-urls',
              f"http://127.0.0.1:{config['backend']}", '--policy', 'round_robin',
              '--host', '127.0.0.1', '--port', str(config['front']),
              '--prometheus-host', '127.0.0.1', '--prometheus-port', str(config['metrics']),
              '--max-concurrent-requests', str(config['active_requests']), '--queue-size', str(QUEUED_REQUESTS),
              '--queue-timeout-secs', str(QUEUE_TIMEOUT_SECONDS),
              '--rate-limit-tokens-per-second', '0', '--request-timeout-secs', '900',
              '--worker-startup-timeout-secs', '1200', '--disable-retries']
    return config, backend, router
