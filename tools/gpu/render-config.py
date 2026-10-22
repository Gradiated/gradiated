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


# Field bounds are checked against the GpuHost CRD schema by
# tools/security/check_gpu_inference.py; this derives what the manifests need.
def inventory(documents):
    hosts, secrets, pods = [], [], set()
    for document in documents:
        if document.get('apiVersion') != 'fleet.gradiated.com/v1alpha1' or document.get('kind') != 'GpuHost':
            raise ValueError('hosts.yaml may only contain GpuHost objects')
        spec = document['spec']
        instance = str(uuid.UUID(spec['instanceId']))
        if instance != spec['instanceId'] or document['metadata']['name'] != 'gpu-' + instance:
            raise ValueError('A GpuHost must be named gpu-<canonical instance ID>')
        if any(host['instance_id'] == instance for host in hosts) or spec['provider']['podId'] in pods:
            raise ValueError('GpuHost instance and pod IDs must be unique')
        pods.add(spec['provider']['podId'])
        capacity = spec['inventory']
        hosts.append({'instance_id': instance,
                      'endpoint': f'http://gpu-{instance}.tailscale-inference.svc.cluster.local:8888/_kubelet',
                      'token_file': f'/var/run/gradiated-host-keys/{instance}',
                      'gpu_count': capacity['gpuCount'], 'cpu': capacity['cpu'],
                      'memory_gib': capacity['memoryGiB'], 'gpu_product': capacity['gpuProduct']})
        secrets.append({'secretKey': instance, 'remoteRef': dict(spec['managementSecret'])})
    if not hosts:
        raise ValueError('GPU inventory cannot be empty')
    return hosts, secrets


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


def node_names(documents):
    return [name for resource in documents
            if resource['kind'] == 'ClusterRole' and resource['metadata']['name'] == 'gpu-controller-nodes'
            for rule in resource['rules'] for name in rule.get('resourceNames', [])]


def render(retire=()):
    hosts, secrets = inventory([item for item in yaml.safe_load_all((GPU / 'hosts.yaml').read_text()) if item])
    runtimes = json.loads((ROOT / 'product/inference/gpu/runtimes.json').read_text())
    controller = list(yaml.safe_load_all((GPU / 'controller.yaml').read_text()))
    pin = json.loads((GPU / 'host.json').read_text())
    if pin is not None and (set(pin) != {'sha256', 'base_id'} or
                            not re.fullmatch('[0-9a-f]{64}', pin['sha256']) or
                            not re.fullmatch('[A-Za-z0-9._-]+', pin['base_id'])):
        raise ValueError('Invalid host bundle pin')
    # Controllers now read hosts from GpuHost objects. The list stays for the
    # controller image running before the release that reads them; removing it
    # in the same change would crash that controller before its successor starts.
    encoded = json.dumps({'namespace': 'gpu-inference', 'hosts': hosts, 'runtimes': runtimes,
                          'host_bundle': pin}, separators=(',', ':'))
    controller[0]['data']['hosts.json'] = encoded + '\n'
    controller[1]['spec']['template']['metadata']['annotations']['gradiated.com/host-inventory'] = hashlib.sha256(encoded.encode()).hexdigest()
    rbac = list(yaml.safe_load_all((GPU / 'rbac.yaml').read_text()))
    credentials = list(yaml.safe_load_all((GPU / 'credentials.yaml').read_text()))
    # Retiring has two steps. Removing a host from hosts.yaml stops Argo wanting
    # its GpuHost, but the host keeps its node permissions and management key so
    # it can still be drained after `kubectl delete gpuhost`; --retire drops them
    # once the GpuHost is gone.
    listed = {host['instance_id'] for host in hosts}
    retiring = [name.removeprefix('gpu-') for name in node_names(rbac)
                if name.removeprefix('gpu-') not in listed and name.removeprefix('gpu-') not in retire]
    secrets += [entry for entry in credentials[1]['spec'].get('data', []) if entry['secretKey'] in retiring]
    names = ['gpu-' + instance for instance in [host['instance_id'] for host in hosts] + retiring]
    for resource in rbac:
        # gpu-fleet-nodes lets the operator cordon a GPU node it is draining, and no other node.
        if resource['metadata']['name'] in ('gpu-controller-nodes', 'gpu-controller-leases', 'gpu-fleet-nodes') and 'rules' in resource:
            for rule in resource['rules']:
                if 'resourceNames' in rule:
                    rule['resourceNames'] = names
    credentials[1]['spec'].pop('dataFrom', None)
    credentials[1]['spec']['data'] = secrets
    outputs = {GPU / 'controller.yaml': controller, GPU / 'rbac.yaml': rbac, GPU / 'credentials.yaml': credentials}
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
    existing = set()
    for path in GPU.glob('*.yaml'):
        if any(document and document.get('kind') == 'Rollout'
               for document in yaml.safe_load_all(path.read_text())):
            existing.add(path)
    return existing - set(outputs)


def main():
    parser = argparse.ArgumentParser(description='Render GPU controller inventory and model Rollouts from hosts.yaml and models.json.')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--retire', action='append', default=[], metavar='INSTANCE_ID',
                        help='drop the access of a host removed from hosts.yaml whose GpuHost is gone')
    args = parser.parse_args()
    outputs = render(set(args.retire))
    obsolete = retired_outputs(outputs)
    if obsolete:
        raise SystemExit('Drain workloads and remove retired Rollouts explicitly: ' + ', '.join(str(path) for path in sorted(obsolete)))
    stale = []
    for path, documents in outputs.items():
        content = ('# Inventory fields generated by tools/gpu/render-config.py; other fields are editable.\n'
                   if path.name in ('controller.yaml', 'rbac.yaml', 'credentials.yaml')
                   else '# Generated by tools/gpu/render-config.py; edit hosts.yaml, models.json or runtimes.json.\n')
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
