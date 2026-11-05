#!/usr/bin/env python3
import argparse
import copy
import hashlib
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
    'h200': {'product': 'H200', 'profile': 'h200-tp2', 'memory_gib': 320, 'active_requests': 4},
    'b200': {'product': 'B200', 'profile': 'b200-pcp2', 'memory_gib': 320, 'active_requests': 8},
}


def name(gpu):
    return f'glm-dealign-sglang-{gpu}'


def stage(models, runtimes, pins, hosts, release, source, instances, replicas=1, promote=False, *, gpu):
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
    primary = models.get('glm-dealign', {})
    if runtimes.get(primary.get('runtime'), {}).get('model_id') != MODEL:
        raise ValueError('Existing primary must serve the exact uncensored model')
    if not instances or len(set(instances)) != len(instances) or type(replicas) is not int or not 1 <= replicas <= len(instances):
        raise ValueError('Choose unique enrolled instances and one replica per available pair')
    inventory = {host['spec']['instanceId']: host['spec'] for host in hosts if host}
    for instance in instances:
        if str(uuid.UUID(instance)) != instance or instance not in inventory:
            raise ValueError('Every instance must have committed GpuHost inventory')
        host = inventory[instance]
        capacity = host['inventory']
        if (host['provider']['name'] != 'runpod' or capacity['gpuProduct'] != product
                or capacity['gpuCount'] != 2 or capacity['cpu'] < 32 or capacity['memoryGiB'] < memory):
            raise ValueError(f'{product} profile requires an enrolled RunPod pair with 32 CPU and {memory} GiB allocatable RAM')

    runtime_id = hashlib.sha256(f'{digest}:{profile}'.encode()).hexdigest()
    runtime = {
        # Host agents reject a catalogue whose image digest differs from its runtime key.
        'image': f'gradiated/glm-sglang-bundle@sha256:{runtime_id}',
        'bundles': {release['baseId']: digest}, 'model_id': f'{MODEL}-sglang-{gpu}',
        'release': {'schema_version': 1, 'model_path': CHECKPOINT, 'model_revision': REVISION,
                    'tokenizer_path': CHECKPOINT, 'tokenizer_revision': REVISION,
                    'runtime_revision': f'glm-{gpu}-{digest[:12]}', 'runtime_model_name': CHECKPOINT},
        'gpus': 2, 'cpu': '32', 'memory': f'{memory}Gi', 'startup_timeout': 3600, 'warmup': True,
        'environment': {'TENSOR_PARALLEL_SIZE': '2', 'GLM_SGLANG_PROFILE': profile},
    }
    candidate = {
        'runtime': runtime_id, 'replicas': replicas, 'min_available': max(1, replicas - 1),
        'canary_for': 'glm-dealign', 'serving_model_id': MODEL,
        'serving_mode': 'production' if promote else 'qualification',
        'progress_deadline_seconds': 5400, 'max_surge': 0, 'max_unavailable': 1,
        'node_selector': {'gradiated.com/provider': 'runpod', 'nvidia.com/gpu.product': product},
        'affinity': {'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {
            'nodeSelectorTerms': [{'matchExpressions': [{'key': 'gradiated.com/instance-id',
                                                         'operator': 'In', 'values': sorted(instances)}]}]}}},
        'autoscaling': {'max_replicas': replicas, 'target_concurrency': pool['active_requests']},
    }
    existing = models.get(name(gpu))
    isolated = {**candidate, 'serving_mode': 'qualification'}
    if promote and (existing not in [isolated, candidate] or runtimes.get(runtime_id) != runtime):
        raise ValueError(f'Promotion requires the exact previously staged {product} deployment and immutable runtime')
    if existing is not None and existing not in [isolated, candidate]:
        raise ValueError(f'Existing {product} deployment differs; review scaling, rollback or replacement explicitly')
    if runtime_id in runtimes and runtimes[runtime_id] != runtime:
        raise ValueError('Runtime identity already has a different immutable definition')
    return {**copy.deepcopy(models), name(gpu): candidate}, {**copy.deepcopy(runtimes), runtime_id: runtime}


def main():
    parser = argparse.ArgumentParser(description='Stage an isolated non-B300 GLM pool alongside existing B300 GLM pools.')
    parser.add_argument('release', type=Path)
    parser.add_argument('source', help='exact source SHA of the bundle built with the pool\'s launch profile')
    parser.add_argument('--gpu', choices=sorted(POOLS), required=True)
    parser.add_argument('--instances', nargs='+', required=True, help='registered instance UUIDs from hosts.yaml, not RunPod IDs')
    parser.add_argument('--replicas', type=int, default=1)
    parser.add_argument('--promote', action='store_true', help='expose the exact staged pool after GPU and SDK qualification')
    parser.add_argument('--write', action='store_true', help='write catalogs; otherwise print a dry run')
    args = parser.parse_args()
    runtimes_path = ROOT / 'product/inference/gpu/runtimes.json'
    read = lambda path: json.loads(path.read_text())
    models, runtimes = stage(read(GPU / 'models.json'), read(runtimes_path), read(GPU / 'pins.json'),
                              list(yaml.safe_load_all((GPU / 'hosts.yaml').read_text())), read(args.release),
                              args.source, args.instances, args.replicas, args.promote, gpu=args.gpu)
    if args.write:
        runtimes_path.write_text(json.dumps(runtimes, indent=2) + '\n')
        (GPU / 'models.json').write_text(json.dumps(models, indent=2) + '\n')
    model = models[name(args.gpu)]
    print(json.dumps({'write': args.write, 'model': model, 'runtime': runtimes[model['runtime']],
                      'next': 'python3 tools/gpu/render-config.py && node tools/models/model-replica-rules.mjs; review and commit'}, indent=2))


if __name__ == '__main__':
    main()
