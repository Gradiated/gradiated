#!/usr/bin/env python3
import argparse
import copy
import json
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[2]
GPU = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference'
MODEL = 'moonshotai/kimi-k3.1-pro'
CHECKPOINT = 'moonshotai/Kimi-K3.1-Pro'
REVISION = 'd9e99b0792a5e93b78ea9bea62a68167e36ddd9e'
INSTANCES = {'01a0fbf8-06fc-7658-96e1-ae72f7dba135'}
BUCKET = 'gradiated-prod-model-artifacts-873716897517'
ACTIVE_REQUESTS = 4


def stage(models, runtimes, pins, hosts, release, source):
    if not re.fullmatch(r'[0-9a-f]{40}', source) or release.get('source') != source:
        raise ValueError('Release must match the qualified source revision')
    digest = release.get('sha256', '')
    if release.get('bundle') != 'kimi-k31-pro' or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise ValueError('Expected an immutable Kimi K3.1 Pro runtime release')
    if 'b300-tp8' not in release.get('runtimeProfiles', []):
        raise ValueError('Release must include the qualified eight-B300 launch profile')
    base = pins['hostBundle']['baseId']
    if release.get('baseId') != base or not re.fullmatch(r'.+@sha256:[0-9a-f]{64}', release.get('baseImage', '')):
        raise ValueError('Release must support the pinned GPU base')
    if release.get('url') != f's3::https://{BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz':
        raise ValueError('Archive path must match the release digest')
    inventory = {item['spec']['instanceId']: item['spec'] for item in hosts if item}
    for instance in sorted(INSTANCES):
        host = inventory.get(instance, {})
        capacity = host.get('inventory', {})
        if (host.get('provider', {}).get('name') != 'runpod' or capacity.get('gpuProduct') != 'B300'
                or capacity.get('gpuCount') != 8 or capacity.get('cpu', 0) < 80
                or capacity.get('memoryGiB', 0) < 1024):
            raise ValueError('The Kimi host needs committed 8xB300, 80 CPU and 1024 GiB inventory')
    runtime = {
        'image': f'gradiated/kimi-k31-bundle@sha256:{digest}',
        'bundles': {base: digest}, 'model_id': MODEL,
        'release': {'schema_version': 1, 'model_path': CHECKPOINT, 'model_revision': REVISION,
                    'tokenizer_path': CHECKPOINT, 'tokenizer_revision': REVISION,
                    'runtime_revision': f'kimi-k31-{digest[:12]}',
                    'runtime_model_name': CHECKPOINT},
        'gpus': 8, 'cpu': '80', 'memory': '1024Gi', 'active_requests': ACTIVE_REQUESTS,
        'hf_home': '/var/lib/kimi-k31/hf', 'startup_timeout': 7200, 'warmup': True,
        'environment': {'TENSOR_PARALLEL_SIZE': '8'},
    }
    candidate = {
        'runtime': digest, 'replicas': 1, 'min_available': 1,
        'progress_deadline_seconds': 10800, 'max_surge': 0, 'max_unavailable': 1,
        'allow_single_replica_unavailable': True,
        'node_selector': {'gradiated.com/provider': 'runpod', 'nvidia.com/gpu.product': 'B300',
                          'nvidia.com/gpu.count': '8'},
        'extra_tolerations': [{'key': 'gradiated.com/kimi-k31', 'operator': 'Equal',
                               'value': 'reserved', 'effect': 'NoSchedule'}],
        'affinity': {'nodeAffinity': {'requiredDuringSchedulingIgnoredDuringExecution': {
            'nodeSelectorTerms': [{'matchExpressions': [{'key': 'gradiated.com/instance-id',
                                                         'operator': 'In', 'values': sorted(INSTANCES)}]}]}}},
        'autoscaling': {'max_replicas': 1, 'target_concurrency': ACTIVE_REQUESTS},
    }
    if 'kimi-k31-pro' in models and models['kimi-k31-pro'] != candidate:
        raise ValueError('Existing Kimi deployment differs; review replacement explicitly')
    if digest in runtimes and runtimes[digest] != runtime:
        raise ValueError('Runtime digest already has another immutable definition')
    return {**copy.deepcopy(models), 'kimi-k31-pro': candidate}, {**copy.deepcopy(runtimes), digest: runtime}


def main():
    parser = argparse.ArgumentParser(description='Stage qualified Kimi on its reserved 8xB300 host.')
    parser.add_argument('release', type=Path)
    parser.add_argument('source', help='exact qualified source revision')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    read = lambda path: json.loads(path.read_text())
    runtimes_path = ROOT / 'product/inference/gpu/runtimes.json'
    models_path = GPU / 'models.json'
    models, runtimes = stage(read(models_path), read(runtimes_path), read(GPU / 'pins.json'),
                             list(yaml.safe_load_all((GPU / 'hosts.yaml').read_text())),
                             read(args.release), args.source)
    if args.write:
        runtimes_path.write_text(json.dumps(runtimes, indent=2) + '\n')
        models_path.write_text(json.dumps(models, indent=2) + '\n')
    model = models['kimi-k31-pro']
    print(json.dumps({'write': args.write, 'model': model, 'runtime': runtimes[model['runtime']]}, indent=2))


if __name__ == '__main__':
    main()
