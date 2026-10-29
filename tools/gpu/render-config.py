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
# One directory per model; the gpu-models ApplicationSet makes an Argo
# application for each, so one model's sync never waits on another.
MODELS = GPU / 'models'
APPLICATIONS = KUBE / 'platform/gpu-models.yaml'


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


IMAGE = re.compile(r'\d{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9/._-]+:gpu-base-inputs-[0-9a-f]{64}')
TEMPLATES = ROOT / 'infra/environments/prod/runpod/templates.json'
RUNTIMES = ROOT / 'product/inference/gpu/runtimes.json'
OPS_MCP = KUBE / 'operations/ops-mcp/workload.yaml'


def validate_pins(pins):
    # RunPod pulls only by tag; imageDigest records the build the tag names.
    if (set(pins) != {'image', 'imageDigest', 'hostBundle'} or set(pins['hostBundle']) != {'sha256', 'baseId'} or
            not IMAGE.fullmatch(pins['image']) or not re.fullmatch('sha256:[0-9a-f]{64}', pins['imageDigest']) or
            not re.fullmatch('[0-9a-f]{64}', pins['hostBundle']['sha256']) or
            not re.fullmatch('[A-Za-z0-9._-]{1,64}', pins['hostBundle']['baseId'])):
        raise ValueError('Invalid GPU fleet pins')


def validate_bundles(runtimes, base_id):
    # A host runs the bundle each release built for its own base, so a base
    # can be pinned only once every release has a bundle for it. Bundles for
    # older bases stay until no host runs them.
    for key, runtime in runtimes.items():
        bundles = runtime.get('bundles')
        if (not isinstance(bundles, dict) or not bundles or
                not all(re.fullmatch('[A-Za-z0-9._-]{1,64}', base) and isinstance(digest, str) and
                        re.fullmatch('[0-9a-f]{64}', digest) for base, digest in bundles.items())):
            raise ValueError(f'Runtime release {key} needs a bundles map from base ID to bundle digest')
        if base_id not in bundles:
            raise ValueError(f'Runtime release {key} has no bundle for the pinned base {base_id}')


def pinned_copies(pins):
    """The RunPod template and ops-mcp's enrollment settings, derived from the pins."""
    templates = json.loads(TEMPLATES.read_text())
    templates['image'] = pins['image']
    workload = OPS_MCP.read_text()
    for name, value in (('GPU_BASE_IMAGE', pins['image']),
                        ('GPU_HOST_BOOTSTRAP_SHA256', pins['hostBundle']['sha256']),
                        ('GPU_HOST_BOOTSTRAP_BASE_ID', pins['hostBundle']['baseId'])):
        pattern = re.compile(rf'(- name: {name}\n\s+value: )\S+')
        if len(pattern.findall(workload)) != 1:
            raise ValueError(f'{OPS_MCP} must set {name} exactly once')
        workload = pattern.sub(lambda match: match.group(1) + value, workload)
    return {TEMPLATES: json.dumps(templates, indent=2) + '\n', OPS_MCP: workload}


def render(retire=()):
    hosts, secrets = inventory([item for item in yaml.safe_load_all((GPU / 'hosts.yaml').read_text()) if item])
    runtimes = json.loads(RUNTIMES.read_text())
    controller = list(yaml.safe_load_all((GPU / 'controller.yaml').read_text()))
    pins = json.loads((GPU / 'pins.json').read_text())
    validate_pins(pins)
    validate_bundles(runtimes, pins['hostBundle']['baseId'])
    # Controllers now read hosts from GpuHost objects. The list stays for the
    # controller image running before the release that reads them; removing it
    # in the same change would crash that controller before its successor starts.
    encoded = json.dumps({'namespace': 'gpu-inference', 'hosts': hosts, 'runtimes': runtimes},
                         separators=(',', ':'))
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
    fleet_pins = [{'apiVersion': 'v1', 'kind': 'ConfigMap',
                   'metadata': {'name': 'gpu-fleet-pins', 'namespace': 'gpu-inference'},
                   'data': {'pins.json': json.dumps(pins, indent=2) + '\n'}}]
    outputs = {GPU / 'controller.yaml': controller, GPU / 'rbac.yaml': rbac, GPU / 'credentials.yaml': credentials,
               GPU / 'gpu-fleet-pins.yaml': fleet_pins}
    for name, model in json.loads((GPU / 'models.json').read_text()).items():
        # The name becomes a directory and the gpu-model-<name> application,
        # which must stay a 63-character label.
        if len(name) > 53 or not re.fullmatch(r'[a-z](?:[a-z0-9-]*[a-z0-9])?', name):
            raise ValueError('A model name must be a DNS label of at most 53 characters: ' + repr(name))
        path = MODELS / name / f'{name}.yaml'
        outputs[path] = [rollout(name, model, runtimes)]
        if "autoscaling" in model:
            outputs[path].append(autoscaler(name, model, runtimes[model["runtime"]]))
    # A list generator rather than a git directory generator: listing
    # directories makes Argo check out the repository with its submodules,
    # and the private autotrain submodule cannot be fetched there.
    applications = yaml.safe_load(APPLICATIONS.read_text())
    applications['spec']['generators'] = [{'list': {'elements': [
        {'model': name} for name in sorted(json.loads((GPU / 'models.json').read_text()))]}}]
    outputs[APPLICATIONS] = [applications]
    return outputs


def retired_outputs(outputs):
    return set(MODELS.glob('*/*.yaml')) - set(outputs)


def main():
    parser = argparse.ArgumentParser(description='Render GPU controller inventory and model Rollouts from hosts.yaml and models.json.')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--retire', action='append', default=[], metavar='INSTANCE_ID',
                        help='drop the access of a host removed from hosts.yaml whose GpuHost is gone')
    args = parser.parse_args()
    outputs = render(set(args.retire))
    obsolete = retired_outputs(outputs)
    if obsolete:
        # The gpu-models ApplicationSet keeps a removed model's resources serving.
        names = sorted(path.parent.name for path in obsolete)
        raise SystemExit('Models removed from models.json still have manifests: ' + ', '.join(names) + '. '
                         'Delete their directories under gpu-inference/models/ in the same change and merge it. '
                         'Once Argo has deleted ' + ', '.join(f'gpu-model-{name}' for name in names)
                         + ' (their resources keep running), run '
                         + '; '.join(f'kubectl -n gpu-inference delete rollout,scaledobject {name}' for name in names)
                         + '.')
    stale = []
    for path, content in pinned_copies(json.loads((GPU / 'pins.json').read_text())).items():
        if args.check:
            if path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content)
    for path, documents in outputs.items():
        content = ('# One Argo application per model from one template. The model list is generated by\n'
                   '# tools/gpu/render-config.py from models.json; other fields are editable. Deleting an\n'
                   "# application keeps its Rollout serving (preserveResourcesOnDeletion).\n"
                   if path == APPLICATIONS else
                   '# Inventory fields generated by tools/gpu/render-config.py; other fields are editable.\n'
                   if path.name in ('controller.yaml', 'rbac.yaml', 'credentials.yaml')
                   else '# Generated by tools/gpu/render-config.py; edit hosts.yaml, models.json, pins.json or runtimes.json.\n')
        content += yaml.safe_dump_all(documents, sort_keys=False, width=120)
        if args.check:
            if not path.exists() or path.read_text() != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
    if stale:
        raise SystemExit('GPU manifests are stale; run python3 tools/gpu/render-config.py:\n' + '\n'.join(stale))


if __name__ == '__main__':
    main()
