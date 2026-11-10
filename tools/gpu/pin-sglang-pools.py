#!/usr/bin/env python3
"""Pin GLM-5.3 Flash and DeepSeek V4.1 Flash 1017 to their published SGLang bundles.

Takes the release records that Model deployment publishes for the
`glm-5-3-flash-sglang` and `deepseek-v4-1-flash-sglang` bundles (read them with
`node tools/models/release.mjs resolve <bundle> <source> <bucket> <account>`), adds
one immutable runtime per model to runtimes.json and points each model's pool at
it in models.json. The previous vLLM runtimes stay in runtimes.json for rollback.

    python3 tools/gpu/pin-sglang-pools.py glm-release.json deepseek-release.json <source> --write
    python3 tools/gpu/render-config.py
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
GPU = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference'
RUNTIMES = ROOT / 'product/inference/gpu/runtimes.json'
BUCKET = 'gradiated-prod-model-artifacts-873716897517'
LORA_ENVIRONMENT = {
    'LORA_ENABLED': 'true', 'LORA_GPU_SLOTS': '8', 'LORA_CPU_SLOTS': '64', 'LORA_MAX_RANK': '8',
    'LORA_DISK_CACHE_BYTES': '274877906944',
    'LORA_DOWNLOAD_HOSTS': f'{BUCKET}.s3.us-east-1.amazonaws.com',
    'GRADIATED_API_BASE_URL': 'http://127.0.0.1:3004',
}


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def models():
    glm = load('glm_sglang_config', ROOT / 'product/inference/runtimes/glm-sglang/config.py')
    deepseek = load('deepseek_sglang_config', ROOT / 'product/inference/runtimes/deepseek-sglang/config.py')
    plain = glm.MODELS['z-ai/glm-5.3-flash']
    return {
        'z-ai/glm-5.3-flash': {
            'bundle': 'glm-5-3-flash-sglang', 'profile': 'b300-pcp2', 'pool': 'glm',
            'image': 'gradiated/glm-sglang-bundle', 'revision_prefix': 'glm-sglang',
            'checkpoint': plain['model'], 'revision': plain['revision'], 'served': plain['served_model_name'],
            'active_requests': glm.PROFILES['b300-pcp2']['active_requests'], 'gpus': 2,
            # Adapters train on the BF16 base; the NVFP4 serving export keeps attention in BF16.
            'lora_base_revision': 'a5b45eb41df6402735dedc900be14a42e8d5e538',
            'resources': {'cpu': '32', 'memory': '400Gi', 'startup_timeout': 3600},
            'environment': {'TENSOR_PARALLEL_SIZE': '2', 'MODEL_ID': 'z-ai/glm-5.3-flash'},
        },
        deepseek.MODEL_ID: {
            'bundle': 'deepseek-v4-1-flash-sglang', 'profile': 'b300-tp4', 'pool': 'deepseek',
            'image': 'gradiated/deepseek-sglang-bundle', 'revision_prefix': 'deepseek-sglang',
            'checkpoint': deepseek.MODEL, 'revision': deepseek.REVISION, 'served': deepseek.MODEL,
            'active_requests': deepseek.PROFILES['b300-tp4']['active_requests'], 'gpus': 4,
            'lora_base_revision': deepseek.REVISION,
            # The checkpoint ships no Hugging Face chat template; the gateway's pinned
            # DeepSeek V4.1 encoder counts tokens for it (SGLang still renders requests).
            'tokenizer_mode': 'deepseek_v41',
            'resources': {'cpu': '32', 'memory': '400Gi', 'startup_timeout': 5400},
            'environment': {'TENSOR_PARALLEL_SIZE': '4', 'MODEL_ID': deepseek.MODEL_ID},
        },
    }


LAUNCHERS = ['product/inference/runtimes/glm-sglang/config.py', 'product/inference/runtimes/deepseek-sglang/config.py']


def check_source(source, root=ROOT):
    """The pinned metadata comes from this checkout, so it must match the bundles' source."""
    if not re.fullmatch('[0-9a-f]{40}', source):
        raise ValueError('Source must be a full commit SHA')
    changed = subprocess.run(['git', 'diff', '--quiet', source, '--', *LAUNCHERS], cwd=root)
    if changed.returncode != 0:
        raise ValueError('Launcher configs differ from the bundles\' source revision; check out that revision first')


def runtime_for(model_id, spec, release, source, base_id):
    if not re.fullmatch('[0-9a-f]{40}', source) or release.get('source') != source:
        raise ValueError('Release must match the explicitly selected source revision')
    digest = release.get('sha256', '')
    if release.get('bundle') != spec['bundle'] or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError(f'Expected an immutable {spec["bundle"]} release')
    if spec['profile'] not in release.get('runtimeProfiles', []):
        raise ValueError(f'Release does not include the {spec["profile"]} launch profile')
    if release.get('baseId') != base_id or not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', release.get('baseImage', '')):
        raise ValueError('Release must support the pinned host base')
    if release.get('url') != f's3::https://{BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz':
        raise ValueError('Release archive path does not match its digest')
    runtime_id = hashlib.sha256(f'{digest}:{model_id}:{spec["profile"]}'.encode()).hexdigest()
    runtime = {
        # Host agents reject a catalogue whose image digest differs from its runtime key.
        'image': f'{spec["image"]}@sha256:{runtime_id}',
        'bundles': {base_id: digest}, 'model_id': model_id,
        'release': {'schema_version': 1, 'model_path': spec['checkpoint'], 'model_revision': spec['revision'],
                    'tokenizer_path': spec['checkpoint'], 'tokenizer_revision': spec['revision'],
                    'runtime_revision': f'{spec["revision_prefix"]}-{digest[:12]}',
                    'runtime_model_name': spec['served'], 'lora_enabled': True,
                    'lora_base_model_revision': spec['lora_base_revision'],
                    **({'tokenizer_mode': spec['tokenizer_mode']} if 'tokenizer_mode' in spec else {})},
        'gpus': spec['gpus'], 'active_requests': spec['active_requests'],
        'cpu': spec['resources']['cpu'], 'memory': spec['resources']['memory'],
        'startup_timeout': spec['resources']['startup_timeout'], 'warmup': True, 'adapters': True,
        'environment': {**spec['environment'], **LORA_ENVIRONMENT,
                        'LORA_BASE_MODEL_REVISION': spec['lora_base_revision']},
    }
    return runtime_id, runtime


def pin(model_catalog, runtimes, pins, releases, source, max_replicas=1):
    """Return updated (models, runtimes) with each model's pool on its SGLang runtime."""
    if type(max_replicas) is not int or max_replicas < 0:
        raise ValueError('max_replicas must be a non-negative integer')
    updated_models, updated_runtimes = copy.deepcopy(model_catalog), copy.deepcopy(runtimes)
    base_id = pins['hostBundle']['baseId']
    retired = 'deepseek/deepseek-v4.1-flash'
    for model_id, spec in models().items():
        runtime_id, runtime = runtime_for(model_id, spec, releases[spec['bundle']], source, base_id)
        if runtime_id in runtimes and runtimes[runtime_id] != runtime:
            raise ValueError('Runtime identity already has a different immutable definition')
        updated_runtimes[runtime_id] = runtime
        # The DeepSeek pool moves from the retired public ID to the 1017 model, which the
        # gateway then serves locally; the old ID falls back to OpenRouter.
        source_model = retired if model_id not in updated_models and retired in updated_models else model_id
        entry = updated_models.pop(source_model, None) or {'min_slots': 0, 'pools': {}}
        if source_model != model_id and set(entry['pools']) - {spec['pool']}:
            # Other pools of the retired model would serve its old checkpoint under the new ID.
            raise ValueError(f'Retire or migrate the other {source_model} pools before pinning {model_id}')
        pool = {'runtime': runtime_id, 'gpu': 'B300', 'max_replicas': max_replicas,
                'progress_deadline_seconds': 5400}
        previous = entry['pools'].get(spec['pool'], {})
        if 'spread' in previous:
            pool['spread'] = previous['spread']
        # Only the model's SGLang pool changes; any other pool it has keeps its definition.
        pinned = {'min_slots': entry['min_slots'], 'pools': {**entry['pools'], spec['pool']: pool}}
        # Keep the catalogue order, so a renamed model stays where its predecessor was.
        order = list(model_catalog)
        position = order.index(source_model) if source_model in order else len(order)
        items = [(key, value) for key, value in updated_models.items() if key != model_id]
        before = [item for item in items if item[0] in order[:position]]
        after = [item for item in items if item not in before]
        updated_models = dict(before + [(model_id, pinned)] + after)
    return updated_models, updated_runtimes


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('glm_release', type=Path)
    parser.add_argument('deepseek_release', type=Path)
    parser.add_argument('source', help='the merge commit Model deployment built both bundles from')
    parser.add_argument('--max-replicas', type=int, default=1)
    parser.add_argument('--write', action='store_true', help='write the catalogues; otherwise print a dry run')
    args = parser.parse_args()
    check_source(args.source)
    read = lambda path: json.loads(path.read_text())
    releases = {}
    for path in (args.glm_release, args.deepseek_release):
        release = read(path)
        releases[release.get('bundle')] = release
    updated_models, updated_runtimes = pin(read(GPU / 'models.json'), read(RUNTIMES), read(GPU / 'pins.json'),
                                           releases, args.source, args.max_replicas)
    if args.write:
        RUNTIMES.write_text(json.dumps(updated_runtimes, indent=2) + '\n')
        (GPU / 'models.json').write_text(json.dumps(updated_models, indent=2) + '\n')
    print(json.dumps({'write': args.write, 'models': {model: updated_models[model] for model in models()},
                      'next': 'python3 tools/gpu/render-config.py; review and commit'}, indent=2))


if __name__ == '__main__':
    main()
