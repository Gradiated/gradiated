#!/usr/bin/env python3
"""Reserve the explicitly authorized two-B300 GLM host through normal pod eviction."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

_spec = importlib.util.spec_from_file_location('qualification_slot', Path(__file__).with_name('qualification-slot.py'))
slot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(slot)

NODE = 'gpu-01a19170-d2a0-74ca-b317-d87d69988e4b'
NAMESPACE = 'gpu-inference'
APP = 'glm-dealign'
MODEL = 'dealignai/glm-5.3-flash-uncensored'
IMAGE = 'gradiated/glm-bundle@sha256:b93c18df2a1c88f98a79140c8354ec57e3c975fba99582890941607ce526870b'
REQUIRED = {'cpu': 32, 'memory': 400 * 1024**3, 'nvidia.com/gpu': 2}


def ready(resource, condition='Ready'):
    return any(item['type'] == condition and item['status'] == 'True'
               for item in resource.get('status', {}).get('conditions', []))


def live(pod):
    return pod.get('status', {}).get('phase') not in ('Succeeded', 'Failed')


def qualified(pod, pod_hash):
    metadata = pod['metadata']
    annotations = metadata.get('annotations', {})
    containers = pod.get('spec', {}).get('containers', [])
    statuses = pod.get('status', {}).get('containerStatuses', [])
    try:
        release = json.loads(annotations.get('gradiated.com/release', '{}'))
    except (TypeError, ValueError):
        return False
    if not isinstance(release, dict):
        return False
    return (metadata.get('namespace') == NAMESPACE and not metadata.get('deletionTimestamp')
            and pod.get('status', {}).get('phase') == 'Running'
            and metadata.get('labels', {}).get('app.kubernetes.io/name') == APP
            and metadata.get('labels', {}).get('rollouts-pod-template-hash') == pod_hash
            and annotations.get('gradiated.com/model-id') == MODEL
            and annotations.get('gradiated.com/qualified') == 'true'
            and release.get('runtime_revision') == 'glm-dealign-b93c18df2a1c'
            and release.get('model_revision') == '745aac2ff0f10acf961f396df3f9418598aa7327'
            and any(owner.get('controller') is True and owner.get('kind') == 'ReplicaSet'
                    and owner.get('name') == APP + '-' + pod_hash
                    for owner in metadata.get('ownerReferences', []))
            and len(containers) == len(statuses) == 1
            and containers[0].get('name') == 'runtime' and containers[0].get('image') == IMAGE
            and statuses[0].get('image') == IMAGE and statuses[0].get('ready') is True
            and bool(statuses[0].get('containerID'))
            and annotations.get('gradiated.com/qualified-runtime') == statuses[0]['containerID']
            and ready(pod) and ready(pod, 'RuntimeReady'))


def rollout_identity(rollout, initial=False):
    metadata, status = rollout['metadata'], rollout.get('status', {})
    pod_hash = status.get('currentPodHash')
    identity = {'uid': metadata['uid'], 'generation': metadata['generation'], 'hash': pod_hash}
    containers = rollout.get('spec', {}).get('template', {}).get('spec', {}).get('containers', [])
    if (metadata.get('name') != APP or metadata.get('namespace') != NAMESPACE
            or rollout.get('spec', {}).get('replicas') != 10 or rollout.get('spec', {}).get('paused')
            or status.get('pauseConditions') or status.get('abort')
            or str(status.get('observedGeneration')) != str(metadata['generation'])
            or not pod_hash or status.get('stableRS') != pod_hash
            or len(containers) != 1 or containers[0].get('image') != IMAGE):
        raise ValueError('The GLM rollout is changing or does not match the authorized release')
    if initial and (status.get('phase') != 'Healthy' or any(
            status.get(key) != 10 for key in ('availableReplicas', 'readyReplicas', 'updatedReplicas'))):
        raise ValueError('The GLM rollout must initially be Healthy with ten available replicas')
    return identity


def budget_identity(budget, expected_uid=None, require_disruption=False):
    if not isinstance(budget, dict):
        raise ValueError('The live GLM disruption budget is missing')
    metadata, spec, status = (budget.get(key, {}) for key in ('metadata', 'spec', 'status'))
    if not all(isinstance(value, dict) for value in (metadata, spec, status)):
        raise ValueError('The live GLM disruption budget is malformed')
    selector = {'matchLabels': {'app.kubernetes.io/name': APP}}
    generation = metadata.get('generation')
    if (budget.get('apiVersion') != 'policy/v1' or budget.get('kind') != 'PodDisruptionBudget'
            or metadata.get('name') != APP or metadata.get('namespace') != NAMESPACE
            or not isinstance(metadata.get('uid'), str) or not metadata['uid']
            or metadata.get('deletionTimestamp')
            or type(spec.get('minAvailable')) is not int or spec['minAvailable'] != 8
            or 'maxUnavailable' in spec or spec.get('selector') != selector):
        raise ValueError('The live GLM disruption budget must select exactly GLM with minAvailable 8')
    if expected_uid is not None and metadata['uid'] != expected_uid:
        raise ValueError('The GLM disruption budget UID changed after reservation')
    if (type(generation) is not int or generation < 1
            or type(status.get('observedGeneration')) is not int
            or status['observedGeneration'] != generation):
        raise ValueError('The GLM disruption budget status is stale or unobserved')
    allowed = status.get('disruptionsAllowed')
    if type(allowed) is not int or allowed < 0:
        raise ValueError('The GLM disruption budget status is not ready')
    if require_disruption and allowed == 0:
        raise ValueError('The GLM disruption budget permits no further eviction')
    return {'name': APP, 'namespace': NAMESPACE, 'uid': metadata['uid'],
            'minAvailable': 8, 'selector': selector}


def validate(node, pods, rollout, lease=None, evicted=()):
    metadata = node['metadata']
    annotations = metadata.get('annotations', {})
    labels = metadata.get('labels', {})
    if (metadata.get('name') != NODE or not ready(node)
            or labels.get('nvidia.com/gpu.product') != 'B300'
            or labels.get('gradiated.com/provider') != 'runpod'):
        raise ValueError('Only the authorized Ready two-B300 host may be reserved')
    if slot.FLEET in annotations:
        raise ValueError('The fleet operator owns the node cordon')
    if lease is None:
        if node.get('spec', {}).get('unschedulable') or slot.OWNER in annotations:
            raise ValueError('The host is already cordoned or reserved')
    elif (metadata['uid'] != lease['uid'] or annotations.get(slot.OWNER) != lease['owner']
          or not node.get('spec', {}).get('unschedulable')):
        raise ValueError('Reservation ownership changed')
    available = {key: slot.quantity(node['status']['allocatable'].get(key, 0)) for key in REQUIRED}
    if available['nvidia.com/gpu'] != 2 or any(available[key] < value for key, value in REQUIRED.items()):
        raise ValueError('The host does not provide two GPUs, 32 CPU and 400 GiB')
    identity = rollout_identity(rollout, initial=lease is None)
    if lease and identity != lease['rollout']:
        raise ValueError('The GLM rollout changed after reservation')
    target = [pod for pod in pods if pod.get('spec', {}).get('nodeName') == NODE
              and (live(pod) or lease and pod['metadata']['uid'] in lease['pods'])]
    if lease is None:
        if len(target) != 2:
            raise ValueError('Expected exactly two production GLM pods on the target host')
        expected = {pod['metadata']['uid']: pod['metadata']['name'] for pod in target}
    else:
        expected = lease['pods']
    present = set()
    for pod in target:
        uid, name = pod['metadata']['uid'], pod['metadata']['name']
        if expected.get(uid) != name:
            raise ValueError('A foreign pod or replacement UID appeared on the host')
        present.add(uid)
        if uid not in evicted and not qualified(pod, identity['hash']):
            raise ValueError('A target pod is not the qualified production runtime')
    if set(expected) - present - set(evicted):
        raise ValueError('A target pod disappeared before its UID-fenced eviction')
    others = [pod for pod in pods if pod.get('spec', {}).get('nodeName') != NODE
              and qualified(pod, identity['hash'])]
    if len(others) < 8:
        raise ValueError('Fewer than eight other qualified GLM replicas are Ready')
    return expected, identity, target


class Client:
    def __init__(self, deadline, clock=time.monotonic):
        self.deadline = deadline
        self.clock = clock

    def run(self, arguments, payload=None):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError('Host drain deadline exceeded')
        result = subprocess.run(['kubectl', '--request-timeout=20s', *arguments],
                                input=json.dumps(payload) if payload is not None else None,
                                capture_output=True, text=True, check=True, timeout=min(30, remaining))
        return json.loads(result.stdout) if result.stdout.strip() else None

    def snapshot(self):
        return (self.run(['get', 'node', NODE, '-o', 'json']),
                self.run(['get', 'pods', '-A', '-o', 'json'])['items'],
                self.run(['get', 'rollout', APP, '-n', NAMESPACE, '-o', 'json']))

    def budget(self):
        return self.run(['get', 'poddisruptionbudget', APP, '-n', NAMESPACE, '-o', 'json'])

    def evict(self, name, uid):
        payload = {'apiVersion': 'policy/v1', 'kind': 'Eviction',
                   'metadata': {'name': name, 'namespace': NAMESPACE},
                   'deleteOptions': {'preconditions': {'uid': uid}}}
        return self.run(['create', '--raw',
                         f'/api/v1/namespaces/{NAMESPACE}/pods/{name}/eviction', '-f', '-'], payload)


def reserve(path, *, apply=False, client=None, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 900
    client = client or Client(deadline, clock)
    node, pods, rollout = client.snapshot()
    expected, identity, _ = validate(node, pods, rollout)
    budget = budget_identity(client.budget())
    plan = {'node': NODE, 'uid': node['metadata']['uid'], 'pods': expected,
            'rollout': identity, 'budget': budget, 'provider_changes': False, 'apply': apply}
    if not apply:
        return plan
    lease = {**plan, 'owner': str(uuid.uuid4())}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as output:
        os.chmod(path, 0o600)
        json.dump(lease, output)
        output.flush()
        os.fsync(output.fileno())
    evicted = set()
    cordon_attempted = False
    try:
        budget_identity(client.budget(), budget['uid'], require_disruption=True)
        cordon_attempted = True
        slot.patch(node, [
            {'op': 'add', 'path': '/metadata/annotations', 'value': {
                **node['metadata'].get('annotations', {}), slot.OWNER: lease['owner']}},
            {'op': 'add', 'path': '/spec/unschedulable', 'value': True}])
        settled_at = clock() + 30
        while True:
            node, pods, rollout = client.snapshot()
            validate(node, pods, rollout, lease)
            budget_identity(client.budget(), budget['uid'])
            rollout_identity(rollout, initial=True)
            if clock() >= settled_at:
                break
            if clock() >= deadline:
                raise TimeoutError('Host drain deadline exceeded')
            sleep(min(5, settled_at - clock(), deadline - clock()))
        for uid, name in expected.items():
            node, pods, rollout = client.snapshot()
            validate(node, pods, rollout, lease, evicted)
            budget_identity(client.budget(), budget['uid'], require_disruption=True)
            client.evict(name, uid)
            evicted.add(uid)
        while True:
            node, pods, rollout = client.snapshot()
            _, _, target = validate(node, pods, rollout, lease, evicted)
            budget_identity(client.budget(), budget['uid'])
            if not target:
                remaining = slot.check_capacity(node, pods)
                if any(remaining[key] < value for key, value in REQUIRED.items()):
                    raise ValueError('Drained host has insufficient free experiment capacity')
                return lease
            if clock() >= deadline:
                raise TimeoutError('Host drain deadline exceeded; normal pod grace periods were preserved')
            sleep(min(5, deadline - clock()))
    except Exception as error:
        if not cordon_attempted:
            path.unlink()
            raise
        try:
            slot.release(lease)
        except Exception as release_error:
            raise RuntimeError(f'{error}; reservation release failed; preserve {path}: {release_error}') from error
        path.unlink()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--lease', type=Path)
    args = parser.parse_args()
    if args.apply and args.lease is None:
        parser.error('--apply requires an explicit --lease path for recovery')
    print(json.dumps(reserve(args.lease, apply=args.apply)))


if __name__ == '__main__':
    main()
