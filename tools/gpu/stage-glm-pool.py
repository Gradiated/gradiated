#!/usr/bin/env python3
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
GPU = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference'
MODEL = 'dealignai/glm-5.3-flash-uncensored'
CHECKPOINT = 'dealignai/GLM-5.3-Flash-UNCENSORED-NVFP4'
REVISION = '745aac2ff0f10acf961f396df3f9418598aa7327'
BUCKET = 'gradiated-prod-model-artifacts-873716897517'
POOLS = {
    'h200': {'product': 'H200', 'profile': 'h200-tp2', 'memory_gib': 320},
    'b200': {'product': 'B200', 'profile': 'b200-pcp2', 'memory_gib': 320},
}


def launcher_profiles():
    spec = importlib.util.spec_from_file_location('render_config', Path(__file__).with_name('render-config.py'))
    render = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(render)
    return render.glm_sglang_profiles()


def name(gpu):
    return f'glm-dealign-sglang-{gpu}'


def stage(models, runtimes, pins, hosts, release, source, replicas=1, promote=False, *, gpu):
    """Add an uncensored GLM pool in qualification mode, or promote the exact staged pool to production."""
    pool = POOLS[gpu]
    product, profile, memory = pool['product'], pool['profile'], pool['memory_gib']
    if not re.fullmatch('[0-9a-f]{40}', source) or release.get('source') != source:
        raise ValueError('Release must match the explicitly selected source revision')
    digest = release.get('sha256', '')
    if release.get('bundle') != 'glm-5-3-flash-sglang' or not re.fullmatch('[0-9a-f]{64}', digest):
        raise ValueError('Expected an immutable GLM SGLang bundle release')
    if profile not in release.get('runtimeProfiles', []):
        raise ValueError(f'Release does not include the {product} launch profile; build the updated bundle first')
    if release.get('baseId') != pins['hostBundle']['baseId'] or not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', release.get('baseImage', '')):
        raise ValueError('Release must support the pinned host base')
    if release.get('url') != f's3::https://{BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz':
        raise ValueError('Release archive path does not match its digest')
    if MODEL not in models:
        raise ValueError('models.json must already list the uncensored model')
    if type(replicas) is not int or replicas < 1:
        raise ValueError('Stage at least one replica')
    # The scheduler places replicas on any unreserved pair of this GPU type; check enough exist.
    pairs = [host['spec'] for host in hosts if host
             and host['spec']['provider']['name'] == 'runpod'
             and not any(taint['key'] == 'gradiated.com/reserved' for taint in host['spec'].get('extraTaints', []))
             and host['spec']['inventory']['gpuProduct'] == product and host['spec']['inventory']['gpuCount'] == 2
             and host['spec']['inventory']['cpu'] >= 32 and host['spec']['inventory']['memoryGiB'] >= memory]
    if len(pairs) < replicas:
        raise ValueError(f'{product} profile requires {replicas} unreserved RunPod pairs with 32 CPU and '
                         f'{memory} GiB allocatable RAM; hosts.yaml has {len(pairs)}')

    runtime_id = hashlib.sha256(f'{digest}:{profile}'.encode()).hexdigest()
    runtime = {
        # Host agents reject a catalogue whose image digest differs from its runtime key.
        'image': f'gradiated/glm-sglang-bundle@sha256:{runtime_id}',
        'bundles': {release['baseId']: digest}, 'model_id': f'{MODEL}-sglang-{gpu}',
        'release': {'schema_version': 1, 'model_path': CHECKPOINT, 'model_revision': REVISION,
                    'tokenizer_path': CHECKPOINT, 'tokenizer_revision': REVISION,
                    'runtime_revision': f'glm-{gpu}-{digest[:12]}', 'runtime_model_name': CHECKPOINT},
        'gpus': 2, 'active_requests': launcher_profiles()[profile]['active_requests'],
        'cpu': '32', 'memory': f'{memory}Gi', 'startup_timeout': 3600, 'warmup': True,
        # Host agents reject GLM_SGLANG_PROFILE; the runtime selects the profile from the assigned GPUs.
        'environment': {'TENSOR_PARALLEL_SIZE': '2'},
    }
    rollout = {'progress_deadline_seconds': 5400, 'max_surge': 0, 'max_unavailable': 1}
    # Staged: a fixed count, SDK-qualified but never routed. Promoted: the same
    # replicas become the pool's maximum, filled after the pools listed before it.
    staged = {'runtime': runtime_id, 'gpu': product, 'mode': 'qualification', 'replicas': replicas, **rollout}
    production = {'runtime': runtime_id, 'gpu': product, 'max_replicas': replicas, **rollout}
    existing = models[MODEL]['pools'].get(name(gpu))
    if promote and (existing not in [staged, production] or runtimes.get(runtime_id) != runtime):
        raise ValueError(f'Promotion requires the exact previously staged {product} pool and immutable runtime')
    if existing is not None and existing not in [staged, production]:
        raise ValueError(f'Existing {product} pool differs; review scaling, rollback or replacement explicitly')
    if runtime_id in runtimes and runtimes[runtime_id] != runtime:
        raise ValueError('Runtime identity already has a different immutable definition')
    updated = copy.deepcopy(models)
    updated[MODEL]['pools'][name(gpu)] = production if promote else staged
    return updated, {**copy.deepcopy(runtimes), runtime_id: runtime}


def main():
    parser = argparse.ArgumentParser(description='Stage an isolated non-B300 uncensored GLM pool, then promote it.')
    parser.add_argument('release', type=Path)
    parser.add_argument('source', help='exact source SHA of the bundle built with the pool\'s launch profile')
    parser.add_argument('--gpu', choices=sorted(POOLS), required=True)
    parser.add_argument('--replicas', type=int, default=1, help='staged replicas, and the maximum once promoted')
    parser.add_argument('--promote', action='store_true', help='expose the exact staged pool after GPU and SDK qualification')
    parser.add_argument('--write', action='store_true', help='write catalogs; otherwise print a dry run')
    args = parser.parse_args()
    runtimes_path = ROOT / 'product/inference/gpu/runtimes.json'
    read = lambda path: json.loads(path.read_text())
    models, runtimes = stage(read(GPU / 'models.json'), read(runtimes_path), read(GPU / 'pins.json'),
                              list(yaml.safe_load_all((GPU / 'hosts.yaml').read_text())), read(args.release),
                              args.source, args.replicas, args.promote, gpu=args.gpu)
    if args.write:
        runtimes_path.write_text(json.dumps(runtimes, indent=2) + '\n')
        (GPU / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
    pool = models[MODEL]['pools'][name(args.gpu)]
    print(json.dumps({'write': args.write, 'pool': pool, 'runtime': runtimes[pool['runtime']],
                      'next': 'python3 tools/gpu/render-config.py; review and commit'}, indent=2))


if __name__ == '__main__':
    main()
