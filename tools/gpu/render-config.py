#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import re
import sys
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
        extra_taints = host_taints(spec)
        hosts.append({'instance_id': instance,
                      'endpoint': f'http://gpu-{instance}.tailscale-inference.svc.cluster.local:8888/_kubelet',
                      'token_file': f'/var/run/gradiated-host-keys/{instance}',
                      'gpu_count': capacity['gpuCount'], 'cpu': capacity['cpu'],
                      'memory_gib': capacity['memoryGiB'], 'gpu_product': capacity['gpuProduct'],
                      **({'extra_taints': extra_taints} if extra_taints else {})})
        secrets.append({'secretKey': instance, 'remoteRef': dict(spec['managementSecret'])})
    if not hosts:
        raise ValueError('GPU inventory cannot be empty')
    return hosts, secrets


def valid_label_key(key):
    label = r'[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?'
    dns_label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
    parts = key.split('/')
    return (len(parts) <= 2 and re.fullmatch(label, parts[-1]) is not None
            and (len(parts) == 1 or (len(parts[0]) <= 253
                 and all(re.fullmatch(dns_label, segment) for segment in parts[0].split('.')))))


def host_taints(spec):
    taints = spec.get('extraTaints', [])
    if not isinstance(taints, list) or len(taints) > 16:
        raise ValueError('GpuHost extraTaints must be a list of at most 16 reservations')
    keys = {'gradiated.com/gpu'}
    label = r'[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?'
    for item in taints:
        if (not isinstance(item, dict) or set(item) != {'key', 'value', 'effect'}
                or not all(isinstance(value, str) for value in item.values())
                or item['effect'] != 'NoSchedule' or not valid_label_key(item['key'])
                or item['key'].startswith(('node.kubernetes.io/', 'node.cloudprovider.kubernetes.io/'))
                or (item['value'] and not re.fullmatch(label, item['value'])) or item['key'] in keys):
            raise ValueError('GpuHost extraTaints require unique explicit key/value NoSchedule reservations')
        keys.add(item['key'])
    return [dict(item) for item in taints]


def model_tolerations(model):
    extra = model.get('extra_tolerations', [])
    if not isinstance(extra, list):
        raise ValueError('Model extra_tolerations must be a list')
    tolerations = [{'key': 'gradiated.com/gpu', 'operator': 'Equal', 'value': 'true', 'effect': 'NoSchedule'}]
    keys = {'gradiated.com/gpu'}
    label = r'[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,61}[A-Za-z0-9])?'
    for item in extra:
        if (not isinstance(item, dict) or set(item) != {'key', 'operator', 'value', 'effect'}
                or not all(isinstance(value, str) for value in item.values())
                or item['operator'] != 'Equal' or item['effect'] != 'NoSchedule'):
            raise ValueError('Model extra_tolerations require explicit key/value Equal NoSchedule entries')
        if (not valid_label_key(item['key'])
                or item['key'].startswith(('node.kubernetes.io/', 'node.cloudprovider.kubernetes.io/'))
                or (item['value'] and not re.fullmatch(label, item['value']))
                or item['key'] in keys):
            raise ValueError('Model extra_tolerations contain an invalid, reserved or duplicate key/value')
        keys.add(item['key'])
        tolerations.append(dict(item))
    return tolerations


def rollout(name, model, runtimes):
    if len(name) > 63 or not re.fullmatch(r'[a-z](?:[a-z0-9-]*[a-z0-9])?', name):
        raise ValueError('Invalid model resource name')
    if 'app.kubernetes.io/name' in model.get('labels', {}):
        raise ValueError('The model identity label is reserved')
    if model['replicas'] < 1 or model['progress_deadline_seconds'] < 1:
        raise ValueError('Serving replicas and deadlines must be positive')
    parent = model.get('canary_for')
    if 'canary_for' in model and (not isinstance(parent, str) or parent == name
                                  or not re.fullmatch(r'[a-z](?:[a-z0-9-]*[a-z0-9])?', parent)):
        raise ValueError('canary_for must name a distinct primary model resource')
    surge = model.get('max_surge', 1)
    unavailable = model.get('max_unavailable', 0)
    single_unavailable = model.get('allow_single_replica_unavailable', False)
    if type(single_unavailable) is not bool or (single_unavailable and
            (parent or type(model['replicas']) is not int or model['replicas'] != 1 or type(surge) is not int or surge != 0
             or type(unavailable) is not int or unavailable != 1)):
        raise ValueError('allow_single_replica_unavailable requires one primary replica, max_surge 0 and max_unavailable 1')
    if type(surge) is not int or surge < (0 if parent or single_unavailable else 1):
        raise ValueError('Rollout max_surge must be positive unless an explicit canary can become unavailable')
    maximum = model['replicas'] if parent or single_unavailable else model['replicas'] - 1
    if type(unavailable) is not int or not 0 <= unavailable <= maximum:
        raise ValueError('Rollout max_unavailable exceeds the replica availability bound')
    if surge == 0 and unavailable == 0:
        raise ValueError('Rollout max_surge and max_unavailable cannot both be zero')
    paused = model.get('autoscaling', {}).get('paused_replicas')
    reserved = {'gradiated.com/canary-of', 'gradiated.com/model-id',
                'gradiated.com/serving-model-id', 'gradiated.com/serving-mode'}
    if reserved.intersection(model.get('annotations', {})):
        raise ValueError('Model identity and serving annotations are reserved')
    if 'serving_model_id' in model and 'serving_mode' not in model:
        raise ValueError('A serving model mapping requires explicit serving_mode')
    mode = model.get('serving_mode', 'production')
    if mode not in ('production', 'qualification'):
        raise ValueError('serving_mode must be production or qualification')
    if ('serving_model_id' in model or mode == 'qualification') and not parent:
        raise ValueError('Serving identity mapping and qualification require an explicit canary')
    if 'serving_model_id' in model and (not isinstance(model['serving_model_id'], str) or not model['serving_model_id'].strip()):
        raise ValueError('serving_model_id must be a nonempty model ID')
    runtime = runtimes[model['runtime']]
    if mode == 'qualification' and ('serving_model_id' not in model
                                    or runtime['model_id'] == model['serving_model_id']):
        raise ValueError('Qualification requires a public mapping and a distinct private runtime model ID')
    if runtime.get('kind') == 'training':
        raise ValueError('Training runtimes cannot serve a Rollout')
    labels = {'app.kubernetes.io/name': name, **model.get('labels', {})}
    annotations = {**model.get('annotations', {}), 'gradiated.com/model-id': runtime['model_id'],
                   'gradiated.com/release': json.dumps(runtime['release'], separators=(',', ':'))}
    if parent:
        annotations['gradiated.com/canary-of'] = parent
        annotations['gradiated.com/serving-model-id'] = model.get('serving_model_id', runtime['model_id'])
        annotations['gradiated.com/serving-mode'] = mode
    rolling = model.get('rolling_update', False)
    if type(rolling) is not bool:
        raise ValueError('rolling_update must be a boolean')
    steps = [
        {'setWeight': 100 if rolling else 50},
        {'analysis': {'templates': [{'templateName': 'sdk-qualification'}], 'args': [
            {'name': 'app', 'value': name},
            {'name': 'hash', 'valueFrom': {'podTemplateHashValue': 'Latest'}}]}}
    ]
    if not rolling:
        steps.append({'setWeight': 100})
    limits = {'cpu': runtime['cpu'], 'memory': runtime['memory'], 'nvidia.com/gpu': str(runtime['gpus'])}
    pod = {
        'serviceAccountName': 'model-runtime', 'automountServiceAccountToken': False,
        'terminationGracePeriodSeconds': 750, 'nodeSelector': model['node_selector'],
        'tolerations': model_tolerations(model),
        'containers': [{'name': 'runtime', 'image': runtime['image'], 'resources': {
            'requests': {**limits, 'memory': runtime.get('request_memory', runtime['memory'])}, 'limits': limits}}]}
    if 'affinity' in model:
        pod['affinity'] = model['affinity']
    return {
        'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout',
        'metadata': {'name': name, 'namespace': 'gpu-inference',
                     **({'annotations': {'gradiated.com/paused-replicas': str(paused)}} if paused is not None else {})},
        'spec': {'replicas': paused if paused is not None else model['replicas'], 'progressDeadlineSeconds': model['progress_deadline_seconds'],
                 'progressDeadlineAbort': True,
                 'strategy': {'canary': {'maxSurge': surge, 'maxUnavailable': unavailable, 'steps': steps}},
                 'selector': {'matchLabels': labels},
                 'template': {'metadata': {'labels': labels, 'annotations': annotations}, 'spec': pod}}}


def validate_canaries(models, runtimes):
    for name, model in models.items():
        if 'canary_for' not in model:
            continue
        parent_name = model['canary_for']
        if not isinstance(parent_name, str) or parent_name == name or parent_name not in models:
            raise ValueError('canary_for must name an existing distinct primary model resource')
        parent = models[parent_name]
        if 'canary_for' in parent:
            raise ValueError('A canary_for target cannot itself be a canary')
        if model.get('serving_model_id', runtimes[model['runtime']]['model_id']) != parent.get('serving_model_id', runtimes[parent['runtime']]['model_id']):
            raise ValueError('A canary must serve the same model ID as its primary')


GLM_SGLANG_CONFIG = ROOT / 'product/inference/runtimes/glm-sglang/config.py'


def glm_sglang_profiles():
    spec = importlib.util.spec_from_file_location('glm_sglang_config', GLM_SGLANG_CONFIG)
    config = importlib.util.module_from_spec(spec)
    # Rendering must not leave bytecode beside the launcher source.
    written, sys.dont_write_bytecode = sys.dont_write_bytecode, True
    try:
        spec.loader.exec_module(config)
    finally:
        sys.dont_write_bytecode = written
    return config.PROFILES


def validate_active_requests(models, runtimes, profiles):
    # Desmond reports this limit and the gateway weights routing by it, so it
    # must be the limit the runtime enforces. A declared value that drifted from
    # the launcher is how the earlier maximum_concurrency field went wrong.
    for key, runtime in runtimes.items():
        limit = runtime.get('active_requests')
        if 'active_requests' in runtime and (type(limit) is not int or not 1 <= limit <= 4096):
            raise ValueError(f'Runtime release {key} active_requests must be an integer from 1 to 4096')
    for name, model in models.items():
        runtime = runtimes[model['runtime']]
        if not runtime['image'].startswith('gradiated/glm-sglang-bundle@'):
            continue
        product = model['node_selector'].get('nvidia.com/gpu.product')
        selected = runtime.get('environment', {}).get('GLM_SGLANG_PROFILE')
        matching = [profile for profile_name, profile in profiles.items()
                    if profile_name == selected or (selected is None and profile['gpu_product'] == product)]
        if len(matching) != 1:
            raise ValueError(f'Model {name} has no single GLM SGLang profile for its GPU')
        if runtime.get('active_requests') != matching[0]['active_requests']:
            raise ValueError(f'Model {name} runtime active_requests must equal its launcher profile, '
                             f'{matching[0]["active_requests"]}')


def disruption_budget(name, model):
    minimum = model['min_available']
    if type(minimum) is not int or not 1 <= minimum <= model['replicas']:
        raise ValueError('Model min_available must be an integer between one and replicas')
    settings = model.get('autoscaling', {})
    if 'paused_replicas' in settings:
        paused = settings['paused_replicas']
        if type(paused) is not int or not 0 <= paused <= settings['max_replicas']:
            raise ValueError('Paused replicas must be an integer within the scaling bounds')
        # A retired or deliberately reduced pool cannot meet its active floor.
        # Keep the configured minimum intact so removing the pause restores it.
        minimum = min(minimum, paused)
    return {'apiVersion': 'policy/v1', 'kind': 'PodDisruptionBudget',
            'metadata': {'name': name, 'namespace': 'gpu-inference'},
            'spec': {'minAvailable': minimum,
                     'selector': {'matchLabels': {'app.kubernetes.io/name': name}}}}


def autoscaler(name, model, runtime):
    settings = model['autoscaling']
    maximum = settings['max_replicas']
    target = settings['target_concurrency']
    if type(maximum) is not int or maximum < model['replicas']:
        raise ValueError('Autoscaling maximum must cover the minimum replicas')
    if type(target) not in (int, float) or not 0 < target < float('inf'):
        raise ValueError('Autoscaling concurrency target must be finite and positive')
    annotations = {'argocd.argoproj.io/sync-options': 'SkipDryRunOnMissingResource=true'}
    if 'paused_replicas' in settings:
        paused = settings['paused_replicas']
        if type(paused) is not int or not 0 <= paused <= maximum:
            raise ValueError('Paused replicas must be an integer within the scaling bounds')
        annotations['autoscaling.keda.sh/paused-replicas'] = str(paused)
    selector = 'namespace="gradiated",model=' + json.dumps(model.get('serving_model_id', runtime['model_id']))
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
        'metadata': {'name': name, 'namespace': 'gpu-inference', 'annotations': annotations},
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
    models = json.loads((GPU / 'models.json').read_text())
    validate_canaries(models, runtimes)
    validate_active_requests(models, runtimes, glm_sglang_profiles())
    for name, model in models.items():
        # The name becomes a directory and the gpu-model-<name> application,
        # which must stay a 63-character label.
        if len(name) > 53 or not re.fullmatch(r'[a-z](?:[a-z0-9-]*[a-z0-9])?', name):
            raise ValueError('A model name must be a DNS label of at most 53 characters: ' + repr(name))
        path = MODELS / name / f'{name}.yaml'
        outputs[path] = [rollout(name, model, runtimes)]
        if 'min_available' in model:
            outputs[path].append(disruption_budget(name, model))
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
