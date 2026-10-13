#!/usr/bin/env python3
import argparse
import hashlib
import ipaddress
import json
import re
from pathlib import Path
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
KUBE = ROOT / 'infra/environments/prod/us-east-1/kubernetes'
GPU = KUBE / 'gpu-inference'


def inventory(entries):
    hosts, services, secrets = [], {}, []
    for entry in entries:
        instance = str(uuid.UUID(entry['instance_id']))
        if instance != entry['instance_id'] or instance in services:
            raise ValueError('Host IDs must be canonical and unique')
        allowed = {'instance_id', 'tailscale_ip', 'management_secret', 'gpu_count', 'cpu', 'memory_gib', 'gpu_product'}
        if set(entry) - allowed:
            raise ValueError('Unknown host inventory fields')
        for field in ('gpu_count', 'cpu', 'memory_gib'):
            if field in entry and (type(entry[field]) is not int or entry[field] <= 0):
                raise ValueError('Host resource budgets must be positive integers')
        address = ipaddress.ip_address(entry['tailscale_ip'])
        if address not in ipaddress.ip_network('100.64.0.0/10'):
            raise ValueError('Expected a Tailscale IPv4 address')
        if any(service['metadata']['annotations']['tailscale.com/tailnet-ip'] == str(address)
               for service in services.values()):
            raise ValueError('Hosts cannot share a Tailscale address')
        name = 'gpu-' + instance
        host = {'instance_id': instance,
                'endpoint': f'http://{name}.tailscale-inference.svc.cluster.local:8888/_kubelet',
                'token_file': f'/var/run/gradiated-host-keys/{instance}',
                **{key: value for key, value in entry.items()
                   if key not in ('instance_id', 'tailscale_ip', 'management_secret')}}
        hosts.append(host)
        services[instance] = {
            'apiVersion': 'v1', 'kind': 'Service',
            'metadata': {'name': name, 'namespace': 'tailscale-inference', 'annotations': {
                'tailscale.com/tailnet-ip': str(address),
                'tailscale.com/proxy-group': 'inference-egress'}},
            'spec': {'type': 'ExternalName', 'externalName': 'unused',
                     'ports': [{'name': 'inference', 'port': 8888, 'protocol': 'TCP'}]}}
        remote = entry['management_secret']
        if not remote['key']:
            raise ValueError('A management secret reference is required')
        secrets.append({'secretKey': instance, 'remoteRef': remote})
    if not hosts:
        raise ValueError('GPU inventory cannot be empty')
    return hosts, services, secrets


def rollout(name, model, runtimes):
    if len(name) > 63 or not re.fullmatch(r'[a-z](?:[a-z0-9-]*[a-z0-9])?', name):
        raise ValueError('Invalid model resource name')
    if 'app.kubernetes.io/name' in model.get('labels', {}):
        raise ValueError('The model identity label is reserved')
    if model['replicas'] < 1 or model['progress_deadline_seconds'] < 1:
        raise ValueError('Serving replicas and deadlines must be positive')
    runtime = runtimes[model['runtime']]
    if runtime.get('kind') == 'training':
        raise ValueError('Training runtimes cannot serve a Rollout')
    labels = {'app.kubernetes.io/name': name, **model.get('labels', {})}
    annotations = {**model.get('annotations', {}), 'gradiated.com/model-id': runtime['model_id'],
                   'gradiated.com/release': json.dumps(runtime['release'], separators=(',', ':'))}
    limits = {'cpu': runtime['cpu'], 'memory': runtime['memory'], 'nvidia.com/gpu': str(runtime['gpus'])}
    pod = {
        'serviceAccountName': 'model-runtime', 'automountServiceAccountToken': False,
        'terminationGracePeriodSeconds': 750, 'nodeSelector': model['node_selector'],
        'tolerations': [{'key': 'gradiated.com/gpu', 'operator': 'Equal', 'value': 'true', 'effect': 'NoSchedule'}],
        'containers': [{'name': 'runtime', 'image': runtime['image'], 'resources': {
            'requests': {**limits, 'memory': runtime.get('request_memory', runtime['memory'])}, 'limits': limits}}]}
    if 'affinity' in model:
        pod['affinity'] = model['affinity']
    return {
        'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout',
        'metadata': {'name': name, 'namespace': 'gpu-inference'},
        'spec': {'replicas': model['replicas'], 'progressDeadlineSeconds': model['progress_deadline_seconds'],
                 'progressDeadlineAbort': True,
                 'strategy': {'canary': {'maxSurge': 1, 'maxUnavailable': 0, 'steps': [
                     {'setWeight': 50}, {'analysis': {'templates': [{'templateName': 'sdk-qualification'}], 'args': [
                         {'name': 'app', 'value': name},
                         {'name': 'hash', 'valueFrom': {'podTemplateHashValue': 'Latest'}}]}}, {'setWeight': 100}]}},
                 'selector': {'matchLabels': labels},
                 'template': {'metadata': {'labels': labels, 'annotations': annotations}, 'spec': pod}}}


def render():
    hosts, services, secrets = inventory(json.loads((GPU / 'hosts.json').read_text()))
    runtimes = json.loads((ROOT / 'product/inference/gpu/runtimes.json').read_text())
    controller = list(yaml.safe_load_all((GPU / 'controller.yaml').read_text()))
    encoded = json.dumps({'namespace': 'gpu-inference', 'hosts': hosts, 'runtimes': runtimes}, separators=(',', ':'))
    controller[0]['data']['hosts.json'] = encoded + '\n'
    controller[1]['spec']['template']['metadata']['annotations']['gradiated.com/host-inventory'] = hashlib.sha256(encoded.encode()).hexdigest()
    rbac = list(yaml.safe_load_all((GPU / 'rbac.yaml').read_text()))
    names = ['gpu-' + host['instance_id'] for host in hosts]
    for resource in rbac:
        if resource['metadata']['name'] in ('gpu-controller-nodes', 'gpu-controller-leases') and 'rules' in resource:
            for rule in resource['rules']:
                if 'resourceNames' in rule:
                    rule['resourceNames'] = names
    credentials = list(yaml.safe_load_all((GPU / 'credentials.yaml').read_text()))
    credentials[1]['spec'].pop('dataFrom', None)
    credentials[1]['spec']['data'] = secrets
    outputs = {GPU / 'controller.yaml': controller, GPU / 'rbac.yaml': rbac, GPU / 'credentials.yaml': credentials}
    for instance, service in services.items():
        outputs[KUBE / 'tailscale-inference/hosts' / f'{instance}.yaml'] = [service]
    for name, model in json.loads((GPU / 'models.json').read_text()).items():
        outputs[GPU / f'{name}.yaml'] = [rollout(name, model, runtimes)]
    return outputs


def retired_outputs(outputs):
    existing = set((KUBE / 'tailscale-inference/hosts').glob('*.yaml'))
    for path in GPU.glob('*.yaml'):
        if any(document and document.get('kind') == 'Rollout'
               for document in yaml.safe_load_all(path.read_text())):
            existing.add(path)
    return existing - set(outputs)


def main():
    parser = argparse.ArgumentParser(description='Render GPU enrollment and model Rollouts from their inventories.')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = render()
    obsolete = retired_outputs(outputs)
    if obsolete:
        raise SystemExit('Drain workloads and remove retired Services/Rollouts explicitly: ' + ', '.join(str(path) for path in sorted(obsolete)))
    stale = []
    for path, documents in outputs.items():
        content = ('# Inventory fields generated by tools/gpu/render-config.py; other fields are editable.\n'
                   if path.name in ('controller.yaml', 'rbac.yaml', 'credentials.yaml')
                   else '# Generated by tools/gpu/render-config.py; edit hosts.json, models.json or runtimes.json.\n')
        content += yaml.safe_dump_all(documents, sort_keys=False, width=120)
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content)
    if stale:
        raise SystemExit('GPU manifests are stale; run python3 tools/gpu/render-config.py:\n' + '\n'.join(stale))


if __name__ == '__main__':
    main()
