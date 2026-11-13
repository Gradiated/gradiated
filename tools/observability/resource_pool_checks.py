"""Behavioral fixtures for pool-scoped CPU and memory failover alerts."""
import yaml


def check_resource_pools(root, alerts):
    application = yaml.safe_load((root / 'infra/environments/prod/us-east-1/kubernetes/platform/observability.yaml').read_text())
    disabled = application['spec']['source']['helm']['valuesObject']['defaultRules']['disabled']
    assert all(disabled[name] for name in ('KubeCPUOvercommit', 'KubeMemoryOvercommit'))
    tests = []
    for resource, alert in [('cpu', 'KubeCPUOvercommit'), ('memory', 'KubeMemoryOvercommit')]:
        def fixture(name, system=8, gpu=90, pending=0, ready=True,
                    nodes=2, eval_time='11m', expected=None, cluster='prod'):
            inputs = []

            def series(metric, value, **labels):
                labels = {'job': 'kube-state-metrics', 'cluster': cluster, **labels}
                selector = ','.join(f'{key}="{value}"' for key, value in labels.items())
                inputs.append({'series': metric + '{' + selector + '}', 'values': f'{value}+0x15'})

            for pool, capacity in [('system', 10), ('gpu', 100)]:
                for index in range(nodes):
                    node = f'{pool}-{index}'
                    # CPU capacity also anchors node classification for memory tests.
                    for kind in set(['cpu', resource]):
                        series('kube_node_status_allocatable', capacity, node=node, resource=kind)
                    if pool == 'gpu':
                        series('kube_node_status_allocatable', 2, node=node, resource='nvidia_com_gpu')
                    series('kube_node_status_condition', int(ready), node=node, condition='Ready', status='true')
                    series('kube_node_spec_unschedulable', 0, node=node)

            def pod(name, amount, gpu=False, phase='Running'):
                # Both types intentionally share a namespace: GPU controllers
                # must not inherit the inference hosts' spare capacity.
                labels = {'namespace': 'gpu-inference', 'pod': name}
                series('kube_pod_container_resource_requests', amount,
                       **labels, container='main', resource=resource)
                if gpu:
                    series('kube_pod_container_resource_requests', 1,
                           **labels, container='main', resource='nvidia_com_gpu')
                series('kube_pod_status_phase', 1, **labels, phase=phase)

            pod('controller', system)
            pod('inference', gpu, gpu=True)
            if pending:
                pod('pending-inference', pending, gpu=True, phase='Pending')
            pod('completed-inference', 999, gpu=True, phase='Succeeded')
            rule = alerts[alert]
            expected_alerts = [
                {'exp_labels': {**rule['labels'], 'cluster': cluster, 'pool': pool, 'resource': resource},
                 'exp_annotations': {key: value.replace('{{ $labels.pool }}', pool)
                                     for key, value in rule['annotations'].items()}}
                for pool in (expected or [])
            ]
            tests.append({'name': f'{resource} pools: {name}', 'interval': '1m',
                          'input_series': inputs, 'alert_rule_test': [
                              {'eval_time': eval_time, 'alertname': alert, 'exp_alerts': expected_alerts}]})
            return inputs

        fixture('healthy pools and completed pods')
        fixture('system shortage cannot borrow GPU capacity', system=12, gpu=10, expected=['system'])
        fixture('GPU shortage cannot borrow system capacity', system=1, gpu=105, expected=['gpu'])
        fixture('pending GPU requests count', pending=40, expected=['gpu'])
        fixture('ten-minute persistence', pending=40, eval_time='9m')
        fixture('unavailable nodes supply no capacity', ready=False, expected=['system', 'gpu'])
        fixture('no nodes supply no capacity', nodes=0, expected=['system', 'gpu'])
        fixture('one-node pool checks total capacity', nodes=1)
        fixture('one-node pool overcommitted', nodes=1, gpu=105, expected=['gpu'])
        fixture('exact failover capacity', system=10, gpu=100)
        inputs = fixture('cordoned node excluded', system=15, gpu=10, nodes=3, expected=['system'])
        # Three nodes provide 20 units after failover; cordoning one leaves 10.
        for item in inputs:
            if 'kube_node_spec_unschedulable{' in item['series'] and 'node="system-2"' in item['series']:
                item['values'] = '1+0x15'
        inputs = fixture('NotReady node excluded', system=15, gpu=10, nodes=3, expected=['system'])
        for item in inputs:
            if 'kube_node_status_condition{' in item['series'] and 'node="system-2"' in item['series']:
                item['values'] = '0+0x15'
        inputs = fixture('clusters cannot share capacity', system=12, gpu=10, expected=['system'])
        # Another cluster with the same node/pod names must not produce a join
        # collision or cover the production system pool's shortage.
        inputs += [{**item, 'series': item['series'].replace('cluster="prod"', 'cluster="other"')}
                   for item in inputs if item['series'].startswith('kube_node_')]
    return tests
