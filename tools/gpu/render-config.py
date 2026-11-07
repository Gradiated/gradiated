#!/usr/bin/env python3
import argparse
import hashlib
import importlib.util
import json
import math
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


# models.json maps each public model to its minimum slots and its pools. A pool is
# one Rollout: one runtime release on one GPU type. A slot is one concurrent
# request a replica admits: its runtime's enforced active_requests, or the pool's
# slots for a runtime without one. Every pool scales on the same two signals;
# there is no per-model tuning.
UTILIZATION = 0.7  # keep each model's in-flight requests at 70% of its slots
REFUSAL_SHARE = 0.05  # add a replica while our capacity refuses over 5% of requests
RESERVED = 'gradiated.com/reserved'
PROMETHEUS = 'http://observability-kube-prometh-prometheus.observability.svc:9090'
REPLICA_RULES = KUBE / 'workloads/observability/model-replica-rules.yaml'
NAME = re.compile(r'[a-z](?:[a-z0-9-]*[a-z0-9])?')
POOL_FIELDS = {'runtime', 'gpu', 'gpu_count', 'reservation', 'spread', 'slots', 'max_replicas', 'mode', 'replicas',
               'progress_deadline_seconds', 'max_surge', 'max_unavailable', 'rolling_update', 'labels', 'annotations'}
SERVING_ANNOTATIONS = {'gradiated.com/model-id', 'gradiated.com/release',
                       'gradiated.com/serving-model-id', 'gradiated.com/serving-mode'}


def count(value, minimum=0):
    return type(value) is int and value >= minimum


def plan(models, runtimes, hosts):
    """Validate models.json and derive every pool's slots, replica floor and fill position."""
    if not isinstance(models, dict) or not models:
        raise ValueError('models.json must map public model IDs to their pools')
    reserved = {}
    for host in hosts:
        for taint in host.get('extra_taints', []):
            if taint['key'] == RESERVED:
                reserved.setdefault(taint['value'], []).append(host['instance_id'])
    pools = {}
    for model_id, model in models.items():
        if not isinstance(model, dict) or set(model) != {'min_slots', 'pools'}:
            raise ValueError(f'Model {model_id} needs exactly min_slots and pools')
        if not count(model['min_slots']):
            raise ValueError(f'Model {model_id} min_slots must be a non-negative integer')
        if not isinstance(model['pools'], dict) or not model['pools']:
            raise ValueError(f'Model {model_id} needs at least one pool')
        # Production pools fill in the order they are listed: the floor first,
        # then demand, so earlier pools should be the cheaper slots.
        ahead, unfilled = [], model['min_slots']
        for name, pool in model['pools'].items():
            # The name becomes a directory and the gpu-model-<name> application,
            # which must stay a 63-character label.
            if len(name) > 53 or not NAME.fullmatch(name):
                raise ValueError('A pool name must be a DNS label of at most 53 characters: ' + repr(name))
            if name in pools:
                raise ValueError(f'Pool {name} appears under two models')
            if not isinstance(pool, dict) or not set(pool) <= POOL_FIELDS:
                raise ValueError(f'Pool {name} has unknown fields: {sorted(set(pool) - POOL_FIELDS)}')
            runtime = runtimes[pool['runtime']]
            if runtime.get('kind') == 'training':
                raise ValueError(f'Pool {name} cannot serve a training runtime')
            if runtime['model_id'] != model_id and runtime['model_id'] in models:
                raise ValueError(f'Pool {name} runs another public model')
            if runtime.get('active_requests') is None:
                slots = pool.get('slots')
                if not count(slots, 1):
                    raise ValueError(f'Pool {name} needs slots: its runtime enforces no active_requests')
            elif 'slots' in pool:
                raise ValueError(f'Pool {name} takes its slots from its runtime active_requests')
            else:
                slots = runtime['active_requests']
            mode = pool.get('mode', 'production')
            if mode == 'qualification':
                # Staged capacity: SDK-qualified but never routed, scaled or counted.
                if runtime['model_id'] == model_id:
                    raise ValueError(f'Qualification pool {name} needs a private runtime model ID')
                if 'max_replicas' in pool or not count(pool.get('replicas'), 1):
                    raise ValueError(f'Qualification pool {name} needs a fixed replicas count, not max_replicas')
                floor = maximum = pool['replicas']
            elif mode == 'production':
                maximum = pool.get('max_replicas')
                if 'replicas' in pool or not count(maximum):
                    raise ValueError(f'Production pool {name} needs max_replicas; min_slots sets its floor')
                floor = min(maximum, math.ceil(unfilled / slots))
                unfilled = max(0, unfilled - floor * slots)
            else:
                raise ValueError(f'Pool {name} mode must be production or qualification')
            if 'reservation' in pool and not reserved.get(pool['reservation']):
                raise ValueError(f'Pool {name} needs a host in hosts.yaml reserved for {pool["reservation"]!r}')
            pools[name] = {**pool, 'model': model_id, 'mode': mode, 'slots': slots, 'floor': floor,
                           'maximum': maximum, 'ahead': list(ahead),
                           'hosts': sorted(reserved.get(pool.get('reservation'), []))}
            if mode == 'production' and maximum:
                ahead.append((name, maximum, slots))
        if unfilled:
            raise ValueError(f'Model {model_id} min_slots exceeds what its production pools can hold')
        if not model['min_slots'] and any(runtimes[pool['runtime']]['release'].get('protocol') == 'system_one'
                                          for pool in model['pools'].values()):
            raise ValueError(f'Model {model_id} serves SystemOne, which OpenRouter cannot serve, so min_slots must be positive')
    return pools


def rollout(name, pool, runtimes):
    if 'app.kubernetes.io/name' in pool.get('labels', {}):
        raise ValueError('The model identity label is reserved')
    if SERVING_ANNOTATIONS.intersection(pool.get('annotations', {})):
        raise ValueError('Model identity and serving annotations are reserved')
    if not count(pool.get('progress_deadline_seconds'), 1):
        raise ValueError('progress_deadline_seconds must be a positive integer')
    surge, unavailable = pool.get('max_surge', 1), pool.get('max_unavailable', 0)
    if not count(surge) or not count(unavailable) or surge + unavailable == 0:
        raise ValueError('max_surge and max_unavailable must be non-negative integers and not both zero')
    rolling = pool.get('rolling_update', False)
    if type(rolling) is not bool:
        raise ValueError('rolling_update must be a boolean')
    if not isinstance(pool.get('gpu'), str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,62}', pool['gpu']):
        raise ValueError('gpu must be the GPU product label of the hosts the pool runs on')
    runtime = runtimes[pool['runtime']]
    labels = {'app.kubernetes.io/name': name, **pool.get('labels', {})}
    annotations = {**pool.get('annotations', {}), 'gradiated.com/model-id': runtime['model_id'],
                   'gradiated.com/release': json.dumps(runtime['release'], separators=(',', ':'))}
    if runtime['model_id'] != pool['model']:
        # The worker routes a private runtime identity under its public model
        # only in production mode, so a qualification pool is never served.
        annotations['gradiated.com/serving-model-id'] = pool['model']
        annotations['gradiated.com/serving-mode'] = pool['mode']
    steps = [
        {'setWeight': 100 if rolling else 50},
        {'analysis': {'templates': [{'templateName': 'sdk-qualification'}], 'args': [
            {'name': 'app', 'value': name},
            {'name': 'hash', 'valueFrom': {'podTemplateHashValue': 'Latest'}}]}}
    ]
    if not rolling:
        steps.append({'setWeight': 100})
    selector = {'gradiated.com/provider': 'runpod', 'nvidia.com/gpu.product': pool['gpu']}
    if 'gpu_count' in pool:
        if not count(pool['gpu_count'], 1):
            raise ValueError('gpu_count must be a positive integer')
        selector['nvidia.com/gpu.count'] = str(pool['gpu_count'])
    tolerations = [{'key': 'gradiated.com/gpu', 'operator': 'Equal', 'value': 'true', 'effect': 'NoSchedule'}]
    affinity = {}
    if pool['hosts']:
        # A reservation both admits the pool to its hosts and keeps it on them.
        tolerations.append({'key': RESERVED, 'operator': 'Equal', 'value': pool['reservation'], 'effect': 'NoSchedule'})
        affinity['nodeAffinity'] = {'requiredDuringSchedulingIgnoredDuringExecution': {'nodeSelectorTerms': [
            {'matchExpressions': [{'key': 'gradiated.com/instance-id', 'operator': 'In', 'values': pool['hosts']}]}]}}
    spread = pool.get('spread')
    term = {'topologyKey': 'kubernetes.io/hostname', 'labelSelector': {'matchLabels': {'app.kubernetes.io/name': name}}}
    if spread == 'required':
        affinity['podAntiAffinity'] = {'requiredDuringSchedulingIgnoredDuringExecution': [term]}
    elif spread == 'preferred':
        affinity['podAntiAffinity'] = {'preferredDuringSchedulingIgnoredDuringExecution': [
            {'weight': 100, 'podAffinityTerm': term}]}
    elif spread is not None:
        raise ValueError('spread must be required or preferred')
    limits = {'cpu': runtime['cpu'], 'memory': runtime['memory'], 'nvidia.com/gpu': str(runtime['gpus'])}
    pod = {
        'serviceAccountName': 'model-runtime', 'automountServiceAccountToken': False,
        'terminationGracePeriodSeconds': 750, 'nodeSelector': selector, 'tolerations': tolerations,
        'containers': [{'name': 'runtime', 'image': runtime['image'], 'resources': {
            'requests': {**limits, 'memory': runtime.get('request_memory', runtime['memory'])}, 'limits': limits}}]}
    if affinity:
        pod['affinity'] = affinity
    metadata = {'name': name, 'namespace': 'gpu-inference'}
    if not pool['maximum']:
        # Argo holds a switched-off pool at zero; otherwise KEDA owns replicas.
        metadata['annotations'] = {'gradiated.com/paused-replicas': '0'}
    return {
        'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout', 'metadata': metadata,
        'spec': {'replicas': pool['floor'], 'progressDeadlineSeconds': pool['progress_deadline_seconds'],
                 'progressDeadlineAbort': True,
                 'strategy': {'canary': {'maxSurge': surge, 'maxUnavailable': unavailable, 'steps': steps}},
                 'selector': {'matchLabels': labels},
                 'template': {'metadata': {'labels': labels, 'annotations': annotations}, 'spec': pod}}}


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


def validate_active_requests(pools, runtimes, profiles):
    # Desmond reports this limit, the gateway weights routing by it and the
    # autoscaler counts it as the replica's slots, so it must be the limit the
    # runtime enforces. A declared value that drifted from the launcher is how
    # the earlier maximum_concurrency field went wrong.
    for key, runtime in runtimes.items():
        limit = runtime.get('active_requests')
        if 'active_requests' in runtime and (type(limit) is not int or not 1 <= limit <= 4096):
            raise ValueError(f'Runtime release {key} active_requests must be an integer from 1 to 4096')
    for name, pool in pools.items():
        runtime = runtimes[pool['runtime']]
        if not runtime['image'].startswith('gradiated/glm-sglang-bundle@'):
            continue
        selected = runtime.get('environment', {}).get('GLM_SGLANG_PROFILE')
        matching = [profile for profile_name, profile in profiles.items()
                    if profile_name == selected or (selected is None and profile['gpu_product'] == pool['gpu'])]
        if len(matching) != 1:
            raise ValueError(f'Pool {name} has no single GLM SGLang profile for its GPU')
        enforced = matching[0]['active_requests']
        if runtime.get('active_requests') != enforced:
            raise ValueError(f'Pool {name} runtime active_requests must equal its launcher profile, {enforced}')


def disruption_budget(name, pool):
    # Voluntary disruptions, such as a host drain, take one replica below the floor at most.
    return {'apiVersion': 'policy/v1', 'kind': 'PodDisruptionBudget',
            'metadata': {'name': name, 'namespace': 'gpu-inference'},
            'spec': {'minAvailable': pool['floor'] - 1,
                     'selector': {'matchLabels': {'app.kubernetes.io/name': name}}}}


def desired_replicas(name):
    return f'max(rollout_info_replicas_desired{{namespace="gpu-inference",name="{name}"}})'


def ready_replicas(name):
    return f'max(rollout_info_replicas_available{{namespace="gpu-inference",name="{name}"}})'


def scaling_queries(name, pool):
    """The two signals every pool scales on, in slots for this pool to supply."""
    model = 'model=' + json.dumps(pool['model'])
    # The model's slot need at the target utilization, less what the pools
    # ahead of this one serve. A pool ahead still growing counts at its
    # maximum; once it requests its maximum only its ready replicas count, so
    # demand it cannot place or serve passes on.
    busy = f'(max(gradiated:model_busy_slots{{{model}}}) or (0 * sum(gradiated:autoscaling_demand{{service="gateway"}})))'
    need = f'{busy} / {UTILIZATION}' + ''.join(
        f' - (({ready_replicas(other)} * {slots} and on() ({desired_replicas(other)} >= {maximum}))'
        f' or vector({maximum * slots}))' for other, maximum, slots in pool['ahead'])
    # While refusals exceed their share, ask for one replica more than are
    # ready, so capacity grows one replica at a time as each finishes loading.
    # Above ten replicas ask for 10% more, past the HPA's 10% tolerance. A pool
    # steps up only once every pool ahead of it requests its maximum, so a pool
    # that cannot place its replicas hands demand on.
    ready = ready_replicas(name)
    step = f'({ready} + 1 + floor({ready} / 10)) * {pool["slots"]}'
    full = ''.join(f' and on() ({desired_replicas(other)} >= {maximum})' for other, maximum, _ in pool['ahead'])
    refusing = f'(gradiated:model_capacity_refusal_ratio{{{model}}} > {REFUSAL_SHARE})'
    return {'utilization': f'clamp_min({need}, 0)',
            'refusals': f'(({step} and on() {refusing}{full}) or vector(0))'}


def autoscaler(name, pool):
    health = 'gradiated:autoscaling_demand{service="gateway"}'
    # Missing or stale gateway telemetry yields no sample, so KEDA falls back
    # and holds the current count instead of reading load as zero.
    fresh = f'({health} and (timestamp({health}) > time() - 45))'
    return {
        'apiVersion': 'keda.sh/v1alpha1', 'kind': 'ScaledObject',
        'metadata': {'name': name, 'namespace': 'gpu-inference',
                     'annotations': {'argocd.argoproj.io/sync-options': 'SkipDryRunOnMissingResource=true'}},
        'spec': {
            'scaleTargetRef': {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout', 'name': name},
            # A pool scales to zero only after half an hour without demand.
            'pollingInterval': 15, 'cooldownPeriod': 1800,
            'minReplicaCount': pool['floor'], 'maxReplicaCount': pool['maximum'],
            'fallback': {'failureThreshold': 3, 'replicas': pool['floor'], 'behavior': 'currentReplicasIfHigher'},
            'advanced': {'restoreToOriginalReplicaCount': False, 'horizontalPodAutoscalerConfig': {'behavior': {
                'scaleUp': {'stabilizationWindowSeconds': 0, 'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}]},
                # Removing a replica waits out its 750-second drain.
                'scaleDown': {'stabilizationWindowSeconds': 600, 'policies': [{'type': 'Pods', 'value': 1, 'periodSeconds': 750}]}}}},
            'triggers': [{'type': 'prometheus', 'name': signal, 'metricType': 'AverageValue', 'metadata': {
                'serverAddress': PROMETHEUS, 'query': f'{query} and on() {fresh}',
                'threshold': str(pool['slots']), 'ignoreNullValues': 'false'}}
                for signal, query in scaling_queries(name, pool).items()]}}


def replica_rules(pools):
    """Per-pool replica targets for the model availability alerts."""
    rules = []
    for name, pool in pools.items():
        serving = pool['mode'] == 'production' and pool['maximum']
        # A rollout may take max_unavailable replicas below the floor while it
        # replaces them, but a pool with a floor always needs one ready replica.
        minimum = max(pool['floor'] - pool.get('max_unavailable', 0), min(pool['floor'], 1)) if serving else 0
        labels = {'model': pool['model'], 'rollout': name}
        rules += [
            {'record': 'gradiated_model_desired_replicas', 'labels': dict(labels),
             'expr': f'{desired_replicas(name)} or vector({pool["floor"]})' if serving else 'vector(0)'},
            {'record': 'gradiated_model_minimum_replicas', 'labels': dict(labels),
             'expr': f'vector({minimum})'}]
    return {'apiVersion': 'monitoring.coreos.com/v1', 'kind': 'PrometheusRule',
            'metadata': {'name': 'gradiated-model-replicas', 'labels': {'release': 'observability'}},
            'spec': {'groups': [{'name': 'gradiated.models.desired', 'rules': rules}]}}


def model_outputs(models, runtimes, hosts):
    pools = plan(models, runtimes, hosts)
    validate_active_requests(pools, runtimes, glm_sglang_profiles())
    outputs = {}
    for name, pool in pools.items():
        documents = [rollout(name, pool, runtimes)]
        if pool['mode'] == 'production' and pool['floor'] >= 2:
            documents.append(disruption_budget(name, pool))
        # A switched-off pool has no pods and no autoscaler. A qualification
        # pool keeps one at its fixed count so the fleet operator can surge it
        # during a host re-image like any other pool.
        if pool['maximum']:
            documents.append(autoscaler(name, pool))
        outputs[MODELS / name / f'{name}.yaml'] = documents
    outputs[REPLICA_RULES] = [replica_rules(pools)]
    return pools, outputs


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
        # Optional kernels a qualified host compiled for each bundle; hosts seed
        # them before a first start and compile anything missing.
        caches = runtime.get('compile_caches', {})
        if (not isinstance(caches, dict) or
                not all(base in bundles and isinstance(digest, str) and re.fullmatch('[0-9a-f]{64}', digest)
                        for base, digest in caches.items())):
            raise ValueError(f'Runtime release {key} compile_caches must map its bundle base IDs to archive digests')


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
    pools, rendered = model_outputs(json.loads((GPU / 'models.json').read_text()), runtimes, hosts)
    outputs.update(rendered)
    # One Argo application per pool, named after the pool. A list generator
    # rather than a git directory generator: listing directories makes Argo
    # check out the repository with its submodules, and the private autotrain
    # submodule cannot be fetched there.
    applications = yaml.safe_load(APPLICATIONS.read_text())
    applications['spec']['generators'] = [{'list': {'elements': [{'model': name} for name in sorted(pools)]}}]
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
        content = ('# One Argo application per model pool from one template. The pool list is generated by\n'
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
