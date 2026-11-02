"""Exercise the actual candidate analysis queries with healthy and broken revisions."""
import yaml


def check_rollouts(root):
    path = root / 'infra/environments/prod/us-east-1/kubernetes/workloads/rollout-analysis.yaml'
    templates = {t['metadata']['name']: t['spec'] for t in yaml.safe_load_all(path.read_text())}
    rules, tests = [], []
    for service, metric in [('api', 'gradiated_api_http_requests_total'),
                            ('gateway', 'gradiated_gateway_http_requests_total'),
                            ('proxy', 'gradiated_proxy_requests_total')]:
        metrics = list(templates['service-telemetry']['metrics'])
        if service == 'gateway':
            metrics += templates['gateway-streams']['metrics']
        for analysis in metrics:
            query = analysis['provider']['prometheus']['query']
            for name, value in [('service', service), ('hash', 'candidate'), ('http-metric', metric)]:
                query = query.replace('{{args.' + name + '}}', value)
            record = f'check:rollout_{service}_{len(rules)}'
            rules.append({'record': record, 'expr': query})

            def series(name, values, **labels):
                labels = {'namespace': 'gradiated', 'rollout_revision': 'candidate', **labels}
                selector = ','.join(f'{k}="{v}"' for k, v in labels.items())
                return {'series': f'{name}{{{selector}}}', 'values': values}

            def case(label, data, expected, eval_time='2m'):
                tests.append({'name': f'rollout {service} {analysis["name"]}: {label}',
                              'interval': '30s', 'input_series': data,
                              'promql_expr_test': [{'expr': f'{record} > bool 0', 'eval_time': eval_time,
                                                   'exp_samples': [{'labels': '{}', 'value': expected}]}]})

            if analysis['name'] == 'candidate-metrics-present':
                def ready_pods(count):
                    return [{'series': 'kube_replicaset_status_ready_replicas{namespace="gradiated",replicaset="'
                             + service + '-candidate"}', 'values': f'{count}+0x8'}]

                healthy = series('up', '1+0x8', service=service, pod='a')
                other = series('up', '1+0x8', service=service, pod='b')
                case('missing telemetry fails', ready_pods(1), 0)
                case('fresh healthy scrape', ready_pods(1) + [healthy], 1)
                case('failed scrape', ready_pods(1) + [series('up', '0+0x8', service=service)], 0)
                case('stale scrape fails', ready_pods(1) + [series('up', '1 stale', service=service)], 0)
                case('stable telemetry cannot qualify candidate', ready_pods(1) +
                     [series('up', '1+0x8', service=service, rollout_revision='stable')], 0)
                case('every ready candidate is observed', ready_pods(2) + [healthy, other], 1)
                case('healthy pod cannot hide a missing target', ready_pods(2) + [healthy], 0)
                case('healthy pod cannot hide a stale target', ready_pods(2) + [healthy,
                     series('up', '1 1 _ _ _', service=service, pod='b')], 0)
                case('missing ready replica count fails closed', [healthy], 0)
                case('stale ready replica count fails closed', [healthy, {
                     **ready_pods(1)[0], 'values': '1 1 _ _ _'}], 0)
            else:
                stream = analysis['name'] == 'candidate-generation-failures'
                counter = 'gradiated_gateway_generations_total' if stream else metric
                success, failure = ('succeeded', 'failed') if stream else ('200', '500')
                case('idle has no observed error regression', [], 0)
                case('persistent errors fail', [series(counter, '0+10x8', status=failure)], 1)
                case('errors outside the 90-second window expire',
                     [series(counter, '0 0 10 10 10+0x4', status=failure)], 0, eval_time='150s')
                case('healthy traffic passes', [series(counter, '0+100x8', status=success)], 0)
                case('isolated error is tolerated', [series(counter, '0 1+0x8', status=failure)], 0)
                case('exactly two percent errors is allowed', [
                     series(counter, '0+2x8', status=failure),
                     series(counter, '0+98x8', status=success)], 0)
                case('above two percent with enough failures is rejected', [
                     series(counter, '0+2x8', status=failure),
                     series(counter, '0+96x8', status=success)], 1)
                case('high ratio with fewer than three failures is allowed',
                     [series(counter, '0+0.5x8', status=failure)], 0)
                if stream or service == 'gateway':
                    case('verification failures cannot reject candidate',
                         [series(counter, '0+10x8', status=failure, traffic='verification')], 0)
                    case('routed failures still reject candidate', [
                         series(counter, '0+10x8', status=failure, traffic='routed'),
                         series(counter, '0+100000x8', status=success, traffic='verification')], 1)
                case('stable errors do not contaminate candidate',
                     [series(counter, '0+10x8', status=failure, rollout_revision='stable')], 0)
                if not stream:
                    case('readiness errors are handled separately',
                         [series(counter, '0+10x8', status=failure, route='/health/ready')], 0)
    return rules, tests
