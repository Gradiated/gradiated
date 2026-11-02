#!/usr/bin/env python3
"""Reserve spare node capacity for isolated GPU qualification without draining pods."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid

OWNER = 'gradiated.com/qualification-slot'
FLEET = 'fleet.gradiated.com/cordoned-by'


def kubectl(*args):
    return json.loads(subprocess.check_output(
        ['kubectl', '--request-timeout=20s', *args, '-o', 'json'],
        text=True, timeout=30))


def quantity(value):
    value = str(value)
    for suffix, multiplier in [('Ki', 1024), ('Mi', 1024**2), ('Gi', 1024**3),
                               ('Ti', 1024**4), ('m', 0.001)]:
        if value.endswith(suffix):
            return float(value[:-len(suffix)]) * multiplier
    return float(value)


def check_capacity(node, pods):
    remaining = {key: quantity(node['status']['allocatable'].get(key, 0))
                 for key in ('cpu', 'memory', 'nvidia.com/gpu')}
    for pod in pods:
        if pod.get('spec', {}).get('nodeName') != node['metadata']['name'] or pod.get('status', {}).get('phase') in ('Succeeded', 'Failed'):
            continue
        for container in pod['spec'].get('containers', []) + pod['spec'].get('initContainers', []):
            for key, value in container.get('resources', {}).get('requests', {}).items():
                if key in remaining:
                    remaining[key] -= quantity(value)
        for key, value in pod['spec'].get('overhead', {}).items():
            if key in remaining:
                remaining[key] -= quantity(value)
    if any(remaining[key] < amount for key, amount in
           {'cpu': 16, 'memory': 224 * 1024**3, 'nvidia.com/gpu': 1}.items()):
        raise ValueError('The node has no spare 1 GPU / 16 CPU / 224 GiB slot')
    return remaining


def patch(node, operations):
    return kubectl('patch', 'node', node['metadata']['name'], '--type=json', '-p', json.dumps([
        {'op': 'test', 'path': '/metadata/resourceVersion', 'value': node['metadata']['resourceVersion']},
        *operations]))


def release(lease):
    node = kubectl('get', 'node', lease['node'])
    if node['metadata']['uid'] != lease['uid']:
        raise ValueError('The node was replaced; preserving its scheduling state')
    annotations = node['metadata'].get('annotations', {})
    if annotations.get(OWNER) != lease['owner'] or FLEET in annotations:
        raise ValueError('Cordon ownership changed; preserving the node cordon')
    annotations = {key: value for key, value in annotations.items() if key != OWNER}
    patch(node, [{'op': 'add', 'path': '/metadata/annotations', 'value': annotations},
                 {'op': 'add', 'path': '/spec/unschedulable', 'value': False}])


def settle(lease, *, clock=time.monotonic, sleep=time.sleep):
    deadline = clock() + 120
    signature = None
    stable_since = clock()
    while clock() < deadline:
        node = kubectl('get', 'node', lease['node'])
        annotations = node['metadata'].get('annotations', {})
        if (node['metadata']['uid'] != lease['uid'] or annotations.get(OWNER) != lease['owner']
                or FLEET in annotations or not node.get('spec', {}).get('unschedulable')):
            raise ValueError('Qualification cordon ownership changed while settling')
        pods = kubectl('get', 'pods', '-A')['items']
        check_capacity(node, pods)
        assigned = [pod for pod in pods if pod.get('spec', {}).get('nodeName') == lease['node']
                    and pod.get('status', {}).get('phase') not in ('Succeeded', 'Failed')]
        current = sorted(json.dumps({'uid': pod['metadata']['uid'],
                         'requests': [c.get('resources', {}).get('requests', {}) for c in
                                      pod['spec'].get('containers', []) + pod['spec'].get('initContainers', [])],
                         'overhead': pod['spec'].get('overhead', {})}, sort_keys=True) for pod in assigned)
        if current != signature:
            signature = current
            stable_since = clock()
        if clock() - stable_since >= 30:
            return
        sleep(5)
    raise TimeoutError('Scheduled demand did not settle within two minutes')


def acquire(name, path):
    if name != 'gpu-' + str(uuid.UUID(name.removeprefix('gpu-'))):
        raise ValueError('Expected a canonical gpu-<instance UUID> node name')
    if name == 'gpu-01a0fbf8-06fc-7658-96e1-ae72f7dba135':
        raise ValueError('This host is reserved for another workstream')
    node = kubectl('get', 'node', name)
    annotations = node['metadata'].get('annotations', {})
    ready = any(c['type'] == 'Ready' and c['status'] == 'True' for c in node['status'].get('conditions', []))
    if not ready or node.get('spec', {}).get('unschedulable') or OWNER in annotations or FLEET in annotations:
        raise ValueError('The node must be Ready, schedulable and unowned')
    check_capacity(node, kubectl('get', 'pods', '-A')['items'])
    lease = {'node': name, 'uid': node['metadata']['uid'], 'owner': str(uuid.uuid4())}
    # Persist recovery information before the external write; never overwrite another lease.
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as output:
        os.chmod(path, 0o600)
        json.dump(lease, output)
        output.flush()
        os.fsync(output.fileno())
    patch(node, [{'op': 'add', 'path': '/metadata/annotations', 'value': {**annotations, OWNER: lease['owner']}},
                 {'op': 'add', 'path': '/spec/unschedulable', 'value': True}])
    try:
        settle(lease)
    except Exception:
        release(lease)
        path.unlink()
        raise
    return lease


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['acquire', 'release'])
    parser.add_argument('--node')
    parser.add_argument('--lease', type=Path, required=True)
    args = parser.parse_args()
    if args.operation == 'acquire':
        if not args.node:
            parser.error('acquire requires --node')
        acquire(args.node, args.lease)
        print('Qualification slot reserved; existing pods keep running')
    else:
        release(json.loads(args.lease.read_text()))
        args.lease.unlink()
        print('Qualification slot released')


if __name__ == '__main__':
    main()
