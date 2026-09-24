"""Autoscaling manifest ownership and behavioral PromQL checks."""
import yaml


def check_autoscaling(root):
    workloads = root / 'infra/environments/prod/us-east-1/kubernetes/workloads'
    applications = {d['metadata']['name']: d for d in yaml.safe_load_all(
        (workloads.parent / 'platform/workloads.yaml').read_text())}
    namespace = yaml.safe_load((workloads / 'namespace.yaml').read_text())
    assert namespace['metadata']['labels']['elbv2.k8s.aws/pod-readiness-gate-inject'] == 'enabled'
    alb = yaml.safe_load((workloads.parent / 'platform/aws-load-balancer-controller.yaml').read_text())['spec']
    values = alb['source']['helm']['valuesObject']
    assert values['enablePodReadinessGateInject'] is True
    assert values['podMutatorWebhookConfig']['failurePolicy'] == 'Fail'
    assert 'RespectIgnoreDifferences=true' in alb['syncPolicy']['syncOptions']
    ignored = {r['kind']: r for r in alb['ignoreDifferences']}
    assert ignored['Secret']['name'] == 'aws-load-balancer-tls'
    assert ignored['Secret']['jsonPointers'] == ['/data']
    for kind in ('MutatingWebhookConfiguration', 'ValidatingWebhookConfiguration'):
        assert ignored[kind]['name'] == 'aws-load-balancer-webhook'
        assert ignored[kind]['jqPathExpressions'] == ['.webhooks[].clientConfig.caBundle']
    check_headroom(workloads)
    tests = []
    for service in ('api', 'gateway', 'proxy', 'worker'):
        owners = [name for name, app in applications.items()
                  if f'{service}-autoscaling.yaml' in
                  app['spec']['source'].get('directory', {}).get('include', '')]
        assert owners == [service], (service, owners)

    for service in ('api', 'gateway', 'proxy', 'worker'):
        spec = yaml.safe_load((workloads / f'{service}-autoscaling.yaml').read_text())['spec']
        assert spec['scaleTargetRef']['name'] == service
        resources = list(yaml.safe_load_all((workloads / f'{service}.yaml').read_text()))
        deployment = next(d for d in resources if d['kind'] == 'Deployment')
        budget = next(d for d in resources if d['kind'] == 'PodDisruptionBudget')
        assert deployment['spec']['strategy']['rollingUpdate']['maxUnavailable'] == 0
        if service == 'gateway':
            config = next(d for d in resources if d['kind'] == 'ConfigMap')['data']
            grace = deployment['spec']['template']['spec']['terminationGracePeriodSeconds']
            longest_request = max(int(config['GATEWAY_GENERATION_TIMEOUT_SECONDS']),
                                  int(config['PROXY_TOTAL_TIMEOUT_SECONDS']))
            assert grace >= longest_request + 10 + 5 + 15 + 10, 'Include preStop, drain and flush budgets'
            autoscaler = yaml.safe_load((workloads.parent / 'platform/cluster-autoscaler.yaml').read_text())
            assert int(autoscaler['spec']['source']['helm']['valuesObject']['extraArgs']
                       ['max-graceful-termination-sec']) >= grace
        if service == 'proxy':
            config = next(d for d in resources if d['kind'] == 'ConfigMap')['data']
            grace = deployment['spec']['template']['spec']['terminationGracePeriodSeconds']
            assert grace >= int(config['PROXY_TOTAL_SECONDS']) + 10 + 5 + 15, 'Include preStop and drain budgets'
            target = next(d for d in resources if d['kind'] == 'TargetGroupConfiguration')
            attributes = target['spec']['defaultConfiguration']['targetGroupAttributes']
            delay = int(next(a['value'] for a in attributes if a['key'] == 'deregistration_delay.timeout_seconds'))
            assert grace <= delay <= 3600, 'The ALB drains a target for at most 3600 s'
            autoscaler = yaml.safe_load((workloads.parent / 'platform/cluster-autoscaler.yaml').read_text())
            assert int(autoscaler['spec']['source']['helm']['valuesObject']['extraArgs']
                       ['max-graceful-termination-sec']) >= grace
        pod = deployment['spec']['template']['spec']
        zones = next(c for c in pod['topologySpreadConstraints'] if c['topologyKey'] == 'topology.kubernetes.io/zone')
        if service in ('gateway', 'proxy'):
            assert pod['priorityClassName'] == 'gradiated-critical'
            assert zones['whenUnsatisfiable'] == 'DoNotSchedule' and zones['maxSkew'] == 1
        assert deployment['spec']['replicas'] == spec['minReplicaCount']
        assert budget['spec']['minAvailable'] == 2
        assert spec['minReplicaCount'] == 3 and spec['maxReplicaCount'] == 20
        assert spec['fallback']['behavior'] == 'currentReplicasIfHigher'
        assert spec['fallback']['replicas'] >= spec['minReplicaCount']
        triggers = {t['type']: t for t in spec['triggers']}
        assert set(triggers) == {'prometheus', 'cpu', 'memory'}
        assert triggers['prometheus']['metadata']['ignoreNullValues'] == 'false'
        assert triggers['prometheus']['metricType'] == 'AverageValue'
        for resource in ('cpu', 'memory'):
            assert triggers[resource]['metricType'] == 'Utilization'
            assert triggers[resource]['metadata']['containerName'] == service
        app = applications[service]['spec']
        assert f'{service}-autoscaling.yaml' in app['source']['directory']['include']
        assert 'RespectIgnoreDifferences=true' in app['syncPolicy']['syncOptions']
        assert app['ignoreDifferences'] == [{'group': 'apps', 'kind': 'Deployment',
                                           'name': service, 'namespace': 'gradiated',
                                           'jsonPointers': ['/spec/replicas']}]

        def series(metric, values, pod='a', **labels):
            labels = {'namespace': 'gradiated', 'pod': pod, **labels}
            selector = ','.join(f'{k}="{v}"' for k, v in labels.items())
            return {'series': f'{metric}{{{selector}}}', 'values': values}

        def inputs(pods=('a', 'b')):
            result = [series('kube_deployment_status_replicas_available', '2+0x8',
                             pod='', deployment=service)]
            for pod in pods:
                result.extend([
                    series(f'gradiated_{service}_service_info', '1+0x8', pod),
                    series('up', '1+0x8', pod,
                           job='gradiated/worker' if service == 'worker' else service),
                ])
            return result

        def case(name, data, value):
            tests.append({'name': f'autoscaling {service}: {name}', 'interval': '30s',
                          'input_series': data, 'promql_expr_test': [{
                              'expr': triggers['prometheus']['metadata']['query'],
                              'eval_time': '2m', 'exp_samples': [] if value is None else [{
                                  'labels': f'gradiated:autoscaling_demand{{service="{service}"}}',
                                  'value': value}]}]})

        case('missing telemetry is not zero', [], None)
        if service == 'worker':
            def backlog(pod, count, observation='0+30x8'):
                return [series('gradiated_worker_ingestion_outstanding_messages',
                               f'{count}+0x8', pod),
                        series('gradiated_worker_ingestion_observed_timestamp_seconds',
                               observation, pod)]
            case('shared backlog is not multiplied by replicas',
                 inputs() + backlog('a', 107) + backlog('b', 107), 107)
            case('stale high observation cannot mask fresh zero',
                 inputs() + backlog('a', 1000, '0+0x8') + backlog('b', 0), 0)
            case('stalled observations trigger fallback despite healthy scrape',
                 inputs() + backlog('a', 107, '0+0x8'), None)
            case('unknown lag invalidates zero',
                 inputs() + backlog('a', 0, '0+0x8'), None)
            case('a single healthy reporter suffices for shared demand',
                 inputs(('a',)) + backlog('a', 100), 100)
        else:
            case('healthy idle exporters return zero', inputs(), 0)
            case('missing pod cannot masquerade as idle', inputs(('a',)), None)
            data = inputs()
            data[2]['values'] = '0+0x8'
            case('failed scrape cannot masquerade as idle', data, None)
            if service == 'proxy':
                case('sum in-flight requests across pods', inputs() + [
                    series('gradiated_proxy_in_flight', '300+0x8', 'a', destination='gateway'),
                    series('gradiated_proxy_in_flight', '200+0x8', 'b', destination='anthropic')], 500)
            elif service == 'gateway':
                case('sum active generations across pods', inputs() + [
                    series('gradiated_gateway_active_generations', '40+0x8', 'a'),
                    series('gradiated_gateway_active_generations', '60+0x8', 'b')], 100)
                case('relay-only traffic scales the gateway', inputs() + [
                    series('gradiated_gateway_active_relays', '75+0x8', 'a')], 75)
                case('hosted and relay concurrency add together', inputs() + [
                    series('gradiated_gateway_active_generations', '40+0x8', 'a'),
                    series('gradiated_gateway_active_relays', '60+0x8', 'b')], 100)
            else:
                case('sum request rates excluding health traffic', inputs() + [
                    series('gradiated_api_http_requests_total', '0+300x8', 'a', route='/v1/models'),
                    series('gradiated_api_http_requests_total', '0+600x8', 'b', route='/v1/models'),
                    series('gradiated_api_http_requests_total', '0+9000x8', 'a', route='/health/ready')], 30)
    return tests


def check_headroom(workloads):
    resources = list(yaml.safe_load_all((workloads / 'scaling-headroom.yaml').read_text()))
    priority = next(d for d in resources if d['kind'] == 'PriorityClass')
    reserve = next(d for d in resources if d['kind'] == 'Deployment')
    pod = reserve['spec']['template']['spec']
    autoscaler = yaml.safe_load((workloads.parent / 'platform/cluster-autoscaler.yaml').read_text())
    cutoff = int(autoscaler['spec']['source']['helm']['valuesObject']['extraArgs']
                 ['expendable-pods-priority-cutoff'])
    assert cutoff <= priority['value'] < 0, 'Buffer must trigger node scale-up but yield to services'
    assert priority['globalDefault'] is False
    assert priority['preemptionPolicy'] == 'Never'
    assert pod['priorityClassName'] == priority['metadata']['name']
    assert pod['terminationGracePeriodSeconds'] == 0
    assert pod['nodeSelector'] == {'gradiated.com/pool': 'system'}
    assert not any(d['kind'] == 'PodDisruptionBudget' for d in resources)
    assert reserve['spec']['strategy']['rollingUpdate']['maxSurge'] == 0

    def requests(container):
        req = container['resources']['requests']
        return int(req['cpu'].removesuffix('m')), int(req['memory'].removesuffix('Mi'))

    expected_cpu = expected_memory = 0
    critical = next(d for d in yaml.safe_load_all((workloads / 'priority-classes.yaml').read_text())
                    if d['metadata']['name'] == 'gradiated-critical')
    assert critical['value'] > 0 and critical['globalDefault'] is False
    assert critical['preemptionPolicy'] == 'PreemptLowerPriority'
    for service in ('api', 'worker', 'gateway', 'proxy'):
        deployment = next(d for d in yaml.safe_load_all((workloads / f'{service}.yaml').read_text())
                          if d['kind'] == 'Deployment')
        service_pod = deployment['spec']['template']['spec']
        on_request_path = service in ('gateway', 'proxy')
        assert service_pod.get('priorityClassName') == ('gradiated-critical' if on_request_path else None)
        assert service_pod.get('preemptionPolicy', 'PreemptLowerPriority') == 'PreemptLowerPriority'
        cpu, memory = requests(service_pod['containers'][0])
        baseline = yaml.safe_load((workloads / f'{service}-autoscaling.yaml').read_text())['spec']['minReplicaCount']
        growth = 2 if on_request_path else 1
        expected_cpu += growth * baseline * cpu
        expected_memory += growth * baseline * memory
    cpu, memory = requests(pod['containers'][0])
    replicas = reserve['spec']['replicas']
    assert (replicas * cpu, replicas * memory) == (expected_cpu, expected_memory), \
        'Buffer must reserve enough requested resources to triple gateway and proxy and double API/worker minima'
    app = yaml.safe_load((workloads.parent / 'platform/scaling-headroom.yaml').read_text())
    assert app['spec']['source']['directory']['include'] == 'scaling-headroom.yaml'
    assert 'scaling-headroom.yaml' in yaml.safe_load((workloads / 'kustomization.yaml').read_text())['resources']
