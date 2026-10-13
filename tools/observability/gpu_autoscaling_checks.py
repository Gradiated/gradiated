"""Exercise GPU HPA queries against realistic gateway scrape and request series."""
import json

import yaml


def check_gpu_autoscaling(root):
    kube = root / 'infra/environments/prod/us-east-1/kubernetes'
    gpu = kube / 'gpu-inference'
    app = yaml.safe_load((kube / 'platform/gpu-inference.yaml').read_text())['spec']
    assert 'RespectIgnoreDifferences=true' in app['syncPolicy']['syncOptions']
    assert app['ignoreDifferences'] == [{'group': 'argoproj.io', 'kind': 'Rollout',
                                        'namespace': 'gpu-inference', 'jsonPointers': ['/spec/replicas']}]
    tests = []
    models = json.loads((gpu / 'models.json').read_text())
    catalogue = json.loads((root / 'product/inference/gpu/runtimes.json').read_text())
    for name, model in models.items():
        rollout, obj = yaml.safe_load_all((gpu / f'{name}.yaml').read_text())
        spec = obj['spec']
        assert spec['scaleTargetRef'] == {'apiVersion': 'argoproj.io/v1alpha1', 'kind': 'Rollout', 'name': name}
        assert spec['minReplicaCount'] == rollout['spec']['replicas'] == model['replicas']
        assert spec['maxReplicaCount'] == model['autoscaling']['max_replicas']
        assert spec['fallback']['replicas'] == model['replicas']
        assert spec['fallback']['behavior'] == 'currentReplicasIfHigher'
        assert spec['advanced']['restoreToOriginalReplicaCount'] is False
        down = spec['advanced']['horizontalPodAutoscalerConfig']['behavior']['scaleDown']
        assert down['stabilizationWindowSeconds'] >= 600
        assert down['policies'] == [{'type': 'Pods', 'value': 1, 'periodSeconds': 750}]
        triggers = {trigger['name']: trigger for trigger in spec['triggers']}
        assert set(triggers) == {'concurrency', 'work', 'capacity'}
        for trigger in triggers.values():
            assert trigger['metricType'] == 'AverageValue'
            assert trigger['metadata']['ignoreNullValues'] == 'false'
        model_id = catalogue[model['runtime']]['model_id']

        def series(metric, values, pod='a', **labels):
            labels = {'namespace': 'gradiated', 'pod': pod, **labels}
            selector = ','.join(f'{key}="{value}"' for key, value in labels.items())
            return {'series': f'{metric}{{{selector}}}', 'values': values}

        def reporters():
            result = [series('kube_deployment_status_replicas_available', '2+0x12',
                             pod='', deployment='gateway')]
            for pod in ('a', 'b'):
                result += [series('gradiated_gateway_service_info', '1+0x12', pod),
                           series('up', '1+0x12', pod, job='gateway')]
            return result

        def case(label, data, expected, eval_time='2m'):
            checks = []
            for signal, value in expected.items():
                expression = triggers[signal]['metadata']['query']
                if signal == 'work':
                    expression = 'round(' + expression + ', 0.000001)'
                checks.append({'expr': expression,
                               'eval_time': eval_time,
                               'exp_samples': [] if value is None else [{'labels': '{}', 'value': value}]})
            tests.append({'name': f'GPU scaling {name}: {label}', 'interval': '30s',
                          'input_series': data, 'promql_expr_test': checks})

        zero = {'concurrency': 0, 'work': 0, 'capacity': 0}
        absent = dict.fromkeys(zero)
        case('healthy idle model is zero', reporters(), zero)
        case('missing telemetry holds replicas', [], absent)
        partial = reporters()
        partial.pop()
        case('missing gateway cannot hide load', partial, absent)
        unhealthy = reporters()
        unhealthy[-1]['values'] = '0+0x12'
        case('failed gateway scrape holds replicas', unhealthy, absent)
        stale = reporters()
        for item in stale:
            if item['series'].startswith('up'):
                item['values'] = '1 1 stale'
        case('stale gateway scrape holds replicas', stale, absent)
        case('sum concurrent work across gateway replicas', reporters() + [
            series('gradiated_gateway_active_generations', '7+0x12', model=model_id),
            series('gradiated_gateway_active_generations', '5+0x12', 'b', model=model_id)],
             {**zero, 'concurrency': 12})
        case('short requests between scrapes contribute occupied seconds', reporters() + [
            series('gradiated_gateway_runtime_latency_seconds_sum', '0+180x12', model=model_id)],
             {**zero, 'work': 6})
        case('first capacity event needs no preceding zero scrape', reporters() + [
            series('gradiated_gateway_capacity_rejection_timestamp_seconds', '_ _ _ 90+0x9', model=model_id)],
             {**zero, 'capacity': spec['maxReplicaCount']})
        case('capacity event expires instead of holding the ceiling forever', reporters() + [
            series('gradiated_gateway_capacity_rejection_timestamp_seconds', '30+0x12', model=model_id)],
             zero, eval_time='3m')
        case('customer policy rejection does not grow GPU fleet', reporters() + [
            series('gradiated_gateway_admission_rejections_total', '0+100x12', model=model_id,
                   reason='insufficient_balance')], zero)
        case('another model does not affect this model', reporters() + [
            series('gradiated_gateway_active_generations', '100+0x12', model='other')], zero)
        case('load does not decay to idle during a scrape outage', stale + [
            series('gradiated_gateway_active_generations', '100+0x12', model=model_id)], absent)
    return tests
