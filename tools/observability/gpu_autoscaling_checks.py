"""Exercise GPU pool scaling queries against realistic gateway and Rollout series."""
import importlib.util
import json

import yaml


def renderer(root):
    spec = importlib.util.spec_from_file_location('render_config', root / 'tools/gpu/render-config.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_gpu_autoscaling(root):
    kube = root / 'infra/environments/prod/us-east-1/kubernetes'
    gpu = kube / 'gpu-inference'
    app = yaml.safe_load((kube / 'platform/gpu-models.yaml').read_text())['spec']['template']['spec']
    assert 'RespectIgnoreDifferences=true' in app['syncPolicy']['syncOptions']
    # KEDA owns replicas except on a switched-off pool, which Argo holds at zero.
    assert app['ignoreDifferences'] == [{
        'group': 'argoproj.io', 'kind': 'Rollout', 'namespace': 'gpu-inference',
        'jsonPointers': ['/spec/paused'],
        'jqPathExpressions': [
            'select(.metadata.annotations["gradiated.com/paused-replicas"] == null) | .spec.replicas',
        ],
    }]
    render = renderer(root)
    runtimes = json.loads((root / 'product/inference/gpu/runtimes.json').read_text())
    hosts, _ = render.inventory([item for item in yaml.safe_load_all((gpu / 'hosts.yaml').read_text()) if item])
    pools = render.plan(json.loads((gpu / 'models.json').read_text()), runtimes, hosts)
    tests = []
    for name, pool in pools.items():
        documents = [doc for doc in yaml.safe_load_all((gpu / 'models' / name / f'{name}.yaml').read_text()) if doc]
        rollout, = [doc for doc in documents if doc['kind'] == 'Rollout']
        scalers = [doc for doc in documents if doc['kind'] == 'ScaledObject']
        assert rollout['spec']['replicas'] == pool['floor']
        if not pool['maximum']:
            assert not scalers, name
            assert rollout['metadata']['annotations']['gradiated.com/paused-replicas'] == '0'
            continue
        assert 'annotations' not in rollout['metadata'], name
        spec = scalers[0]['spec']
        assert spec['scaleTargetRef'] == {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout', 'name': name}
        assert (spec['minReplicaCount'], spec['maxReplicaCount']) == (pool['floor'], pool['maximum'])
        assert spec['fallback'] == {'failureThreshold': 3, 'replicas': pool['floor'], 'behavior': 'currentReplicasIfHigher'}
        assert spec['advanced']['restoreToOriginalReplicaCount'] is False
        behavior = spec['advanced']['horizontalPodAutoscalerConfig']['behavior']
        # Scale-up requests the whole deficit at once; starts take minutes.
        assert behavior['scaleUp']['selectPolicy'] == 'Max' and behavior['scaleUp']['stabilizationWindowSeconds'] == 0
        assert behavior['scaleUp']['policies'] == [{'type': 'Percent', 'value': 100, 'periodSeconds': 15},
                                                   {'type': 'Pods', 'value': 4, 'periodSeconds': 15}]
        assert behavior['scaleDown']['stabilizationWindowSeconds'] == 60
        assert behavior['scaleDown']['policies'] == [{'type': 'Pods', 'value': 1, 'periodSeconds': 60}]
        # Every pool scales on exactly these signals, measured in its slots.
        # A pool with no floor also brings up a replica for its updating Rollout to qualify.
        assert [trigger['name'] for trigger in spec['triggers']] == (
            ['utilization', 'refusals', 'draining'] + ([] if pool['floor'] else ['qualifying'])), name
        for trigger in spec['triggers']:
            assert trigger['metricType'] == 'AverageValue'
            assert trigger['metadata']['ignoreNullValues'] == 'false'
            assert trigger['metadata']['threshold'] == str(pool['slots'])
        if pool['mode'] == 'production':
            tests += scaling_tests(name, pool, {t['name']: t['metadata']['query'] for t in spec['triggers']})

    # Fill order: a second pool takes only what the first cannot hold, and steps
    # up on refusals only once the first is at its maximum.
    synthetic = render.plan({'test/model': {'min_slots': 24, 'pools': {
        'first': {'runtime': 'large', 'max_replicas': 2}, 'second': {'runtime': 'small', 'max_replicas': 4}}}}, {
        'large': {'model_id': 'test/model', 'active_requests': 12, 'release': {}},
        'small': {'model_id': 'test/model', 'active_requests': 3, 'release': {}}}, [])
    assert [(p['floor'], p['maximum']) for p in synthetic.values()] == [(2, 2), (0, 4)]
    for name, pool in synthetic.items():
        tests += scaling_tests(name, pool, render.scaling_queries(name, pool), wrap=True)
    return tests


def scaling_tests(name, pool, queries, wrap=False):
    model = pool['model']
    health = 'gradiated:autoscaling_demand{service="gateway"}'
    if wrap:
        queries = {signal: f'{query} and on() ({health} and (timestamp({health}) > time() - 45))'
                   for signal, query in queries.items()}
    tests = []

    def series(metric, values, pod='a', **labels):
        labels = {'namespace': 'gradiated', 'pod': pod, **labels}
        selector = ','.join(f'{key}="{value}"' for key, value in labels.items())
        return {'series': f'{metric}{{{selector}}}', 'values': values}

    def rollouts(ready=None, ahead=None, ahead_ready=None):
        """This pool's ready replicas, and each pool ahead requesting and serving the given counts or its maximum."""
        result = [{'series': f'rollout_info_replicas_available{{namespace="gpu-inference",name="{name}"}}',
                   'values': f'{pool["floor"] if ready is None else ready}+0x12'}]
        for other, maximum, _ in pool['ahead']:
            result += [{'series': f'rollout_info_replicas_desired{{namespace="gpu-inference",name="{other}"}}',
                        'values': f'{maximum if ahead is None else ahead}+0x12'},
                       {'series': f'rollout_info_replicas_available{{namespace="gpu-inference",name="{other}"}}',
                        'values': f'{maximum if ahead_ready is None else ahead_ready}+0x12'}]
        return result

    def reporters():
        result = [series('kube_deployment_status_replicas_available', '0+0x12', pod='', deployment='gateway'),
                  series('rollout_info_replicas_available', '2+0x12', pod='', name='gateway')]
        for pod in ('a', 'b'):
            result += [series('gradiated_gateway_service_info', '1+0x12', pod),
                       series('up', '1+0x12', pod, job='gateway')]
        return result + rollouts()

    def case(label, data, expected, eval_time='2m'):
        checks = [{'expr': f'round({queries[signal]}, 0.000001)', 'eval_time': eval_time,
                   'exp_samples': [] if value is None else [{'labels': '{}', 'value': value}]}
                  for signal, value in expected.items()]
        tests.append({'name': f'GPU scaling {name}: {label}', 'interval': '30s',
                      'input_series': data, 'promql_expr_test': checks})

    ahead = sum(maximum * slots for _, maximum, slots in pool['ahead'])
    step = (pool['floor'] + 1 + pool['floor'] // 10) * pool['slots']
    zero = {'utilization': 0, 'refusals': 0, 'draining': 0}
    absent = dict.fromkeys(zero)

    def requests(admitted, refused=0, metric='gradiated_gateway_routing_capacity_rejections_total', **labels):
        """Counters advancing by the given requests per 30-second scrape."""
        result = [series('gradiated_gateway_admissions_total', f'0+{admitted}x12', model=model, deployment='d')]
        if refused:
            result.append(series(metric, f'0+{refused}x12', model=model, **labels))
        return result

    case('healthy idle model is zero', reporters(), zero)
    if 'qualifying' in queries:
        def phase(value):
            return [{'series': f'rollout_info{{namespace="gpu-inference",name="{name}",phase="{value}"}}',
                     'values': '1+0x12'}]
        case('settled rollout asks for no qualifying replica', reporters() + phase('Completed'), {'qualifying': 0})
        case('aborted rollout releases its qualifying replica', reporters() + phase('Abort'), {'qualifying': 0})
        for value in ('Progressing', 'Paused'):
            case(f'{value.lower()} rollout asks for one replica to qualify', reporters() + phase(value),
                 {'qualifying': pool['slots']})
        case('missing telemetry holds a qualifying replica', phase('Progressing'), {'qualifying': None})
    case('missing telemetry holds replicas', [], absent)
    partial = [item for item in reporters() if item['series'] != series('up', '', 'b', job='gateway')['series']]
    case('missing gateway cannot hide load', partial, absent)
    unhealthy = [{**item, 'values': '0+0x12'} if item['series'] == series('up', '', 'b', job='gateway')['series'] else item
                 for item in reporters()]
    case('failed gateway scrape holds replicas', unhealthy, absent)
    stale = [{**item, 'values': '1 1 stale'} if item['series'].startswith('up') else item for item in reporters()]
    case('stale gateway scrape holds replicas', stale, absent)
    case('load does not decay to idle during a scrape outage', stale + [
        series('gradiated_gateway_active_generations', '100+0x12', model=model, deployment='d')], absent)

    # 35 in flight across gateways, part of it on OpenRouter, needs 50 slots at
    # the default 70% target, or 35 at a pool's target of 100%.
    need = round(35 / pool['utilization'], 6)
    case('in-flight requests across gateways and OpenRouter set the slot need', reporters() + [
        series('gradiated_gateway_active_generations', '24+0x12', model=model, deployment='d'),
        series('gradiated_gateway_active_generations', '11+0x12', 'b', model=model, deployment='openrouter')],
         {**zero, 'utilization': max(0, need - ahead)})
    # Utilization keeps its peak for the pool's hold, so load that just stopped still holds the count.
    case('the slot need holds its peak', reporters() + [
        series('gradiated_gateway_active_generations', '35 35 0+0x10', model=model, deployment='d')],
         {**zero, 'utilization': max(0, need - ahead)}, eval_time='5m')
    case('another model does not affect this model', reporters() + [
        series('gradiated_gateway_active_generations', '100+0x12', model='other', deployment='d')], zero)

    # A terminating replica holds the replicas that are staying until it has gone,
    # whatever the lagging Rollout desired count still says.
    def pod(suffix, deleting=False, phase='Running'):
        selector = f'namespace="gpu-inference",pod="{name}-5b4888d4c5-{suffix}"'
        result = [{'series': f'kube_pod_status_phase{{{selector},phase="{other}"}}',
                   'values': f'{int(other == phase)}+0x12'} for other in ('Pending', 'Running', 'Succeeded', 'Failed')]
        if deleting:
            result.append({'series': f'kube_pod_deletion_timestamp{{namespace="gpu-inference",pod="{name}-5b4888d4c5-{suffix}"}}',
                           'values': '1+0x12'})
        return result
    lagging = {'series': f'rollout_info_replicas_desired{{namespace="gpu-inference",name="{name}"}}', 'values': '4+0x12'}
    case('a draining replica holds the replicas that stay', reporters() + [lagging] + pod('aaaaa') + pod('bbbbb')
         + pod('ccccc') + pod('ddddd', deleting=True), {**zero, 'draining': 3 * pool['slots']})
    case('a deleted failed pod neither drains nor reduces the staying count', reporters() + [lagging] + pod('aaaaa')
         + pod('bbbbb') + pod('ccccc') + pod('eeeee', deleting=True, phase='Failed'), zero)
    case('a deleted failed pod is not subtracted twice', reporters() + [lagging] + pod('aaaaa') + pod('bbbbb')
         + pod('ccccc') + pod('eeeee', deleting=True, phase='Failed') + pod('ddddd', deleting=True),
         {**zero, 'draining': 3 * pool['slots']})
    case('a failed pod awaiting garbage collection is not a staying replica', reporters() + [lagging] + pod('aaaaa')
         + pod('bbbbb') + pod('ccccc') + pod('eeeee', phase='Failed') + pod('ddddd', deleting=True),
         {**zero, 'draining': 3 * pool['slots']})
    case("another pool's draining replica does not", reporters() + [lagging] + pod('aaaaa') + [{
        'series': f'kube_pod_deletion_timestamp{{namespace="gpu-inference",pod="{name}-b200-5b4888d4c5-r7b27"}}', 'values': '1+0x12'}],
         zero)
    case('refusals above 5% of requests add a replica', reporters() + requests(54, 6), {**zero, 'refusals': step})
    # The step counts ready replicas, so one still loading holds it until it serves.
    loading = [item for item in reporters() if 'gpu-inference' not in item['series']]
    case('a replica still loading holds the refusal step', loading + rollouts(ready=pool['floor'] - 1 if pool['floor'] else 0)
         + requests(54, 6), {**zero, 'refusals': (max(pool['floor'] - 1, 0) + 1) * pool['slots']})
    case('above ten ready replicas the step clears the HPA tolerance', loading + rollouts(ready=12) + requests(54, 6),
         {**zero, 'refusals': 14 * pool['slots']})
    case('refusals at 3% of requests do not', reporters() + requests(97, 3), zero)
    case('moving to OpenRouter for capacity is a refusal', reporters() + requests(
        54, 6, 'gradiated_gateway_capacity_fallbacks_total', capacity='openrouter', reason='at_capacity', traffic='customer'),
         {**zero, 'refusals': step})
    case('a failure that was not about capacity is not a refusal', reporters() + requests(
        54, 6, 'gradiated_gateway_capacity_fallbacks_total', capacity='openrouter', reason='attempt_failed', traffic='customer'),
         zero)
    case('our capacity_exceeded failures are refusals', reporters() + requests(
        48, 12, 'gradiated_gateway_generations_total', deployment='d', status='failed', error='capacity_exceeded'),
         {**zero, 'refusals': step})
    case("OpenRouter's capacity_exceeded is not ours", reporters() + requests(
        48, 12, 'gradiated_gateway_generations_total', deployment='openrouter', status='failed', error='capacity_exceeded'),
         zero)
    case('customer policy rejection does not grow GPU pools', reporters() + requests(
        54, 6, 'gradiated_gateway_admission_rejections_total', reason='insufficient_balance'), zero)
    # A refusal burst keeps its step for the pool's hold (ten minutes by
    # default), so a starting replica is not removed.
    hold = pool['hold_minutes']
    samples = 2 * (hold + 10)
    burst = [series('gradiated_gateway_admissions_total', f'0+54x4 216+0x{samples}', model=model, deployment='d'),
             series('gradiated_gateway_routing_capacity_rejections_total', f'0+6x4 24+0x{samples}', model=model)]
    long_reporters = [{**item, 'values': item['values'].replace('x12', f'x{samples}')} for item in reporters()]
    case('a refusal burst holds its step for the hold', long_reporters + burst, {**zero, 'refusals': step},
         eval_time=f'{hold - 2}m')
    case('refusals expire a hold after their rate window', long_reporters + burst, zero, eval_time=f'{hold + 6}m')
    if pool['ahead']:
        case('refusals wait for the pools ahead to reach their maximum',
             [item for item in reporters() if 'gpu-inference' not in item['series']]
             + rollouts(ahead=pool['ahead'][0][1] - 1) + requests(54, 6), zero)
        case('demand the pools ahead can hold leaves this pool idle', reporters() + [
            series('gradiated_gateway_active_generations', f'{ahead * 0.7:g}+0x12', model=model, deployment='d')], zero)
        held = [item for item in reporters() if 'gpu-inference' not in item['series']]
        demand = [series('gradiated_gateway_active_generations', f'{ahead * 0.7:g}+0x12', model=model, deployment='d')]
        case('a pool ahead at its maximum that cannot serve hands its demand on',
             held + rollouts(ahead_ready=0) + demand, {**zero, 'utilization': ahead})
        case('a pool ahead still growing keeps its share while it loads',
             held + rollouts(ahead=pool['ahead'][0][1] - 1, ahead_ready=0) + demand, zero)
    return tests
