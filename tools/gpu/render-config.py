#!/usr/bin/env python3
import argparse
import hashlib
import json
import re
from pathlib import Path
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
KUBE = ROOT / 'infra/environments/prod/us-east-1/kubernetes'
GPU = KUBE / 'gpu-inference'
# Hosts are routed by MagicDNS name, which stays the same when a re-imaged pod
# rejoins the tailnet with a new address.
TAILNET = 'tail186117.ts.net'


def inventory(entries):
    hosts, services, secrets = [], {}, []
    for entry in entries:
        instance = str(uuid.UUID(entry['instance_id']))
        if instance != entry['instance_id'] or instance in services:
            raise ValueError('Host IDs must be canonical and unique')
        allowed = {'instance_id', 'management_secret', 'gpu_count', 'cpu', 'memory_gib', 'gpu_product'}
        if set(entry) - allowed:
            raise ValueError('Unknown host inventory fields')
        for field in ('gpu_count', 'cpu', 'memory_gib'):
            if field in entry and (type(entry[field]) is not int or entry[field] <= 0):
                raise ValueError('Host resource budgets must be positive integers')
        name = 'gpu-' + instance
        host = {'instance_id': instance,
                'endpoint': f'http://{name}.tailscale-inference.svc.cluster.local:8888/_kubelet',
                'token_file': f'/var/run/gradiated-host-keys/{instance}',
                **{key: value for key, value in entry.items()
                   if key not in ('instance_id', 'management_secret')}}
        hosts.append(host)
        services[instance] = {
            'apiVersion': 'v1', 'kind': 'Service',
            'metadata': {'name': name, 'namespace': 'tailscale-inference', 'annotations': {
                'tailscale.com/tailnet-fqdn': f'{name}.{TAILNET}',
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


def autoscaler(name, model, runtime):
    settings = model['autoscaling']
    maximum = settings['max_replicas']
    target = settings['target_concurrency']
    if type(maximum) is not int or maximum < model['replicas']:
        raise ValueError('Autoscaling maximum must cover the minimum replicas')
    if type(target) not in (int, float) or not 0 < target < float('inf'):
        raise ValueError('Autoscaling concurrency target must be finite and positive')
    selector = 'namespace="gradiated",model=' + json.dumps(runtime['model_id'])
    health = 'gradiated:autoscaling_demand{service="gateway"}'
    fresh = f'({health} and (timestamp({health}) > time() - 45))'
    idle = f'(0 * sum({health}))'
    queries = {
        'concurrency': f'max_over_time((sum(gradiated_gateway_active_generations{{{selector}}}) or {idle})[1m:15s])',
        'work': f'(sum(rate(gradiated_gateway_runtime_latency_seconds_sum{{{selector}}}[2m])) or {idle})',
        'capacity': f'((max(gradiated_gateway_capacity_rejection_timestamp_seconds{{{selector}}} > time() - 120) > bool 0) or vector(0)) * {maximum}',
    }
    return {
        'apiVersion': 'keda.sh/v1alpha1', 'kind': 'ScaledObject',
        'metadata': {'name': name, 'namespace': 'gpu-inference', 'annotations': {
            'argocd.argoproj.io/sync-options': 'SkipDryRunOnMissingResource=true'}},
        'spec': {
            'scaleTargetRef': {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout', 'name': name},
            'pollingInterval': 15, 'minReplicaCount': model['replicas'], 'maxReplicaCount': maximum,
            'fallback': {'failureThreshold': 3, 'replicas': model['replicas'], 'behavior': 'currentReplicasIfHigher'},
            'advanced': {'restoreToOriginalReplicaCount': False, 'horizontalPodAutoscalerConfig': {'behavior': {
                'scaleUp': {'stabilizationWindowSeconds': 0, 'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}]},
                'scaleDown': {'stabilizationWindowSeconds': 600, 'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 750}]}}}},
            'triggers': [{'type': 'prometheus', 'name': signal, 'metricType': 'AverageValue', 'metadata': {
                'serverAddress': 'http://observability-kube-prometh-prometheus.observability.svc:9090',
                'query': f'({query}) and on() {fresh}',
                'threshold': str(1 if signal == 'capacity' else target), 'ignoreNullValues': 'false'}}
                for signal, query in queries.items()]}}


def render():
    hosts, services, secrets = inventory(json.loads((GPU / 'hosts.json').read_text()))
    runtimes = json.loads((ROOT / 'product/inference/gpu/runtimes.json').read_text())
    controller = list(yaml.safe_load_all((GPU / 'controller.yaml').read_text()))
    pin = json.loads((GPU / 'host.json').read_text())
    if pin is not None and (set(pin) != {'sha256', 'base_id'} or
                            not re.fullmatch('[0-9a-f]{64}', pin['sha256']) or
                            not re.fullmatch('[A-Za-z0-9._-]+', pin['base_id'])):
        raise ValueError('Invalid host bundle pin')
    encoded = json.dumps({'namespace': 'gpu-inference', 'hosts': hosts, 'runtimes': runtimes,
                          'host_bundle': pin}, separators=(',', ':'))
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
        document = rollout(name, model, runtimes)
        path = GPU / f'{name}.yaml'
        if path in outputs:
            raise ValueError('Model name collides with a static manifest: ' + name)
        if path.exists():
            existing = [item for item in yaml.safe_load_all(path.read_text()) if item]
            if not existing or existing[0].get('kind') != 'Rollout' or any(item.get('kind') != 'ScaledObject' for item in existing[1:]):
                raise ValueError('Model name collides with a static manifest: ' + name)
        outputs[path] = [document]
        if "autoscaling" in model:
            outputs[path].append(autoscaler(name, model, runtimes[model["runtime"]]))
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
