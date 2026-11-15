#!/usr/bin/env python3
"""Check alert/dashboard links, PromQL, and probe/stall behavior.

Requires PyYAML and promtool. Run with --promtool /path/to/promtool if needed.
"""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from urllib.parse import parse_qs, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[2]
OBS = ROOT / 'infra/environments/prod/us-east-1/kubernetes/workloads/observability'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--promtool', default=shutil.which('promtool'))
    args = parser.parse_args()
    if not args.promtool:
        parser.error('promtool is required')
    exporter = yaml.safe_load((ROOT / 'infra/environments/prod/us-east-1/kubernetes/platform/cloudwatch-exporter.yaml').read_text())
    exporter_config = yaml.safe_load(exporter['spec']['source']['helm']['valuesObject']['config'])
    for metric_name in ('root_usage', 'urgent_findings', 'review_findings'):
        security_export = next(metric for metric in exporter_config['metrics']
                               if metric['aws_namespace'] == 'Gradiated/Security' and metric['aws_metric_name'] == metric_name)
        assert security_export['aws_statistics'] == ['Maximum']
        assert 0 < security_export['range_seconds'] <= security_export['period_seconds'] - 60, 'CloudWatch rounding must not create a second period whose newer zero masks security events'
    dashboards = {d['uid']: d for p in OBS.glob('*.json')
                  if (d := json.loads(p.read_text()))}
    groups = [g for name in ('prometheus-rules.yaml', 'logging-prometheus-rules.yaml', 'controller-prometheus-rules.yaml', 'resource-pool-rules.yaml', 'autoscaling-prometheus-rules.yaml', 'model-replica-rules.yaml', 'data-store-prometheus-rules.yaml', 'security-prometheus-rules.yaml', 'recovery-prometheus-rules.yaml')
              for g in yaml.safe_load((OBS / name).read_text())['spec']['groups']]
    alerts = {rule['alert']: rule for group in groups for rule in group['rules'] if 'alert' in rule}
    from paging_checks import check_critical_persistence

    check_critical_persistence(alerts.values())
    for name in ('ModelNoReadyReplicas', 'InferenceModelProbeFailed',
                 'InferenceProbeMonitoringStalled', 'GatewayRuntimeFailures'):
        assert alerts[name]['for'] == '1m', f'{name} must tolerate a sub-minute interruption'
    for name, rule in alerts.items():
        annotations = rule['annotations']
        url = urlparse(annotations['panel_url'])
        assert url.scheme == 'https' and url.netloc == 'grafana.gradiated.com', name
        assert annotations['dashboard_url'] == url._replace(query='').geturl(), name
        dashboard = dashboards[url.path.removeprefix('/d/')]
        panel_id = int(parse_qs(url.query)['viewPanel'][0])
        assert any(p['id'] == panel_id and p.get('targets')
                   for p in dashboard['panels']), name
        assert not annotations.get('runbook_url'), name
        if name in ('AwsRootAccountUsed', 'AwsRootUsageMonitoringMissing'):
            assert annotations['logs_url'] == 'https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Fgradiated%252Fsecurity%252Fcloudtrail', name
        elif name in ('AwsUrgentSecurityFinding', 'AwsSecurityFindingNeedsReview'):
            assert annotations['logs_url'] == 'https://console.aws.amazon.com/cloudwatch/home?region=us-east-1#logsV2:log-groups/log-group/%252Fgradiated%252Fsecurity%252Ffindings', name
        else:
            assert annotations['logs_url'].startswith('https://grafana.gradiated.com/d/gradiated-logs?'), name

    # Validate actual chart expressions as recording rules, substituting dashboard variables.
    chart_rules = []
    for dashboard in dashboards.values():
        ids = [p['id'] for p in dashboard['panels']]
        assert len(ids) == len(set(ids)), dashboard['uid']
        for panel in dashboard['panels']:
            if panel.get('datasource', {}).get('type') == 'loki':
                continue
            for target in panel.get('targets', []):
                expr = target['expr'].replace('$__rate_interval', '5m')
                expr = expr.replace('$deployment', '.*').replace('$model', '.*').replace('$__range', '1h')
                # PromQL label_replace uses numeric $1 captures, unlike Grafana variables.
                assert '$' not in re.sub(r'\$[0-9]+', '', expr), expr
                chart_rules.append({'record': f'check:panel_{len(chart_rules)}', 'expr': expr})

    from autoscaling_checks import check_autoscaling

    from gpu_autoscaling_checks import check_gpu_autoscaling

    from rollout_checks import check_rollouts

    rollout_rules, rollout_tests = check_rollouts(ROOT)
    groups.append({'name': 'rollout_analysis_syntax', 'rules': rollout_rules})
    tests = check_autoscaling(ROOT) + check_gpu_autoscaling(ROOT) + rollout_tests
    from resource_pool_checks import check_resource_pools

    tests += check_resource_pools(ROOT, alerts)
    def scenario(name, inputs, expected, checks, labels=None, eval_time="8m", interval="30s"):
        cases = []
        for alert in checks:
            rule = alerts[alert]
            annotations = dict(rule['annotations'])
            extra = labels or {}
            for key, value in annotations.items():
                for label, label_value in extra.items():
                    value = value.replace('{{ $labels.' + label + ' }}', label_value)
                annotations[key] = value
            cases.append({'eval_time': eval_time, 'alertname': alert, 'exp_alerts':
                          [{'exp_labels': {**rule['labels'], **extra},
                            'exp_annotations': annotations}] if alert == expected else []})
        tests.append({'name': name, 'interval': interval, 'input_series': inputs,
                      'alert_rule_test': cases})

    for name, metric, label in [
        ('ApiDependencyDown', 'gradiated_api_dependency_ready', 'dependency="postgres"'),
        ('GatewayDependencyDown', 'gradiated_gateway_dependency_ready', 'dependency="valkey"'),
        ('WorkerLoopDown', 'gradiated_worker_loop_up', 'loop="generation_ingestion"'),
    ]:
        for healthy in [0, 1]:
            scenario(f'{name}: healthy neighbor {healthy}', [
                {'series': metric + '{instance="a",' + label + '}', 'values': '0+0x40'},
                {'series': metric + '{instance="b",' + label + '}', 'values': f'{healthy}+0x40'},
            ], name if not healthy else None, [name], dict([label.replace('"', '').split('=')]))

    for ready, expected in [(0, 'LokiUnavailable'), (1, 'LokiRedundancyDegraded'), (2, None)]:
        scenario('Loki availability: ' + str(ready), [
            {'series': 'kube_statefulset_status_replicas_ready{namespace="observability",statefulset="loki"}',
             'values': f'{ready}+0x40'},
        ], expected, ['LokiUnavailable', 'LokiRedundancyDegraded'],
           {'namespace': 'observability', 'statefulset': 'loki'})

    for failures in [19, 20]:
        scenario('runtime failure sample floor: ' + str(failures), [
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="failed"}',
             'values': f'0 0 {failures}+0x60'},
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="succeeded"}',
             'values': '0 0 20+0x60'},
        ], 'GatewayRuntimeFailures' if failures == 20 else None, ['GatewayRuntimeFailures'],
           {'model': 'test/model', 'deployment': 'test-deployment'}, '2m', interval='5s')

    for name, eval_time, expected in [
        ('brief burst', '30s', None),
        ('sustained for one minute', '2m', 'GatewayRuntimeFailures'),
        ('expired from three-minute window', '4m', None),
    ]:
        scenario('runtime failure persistence: ' + name, [
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="failed"}',
             'values': '0 0 20+0x60'},
        ], expected, ['GatewayRuntimeFailures'],
           {'model': 'test/model', 'deployment': 'test-deployment'}, eval_time, interval='5s')

    lora_labels = {'job': 'lora-loaders', 'instance': 'test:1', 'deployment': 'test-a'}
    def lora_series(metric, values, job='lora-loaders', deployment='test-a'):
        return {'series': metric + '{job="' + job + '",instance="test:1",deployment="' + deployment + '"}', 'values': values}

    for name, up, limit, expected in [('healthy', 1, 100, None), ('unreachable', 0, None, 'LoraLoaderUnavailable'), ('missing payload', 1, None, 'LoraLoaderUnavailable')]:
        inputs = [lora_series('up', f'{up}+0x40')]
        if limit is not None:
            inputs.append(lora_series('gradiated_lora_disk_cache_limit_bytes', f'{limit}+0x40'))
        scenario('lora ' + name, inputs, expected, ['LoraLoaderUnavailable'], lora_labels)
    scenario('lora healthy neighbor cannot mask missing telemetry', [lora_series('up', '1+0x40'), lora_series('gradiated_lora_disk_cache_limit_bytes', '100+0x40'), lora_series('up', '1+0x40', deployment='test-b')], 'LoraLoaderUnavailable', ['LoraLoaderUnavailable'], {**lora_labels, 'deployment': 'test-b'})
    scenario('lora disabled', [lora_series('up', '0+0x40', 'other')], None, ['LoraLoaderUnavailable'])
    for alert, metric in [('LoraPreparationFailures', 'last_failure_timestamp_seconds'), ('LoraCapacityRejected', 'last_capacity_rejection_timestamp_seconds')]:
        values = [lora_series('gradiated_lora_' + metric, '0+0x7 240+0x33')]
        scenario('lora recent ' + metric, values, alert, [alert], lora_labels)
        scenario('lora expired ' + metric, values, None, [alert], eval_time='12m')
    scenario('lora pinned disk pressure', [lora_series('gradiated_lora_pinned_disk_bytes', '95+0x40'), lora_series('gradiated_lora_disk_cache_limit_bytes', '100+0x40')], 'LoraPinnedDiskNearlyFull', ['LoraPinnedDiskNearlyFull'], lora_labels, '16m')

    scenario('lora discovery failure', [{'series': 'prometheus_sd_http_failures_total', 'values': '0+1x40'}], 'LoraTargetDiscoveryFailures', ['LoraTargetDiscoveryFailures'])

    def qualifications(outcome, values):
        return {'series': f'gradiated_api_adapter_qualifications_total{{instance="a",model="z-ai/glm-5.3-flash",outcome="{outcome}",service="api"}}', 'values': values}
    for outcome in ['failed', 'no_capacity']:
        scenario(f'adapter qualification {outcome}', [qualifications(outcome, '0+0x7 1+0x33')], 'AdapterQualificationFailing', ['AdapterQualificationFailing'], {'model': 'z-ai/glm-5.3-flash', 'outcome': outcome})
        scenario(f'adapter qualification {outcome} ages out', [qualifications(outcome, '0+0x7 1+0x33')], None, ['AdapterQualificationFailing'], eval_time='25m')
    for outcome in ['passed', 'rejected']:
        scenario(f'adapter qualification {outcome} is not an incident', [qualifications(outcome, '0+0x7 1+0x33')], None, ['AdapterQualificationFailing'])

    for name, available, snapshots, expected in [
        ('fresh snapshot', 2, [(1, '0+30x40')], None),
        ('one fresh worker suffices', 2, [(0, '0+0x40'), (1, '0+30x40')], None),
        ('database observations fail', 2, [(0, '0+30x40')], 'TrainingObservationsUnavailable'),
        ('successful observation stops refreshing', 2, [(1, '0+0x40')], 'TrainingObservationsUnavailable'),
        ('training gauges disappear', 2, [], 'TrainingObservationsUnavailable'),
        ('workers unavailable', 0, [], None),
    ]:
        inputs = [{'series': 'kube_deployment_status_replicas_available{namespace="gradiated",deployment="temporal-worker"}',
                   'values': f'{available}+0x40'}]
        for i, (healthy, timestamp) in enumerate(snapshots):
            labels = '{job="temporal-worker",instance="worker-' + str(i) + '"}'
            inputs += [{'series': 'gradiated_training_metrics_available' + labels, 'values': f'{healthy}+0x40'},
                       {'series': 'gradiated_training_metrics_timestamp_seconds' + labels, 'values': timestamp}]
        scenario('Training observation ' + name, inputs, expected,
                 ['TrainingObservationsUnavailable'], eval_time='8m')

    for name, failed, cancelled, available, timestamp, expected in [
        ('recent failure', 1, 0, 1, '0+30x40', 'TrainingRunsFailed'),
        ('replicated snapshot', 1, 0, 1, '0+30x40', 'TrainingRunsFailed'),
        ('no failures', 0, 0, 1, '0+30x40', None),
        ('cancelled only', 0, 2, 1, '0+30x40', None),
        ('failed snapshot unavailable', 1, 0, 0, '0+30x40', None),
        ('failed snapshot stale', 1, 0, 1, '0+0x40', None),
    ]:
        inputs = []
        for i in range(2 if name == 'replicated snapshot' else 1):
            labels = '{job="temporal-worker",instance="worker-' + str(i) + '"}'
            inputs += [{'series': 'gradiated_training_completed_runs_1h{stage="failed",job="temporal-worker",instance="worker-' + str(i) + '"}', 'values': f'{failed}+0x40'},
                       {'series': 'gradiated_training_completed_runs_1h{stage="cancelled",job="temporal-worker",instance="worker-' + str(i) + '"}', 'values': f'{cancelled}+0x40'},
                       {'series': 'gradiated_training_metrics_available' + labels, 'values': f'{available}+0x40'},
                       {'series': 'gradiated_training_metrics_timestamp_seconds' + labels, 'values': timestamp}]
        scenario('Training failure ' + name, inputs, expected,
                 ['TrainingRunsFailed'], eval_time='8m')

    scenario('Training failure stale failed replica with fresh successful replica', [
        {'series': 'gradiated_training_completed_runs_1h{stage="failed",job="temporal-worker",instance="stale"}', 'values': '1+0x40'},
        {'series': 'gradiated_training_metrics_available{job="temporal-worker",instance="stale"}', 'values': '1+0x40'},
        {'series': 'gradiated_training_metrics_timestamp_seconds{job="temporal-worker",instance="stale"}', 'values': '0+0x40'},
        {'series': 'gradiated_training_completed_runs_1h{stage="failed",job="temporal-worker",instance="fresh"}', 'values': '0+0x40'},
        {'series': 'gradiated_training_metrics_available{job="temporal-worker",instance="fresh"}', 'values': '1+0x40'},
        {'series': 'gradiated_training_metrics_timestamp_seconds{job="temporal-worker",instance="fresh"}', 'values': '0+30x40'},
    ], None, ['TrainingRunsFailed'], eval_time='8m')

    # Temporal service alerts are disabled during bootstrap (replicas=0), tolerate
    # startup/drain windows and do not let another workload mask missing metrics.
    temporal_alerts = ['TemporalWorkerUnavailable', 'TemporalWorkerAvailabilityDegraded',
                       'TemporalWorkerTelemetryMissing', 'TemporalWorkerRpcFailures',
                       'TemporalWorkerWorkflowTaskFailures', 'TemporalWorkerActivityFailures',
                       'TemporalWorkerWorkflowQueueWait']
    def temporal_series(metric, values, selector='namespace="gradiated",pod="temporal-worker-a"'):
        return {'series': metric + '{' + selector + '}', 'values': values}

    def temporal_deployment(desired, available):
        return [temporal_series(metric, f'{value}+0x40',
                                'namespace="gradiated",deployment="temporal-worker"')
                for metric, value in [('kube_deployment_spec_replicas', desired),
                                      ('kube_deployment_status_replicas_available', available)]]

    for name, desired, available, up, expected, duration in [
        ('disabled', 0, 0, None, None, '16m'),
        ('healthy', 2, 2, 2, None, '16m'),
        ('starting within budget', 2, 0, None, None, '4m'),
        ('unavailable', 2, 0, None, 'TemporalWorkerUnavailable', '6m'),
        ('normal rollout', 2, 1, 1, None, '8m'),
        ('degraded redundancy', 2, 1, 1, 'TemporalWorkerAvailabilityDegraded', '11m'),
        ('metrics absent', 2, 2, None, 'TemporalWorkerTelemetryMissing', '6m'),
        ('all scrapes fail', 2, 2, 0, 'TemporalWorkerTelemetryMissing', '6m'),
        ('one scrape fails', 2, 2, 1, 'TemporalWorkerTelemetryMissing', '6m'),
        ('surge scrape', 2, 2, 3, None, '16m'),
    ]:
        inputs = temporal_deployment(desired, available)
        if up is not None:
            inputs += [temporal_series('up', '1+0x40',
                       f'namespace="gradiated",pod="temporal-worker-{i}"') for i in range(up)]
            if up == 0:
                inputs.append(temporal_series('up', '0+0x40'))
        inputs.append(temporal_series('up', '1+0x40', 'namespace="gradiated",pod="worker-other"'))
        scenario('Temporal ' + name, inputs, expected, temporal_alerts, eval_time=duration)

    for metric, alert, duration in [
        ('temporal_request_failure_total', 'TemporalWorkerRpcFailures', '11m'),
        ('temporal_long_request_failure_total', 'TemporalWorkerRpcFailures', '11m'),
        ('temporal_workflow_task_execution_failed_total', 'TemporalWorkerWorkflowTaskFailures', '11m'),
        ('temporal_activity_execution_failed_total', 'TemporalWorkerActivityFailures', '16m'),
    ]:
        for case, desired, values, selector, fires in [
            ('sustained', 2, '0+2x40', 'namespace="gradiated",pod="temporal-worker-a"', True),
            ('idle', 2, '0+0x40', 'namespace="gradiated",pod="temporal-worker-a"', False),
            ('isolated errors recovered', 2, '0+2x4 8+0x36', 'namespace="gradiated",pod="temporal-worker-a"', False),
            ('disabled', 0, '0+2x40', 'namespace="gradiated",pod="temporal-worker-a"', False),
            ('other workload', 2, '0+2x40', 'namespace="gradiated",pod="worker-other"', False),
        ]:
            inputs = temporal_deployment(desired, desired) + [
                temporal_series('up', '1+0x40', f'namespace="gradiated",pod="temporal-worker-{i}"')
                for i in range(desired)] + [temporal_series(metric, values, selector)]
            scenario('Temporal ' + metric + ' ' + case, inputs, alert if fires else None,
                     temporal_alerts, eval_time=duration)
    scenario('Temporal cancelled polls during shutdown', temporal_deployment(2, 2) + [
        temporal_series('up', '1+0x40', f'namespace="gradiated",pod="temporal-worker-{i}"') for i in range(2)
    ] + [temporal_series('temporal_long_request_failure_total', '0+2x40',
                       'namespace="gradiated",pod="temporal-worker-a",status_code="CANCELLED"')],
             None, temporal_alerts, eval_time='16m')

    for name, desired, samples, fast, fires in [('slow busy', 2, 2, 0, True),
                                              ('healthy busy', 2, 2, 2, False),
                                              ('slow sparse', 2, 0.1, 0, False),
                                              ('disabled', 0, 2, 0, False)]:
        selector = 'namespace="gradiated",pod="temporal-worker-a",task_queue="general"'
        metric = 'temporal_workflow_task_schedule_to_start_latency_seconds'
        inputs = temporal_deployment(desired, desired) + [
            temporal_series('up', '1+0x40', f'namespace="gradiated",pod="temporal-worker-{i}"') for i in range(desired)
        ] + [temporal_series(metric + '_bucket', f'0+{fast}x40', selector + ',le="30"'),
             temporal_series(metric + '_bucket', f'0+{samples}x40', selector + ',le="60"'),
             temporal_series(metric + '_bucket', f'0+{samples}x40', selector + ',le="+Inf"'),
             temporal_series(metric + '_count', f'0+{samples}x40', selector)]
        scenario('Temporal queue ' + name, inputs,
                 'TemporalWorkerWorkflowQueueWait' if fires else None, temporal_alerts,
                 {'task_queue': 'general'}, '16m')

    for name, available, desired, fires, duration in [
        ('full', 3, 3, False, '10m'),
        ('refilling', 1, 3, False, '5m'),
        ('depleted', 1, 3, True, '10m'),
        ('disabled intentionally', 0, 0, False, '10m'),
        ('missing deployment', None, None, True, '10m'),
    ]:
        labels = {'namespace': 'gradiated', 'deployment': 'scaling-headroom'}
        inputs = [] if available is None else [
            {'series': metric + '{namespace="gradiated",deployment="scaling-headroom"}',
             'values': f'{value}+0x30'} for metric, value in [
                 ('kube_deployment_status_replicas_available', available),
                 ('kube_deployment_spec_replicas', desired)]]
        scenario('headroom ' + name, inputs,
                 'ScalingHeadroomDepleted' if fires else None,
                 ['ScalingHeadroomDepleted'], labels, duration)

    for hpa, alert, eval_time, desired, limited, fires in [
        ('keda-hpa-api', 'AutoscalingLimited', '10m', 2, 1, False),
        ('keda-hpa-api', 'AutoscalingLimited', '10m', 20, 0, False),
        ('keda-hpa-api', 'AutoscalingLimited', '10m', 20, 1, True),
        ('keda-hpa-proxy', 'RequestPathAutoscalingLimited', '3m', 20, 1, True),
        ('keda-hpa-proxy', 'RequestPathAutoscalingLimited', '1m', 20, 1, False),
        ('keda-hpa-gateway', 'RequestPathAutoscalingLimited', '3m', 2, 1, False),
    ]:
        labels = {'namespace': 'gradiated', 'horizontalpodautoscaler': hpa}
        selector = f'namespace="gradiated",horizontalpodautoscaler="{hpa}"'
        inputs = [
            {'series': 'kube_horizontalpodautoscaler_status_desired_replicas{' + selector + '}',
             'values': f'{desired}+0x30'},
            {'series': 'kube_horizontalpodautoscaler_spec_max_replicas{' + selector + '}',
             'values': '20+0x30'},
            {'series': 'kube_horizontalpodautoscaler_status_condition{' + selector +
             ',condition="ScalingLimited",status="true"}', 'values': f'{limited}+0x30'},
        ]
        scenario(f'autoscaling cap {hpa} desired={desired} limited={limited} at {eval_time}', inputs,
                 alert if fires else None, [alert],
                 {**labels, 'condition': 'ScalingLimited', 'status': 'true'}, eval_time)

    controllers = [('keda', 'keda-operator'), ('keda', 'keda-operator-metrics-apiserver'),
                   ('kube-system', 'metrics-server'), ('kube-system', 'cluster-autoscaler')]
    for namespace, deployment in controllers:
        for available, duration, fires in [(None, '2m', True), (0, '2m', True),
                                           (0, '1m', False), (1, '2m', False)]:
            inputs = []
            for ns, name in controllers:
                value = available if (ns, name) == (namespace, deployment) else 2
                if value is not None:
                    inputs.append({'series': 'kube_deployment_status_replicas_available'
                                   + f'{{namespace="{ns}",deployment="{name}"}}',
                                   'values': f'{value}+0x8'})
            alert = 'AutoscalingControllerUnavailable'
            scenario(f'controller {deployment} available={available} duration={duration}', inputs,
                     alert if fires else None, [alert],
                     {'namespace': namespace, 'deployment': deployment}, duration)

    for missing in (None, 'api', 'gateway', 'proxy', 'worker', 'mcp'):
        inputs = [{'series': 'kube_horizontalpodautoscaler_spec_max_replicas'
                   + f'{{namespace="gradiated",horizontalpodautoscaler="keda-hpa-{service}"}}',
                   'values': '20+0x8'} for service in ('api', 'gateway', 'proxy', 'worker', 'mcp') if service != missing]
        alert = 'AutoscalerMissing'
        scenario(f'missing HPA {missing}', inputs, alert if missing else None, [alert],
                 {'namespace': 'gradiated', 'horizontalpodautoscaler': f'keda-hpa-{missing}'}, '2m')

    for condition in ('ScalingActive', 'AbleToScale'):
        for status, duration, fires in [('false', '2m', True), ('false', '1m', False), ('true', '2m', False)]:
            labels = {'namespace': 'gradiated', 'horizontalpodautoscaler': 'keda-hpa-gateway',
                      'condition': condition, 'status': status}
            selector = ','.join(f'{k}="{v}"' for k, v in labels.items())
            inputs = [{'series': 'kube_horizontalpodautoscaler_status_condition{' + selector + '}',
                       'values': '1+0x8'}]
            alert = 'AutoscalingUnavailable'
            scenario(f'HPA {condition}={status} duration={duration}', inputs,
                     alert if fires else None, [alert], labels, duration)

    for service, title, down in [('api', 'Api', 'ApiPublicUnavailable'),
                                 ('console', 'Console', 'ConsoleUnavailable'),
                                 ('mcp', 'Mcp', 'McpPublicUnavailable'),
                                 ('metabase', 'Metabase', 'MetabaseUnavailable'),
                                 ('proxy', 'Proxy', 'ProxyPublicUnavailable')]:
        missing = f'{title}ProbeMissing'
        for case, values, expected in [('healthy', '1+0x30', None),
                                       ('transient', '1+0x5 0 1+0x24', None),
                                       ('down', '0+0x30', down),
                                       ('recovered', '0+0x10 1+0x20', None),
                                       ('missing', None, missing)]:
            inputs = [] if values is None else [
                {'series': f'probe_success{{service="{service}"}}', 'values': values}]
            scenario(f'{service}: {case}', inputs, expected, [down, missing])

    stall = 'GatewayGenerationsStuck'
    active = {'series': 'gradiated_gateway_active_generations{deployment="stalled"}',
              'values': '1+0x30'}
    for name, inputs, fires in [
        ('first generation hangs before a terminal series exists', [active], True),
        ('terminal counter stopped', [active, {
            'series': 'gradiated_gateway_generations_total{deployment="stalled"}',
            'values': '4+0x30'}], True),
        ('another deployment cannot mask a stall', [active, {
            'series': 'gradiated_gateway_generations_total{deployment="healthy"}',
            'values': '0+1x30'}], True),
        ('making progress', [active, {
            'series': 'gradiated_gateway_generations_total{deployment="stalled"}',
            'values': '0+1x30'}], False),
        ('idle', [{'series': active['series'], 'values': '0+0x30'}], False),
        ('absent active telemetry is not a generation stall', [], False),
    ]:
        scenario(name, inputs, stall if fires else None, [stall], {'deployment': 'stalled'})

    replica_alert = 'DeploymentUnavailable'
    for name, available, desired, fires in [
        ('complete service outage', 0, 2, True),
        ('partial rollout retains capacity', 1, 2, False),
        ('healthy replicas', 2, 2, False),
        ('intentionally scaled to zero', 0, 0, False),
    ]:
        inputs = [{'series': metric + '{namespace="gradiated",deployment="api"}',
                   'values': f'{value}+0x30'} for metric, value in [
                       ('kube_deployment_status_replicas_available', available),
                       ('kube_deployment_spec_replicas', desired)]]
        inputs += [{'series': metric + '{namespace="gradiated",name="api"}', 'values': '0+0x30'}
                   for metric in ('rollout_info_replicas_available', 'rollout_info_replicas_desired')]
        scenario(name, inputs, replica_alert if fires else None, [replica_alert],
                 {'namespace': 'gradiated', 'deployment': 'api'})

    for name, available, fires in [('mcp outage', 0, True), ('mcp serving', 1, False)]:
        inputs = [{'series': metric + '{namespace="gradiated",deployment="mcp"}',
                   'values': f'{value}+0x30'} for metric, value in [
                       ('kube_deployment_status_replicas_available', available),
                       ('kube_deployment_spec_replicas', 2)]]
        scenario(name, inputs, replica_alert if fires else None, [replica_alert],
                 {'namespace': 'gradiated', 'deployment': 'mcp'})

    for name, old, candidate, fires in [('migration old serves', 3, 0, False),
                                        ('rollout serves', 0, 3, False),
                                        ('rollout outage', 0, 0, True)]:
        inputs = [{'series': f'{metric}{{namespace="gradiated",{label}="api"}}',
                   'values': f'{value}+0x30'} for metric, label, value in [
                       ('kube_deployment_status_replicas_available', 'deployment', old),
                       ('kube_deployment_spec_replicas', 'deployment', old),
                       ('rollout_info_replicas_available', 'name', candidate),
                       ('rollout_info_replicas_desired', 'name', 3)]]
        scenario(name, inputs, replica_alert if fires else None, [replica_alert],
                 {'namespace': 'gradiated', 'deployment': 'api'})

    for service, alert in [('api', 'ApiPublicUnavailable'),
                           ('console', 'ConsoleUnavailable'),
                           ('mcp', 'McpPublicUnavailable'),
                           ('proxy', 'ProxyPublicUnavailable')]:
        inputs = [{'series': f'probe_success{{service="{service}"}}',
                   'values': '1+0x5 0+0x30'}]
        scenario(f'{service} brief outage stays quiet', inputs, None, [alert], eval_time='4m')
        scenario(f'{service} outage fires after two minutes', inputs, alert, [alert], eval_time='5m')

    for alert, metric, threshold, hold, labels in [
        ('GenerationIngestionStuck',
         'gradiated_worker_ingestion_backlog{kind="oldest_pending_age_seconds"}', 300, '1m', {}),
        ('SettlementLagging', 'gradiated_worker_settlement_lag_seconds', 300, '2m', {}),
    ]:
        leader_input = ([{'series': 'gradiated_worker_settlement_leader', 'values': '1+0x30'}]
                        if alert == 'SettlementLagging' else [])
        scenario(alert + ' threshold stays quiet', [{'series': metric, 'values': f'{threshold}+0x30'}] + leader_input,
                 None, [alert], labels)
        inputs = [{'series': metric, 'values': f'{threshold+1}+0x30'}] + leader_input
        scenario(alert + ' does not fire immediately', inputs, None, [alert], labels, '0m')
        scenario(alert + ' fires at promised duration', inputs, alert, [alert], labels, hold)

    for alert, metric, failure_labels, success_labels, labels in [
        ('ApiSevereErrors', 'gradiated_api_http_requests_total',
         'route="/v1/test",status="500"', 'route="/v1/test",status="200"', {}),
        ('GatewaySevereErrors', 'gradiated_gateway_http_requests_total',
         'status="500"', 'status="200"', {}),
        ('GatewaySevereGenerationFailures', 'gradiated_gateway_generations_total',
         'deployment="bad",status="failed"', 'deployment="bad",status="succeeded"', {'deployment': 'bad'}),
    ]:
        for name, failed_values, ok_values, fires in [
            ('severe failures', '0+3x30', '0+1x30', True),
            ('isolated errors', '0+0x5 1+0x25', '0+3x30', False),
            ('healthy', '0+0x30', '0+3x30', False),
            ('high throughput moderate ratio', '0+3x30', '0+30x30', False),
        ]:
            inputs = [{'series': metric + '{' + failure_labels + '}', 'values': failed_values},
                      {'series': metric + '{' + success_labels + '}', 'values': ok_values}]
            if metric.startswith('gradiated_api'):
                inputs.append({'series': metric + '{route="/health/ready",status="200"}',
                               'values': '0+100x30'})
            if labels:
                inputs.append({'series': metric + '{deployment="healthy",status="succeeded"}',
                               'values': '0+100x30'})
            scenario(alert + ': ' + name, inputs, alert if fires else None, [alert], labels, '3m')

    for traffic, expected in [('verification', None), ('routed', 'GatewaySevereGenerationFailures')]:
        scenario('severe generation traffic classification: ' + traffic, [
            {'series': 'gradiated_gateway_generations_total{deployment="bad",status="failed",traffic="' + traffic + '"}', 'values': '0+3x30'},
            {'series': 'gradiated_gateway_generations_total{deployment="bad",status="succeeded",traffic="routed"}', 'values': '0+1x30'},
        ] + ([{'series': 'gradiated_gateway_generations_total{deployment="bad",status="succeeded",traffic="verification"}', 'values': '0+10000x30'}] if traffic == 'routed' else []), expected, ['GatewaySevereGenerationFailures'], {'deployment': 'bad'}, '3m')

    for alert, eval_time in [('GatewaySevereErrors', '3m'), ('GatewayHighErrorRate', '10m')]:
        for traffic, expected in [('verification', None), ('routed', alert)]:
            scenario('HTTP verification classification: ' + alert + traffic, [
                {'series': 'gradiated_gateway_http_requests_total{status="503",traffic="' + traffic + '"}', 'values': '0+3x30'},
                {'series': 'gradiated_gateway_http_requests_total{status="200",traffic="routed"}', 'values': '0+1x30'},
            ] + ([{'series': 'gradiated_gateway_http_requests_total{status="200",traffic="verification"}', 'values': '0+10000x30'}] if traffic == 'routed' else []), expected, [alert], {}, eval_time)

    scenario('legacy gateway HTTP metrics retain paging', [
        {'series': 'gradiated_gateway_http_requests_total{status="503"}', 'values': '0+3x30'},
        {'series': 'gradiated_gateway_http_requests_total{status="200"}', 'values': '0+1x30'},
    ], 'GatewayHighErrorRate', ['GatewayHighErrorRate'], {}, '10m')

    alb_errors = 'PublicLoadBalancerErrors'
    alb_series = 'aws_applicationelb_httpcode_elb_5_xx_count_sum{load_balancer="app/gradiated-prod-public-api/abc"}'
    for name, values, requests, eval_time, fires in [
        ('sustained ALB 5xx', '6+0x20', 150, '6m', True),
        ('below count threshold', '4+0x20', 150, '6m', False),
        ('small error fraction at high volume', '6+0x20', 1000, '6m', False),
        ('exactly one percent', '5+0x20', 500, '6m', False),
        ('just over one percent', '5+0x20', 495, '6m', True),
        ('ELB failures with no target requests', '6+0x20', None, '6m', True),
        ('one-minute spike', '6 6 stale', 150, '6m', False),
        ('no errors reported', None, 150, '6m', False),
    ]:
        inputs = [] if values is None else [{'series': alb_series, 'values': values}]
        if requests is not None:
            inputs.append({'series': 'aws_applicationelb_request_count_sum{load_balancer="app/gradiated-prod-public-api/abc"}',
                           'values': f'{requests}+0x20'})
        scenario('public load balancer: ' + name, inputs, alb_errors if fires else None,
                 [alb_errors], eval_time=eval_time)

    for result in ['full', 'too_large', 'closed', 'collector', 'unsupported', 'sent']:
        alert = 'ProxyCaptureDrops'
        inputs = [{'series': f'gradiated_proxy_captures_total{{result="{result}"}}',
                   'values': '0+1x30'}]
        scenario('capture drops: ' + result, inputs, alert if result != 'sent' else None,
                 [alert], eval_time='2m')
    scenario('capture drops: isolated event',
             [{'series': 'gradiated_proxy_captures_total{result="collector"}',
               'values': '0+0x5 1+0x25'}], None, ['ProxyCaptureDrops'], eval_time='5m')

    proxy_errors = 'ProxyHighErrorRate'
    for name, failed, ok, destination, fires in [
        ('3% gateway failures', 9, 291, 'gateway', True),
        ('3% proxy failures', 9, 291, 'local', True),
        ('1% gateway failures', 3, 297, 'gateway', False),
        ('healthy', 0, 3000, 'gateway', False),
        ('provider failures on relays are excluded', 300, 3000, 'anthropic', False),
        ('low traffic stays quiet', 1, 0, 'local', False),
    ]:
        inputs = [{'series': f'gradiated_proxy_requests_total{{destination="{destination}",status="500"}}',
                   'values': f'0+{failed}x30'},
                  {'series': 'gradiated_proxy_requests_total{destination="gateway",status="200"}',
                   'values': f'0+{ok}x30'}]
        scenario('proxy errors: ' + name, inputs, proxy_errors if fires else None, [proxy_errors], eval_time='5m')

    proxy_4xx = 'ProxyHigh4xxRate'
    for name, refused, ok, destination, fires in [
        ('15% proxy 4xx', 45, 255, 'local', True),
        ('5% proxy 4xx', 15, 285, 'local', False),
        ('gateway 4xx are excluded', 150, 150, 'gateway', False),
        ('low traffic stays quiet', 1, 0, 'local', False),
    ]:
        inputs = [{'series': f'gradiated_proxy_requests_total{{destination="{destination}",status="401"}}',
                   'values': f'0+{refused}x30'},
                  {'series': 'gradiated_proxy_requests_total{destination="gateway",status="200"}',
                   'values': f'0+{ok}x30'}]
        scenario('proxy 4xx: ' + name, inputs, proxy_4xx if fires else None, [proxy_4xx], eval_time='12m')

    capacity = 'ProxyNearCapacity'
    for name, in_flight, fires in [('above 80%', 3300, True), ('below 80%', 3000, False)]:
        inputs = [{'series': f'gradiated_proxy_in_flight{{pod="proxy-a",destination="{destination}"}}',
                   'values': f'{in_flight // 2}+0x30'} for destination in ('gateway', 'anthropic')]
        scenario('proxy capacity: ' + name, inputs, capacity if fires else None, [capacity],
                 {'pod': 'proxy-a'}, '5m')

    oom = 'ContainerOOMKilled'
    container = 'namespace="gradiated",pod="proxy-a",container="proxy"'
    for name, reason, fires in [('out-of-memory restart', 'OOMKilled', True),
                                ('restart without out-of-memory kill', 'Error', False)]:
        inputs = [{'series': 'kube_pod_container_status_last_terminated_reason{' + container + f',reason="{reason}"}}',
                   'values': '1+0x20'},
                  {'series': 'kube_pod_container_status_restarts_total{' + container + '}',
                   'values': '0+0x5 1+0x14'}]
        scenario('OOM: ' + name, inputs, oom if fires else None, [oom],
                 {'namespace': 'gradiated', 'pod': 'proxy-a', 'container': 'proxy', 'reason': 'OOMKilled'}, '4m')
    scenario('OOM: old kill without a recent restart', [
        {'series': 'kube_pod_container_status_last_terminated_reason{' + container + ',reason="OOMKilled"}',
         'values': '1+0x40'},
        {'series': 'kube_pod_container_status_restarts_total{' + container + '}', 'values': '1+0x40'},
    ], None, [oom], eval_time='15m')

    memory = 'ContainerMemoryHigh'
    for name, used, fires in [('above 85%', 900, True), ('below 85%', 700, False)]:
        inputs = [{'series': 'container_memory_working_set_bytes{' + container + ',image="proxy"}',
                   'values': f'{used}+0x30'},
                  {'series': 'kube_pod_container_resource_limits{' + container + ',resource="memory"}',
                   'values': '1000+0x30'}]
        scenario('memory: ' + name, inputs, memory if fires else None, [memory],
                 {'namespace': 'gradiated', 'pod': 'proxy-a', 'container': 'proxy'}, '8m')

    collector_telemetry = 'CollectorTelemetryMissing'
    scenario('collector telemetry present', [{'series': 'gradiated_collector_service_info{pod="collector-0"}', 'values': '1+0x30'}],
             None, [collector_telemetry], eval_time='5m')
    scenario('collector telemetry missing', [{'series': 'gradiated_worker_service_info{instance="a"}', 'values': '1+0x30'}],
             collector_telemetry, [collector_telemetry], eval_time='5m')

    collector_ready = 'CollectorUnavailable'
    for name, ready, fires in [('no ready replica', 0, True), ('one ready replica', 1, False)]:
        scenario('collector ' + name, [
            {'series': 'kube_deployment_status_replicas_available{namespace="gradiated",deployment="collector"}',
             'values': f'{ready}+0x30'}], collector_ready if fires else None, [collector_ready], eval_time='8m')

    uploads = 'CollectorUploadsFailing'
    for name, values, fires in [('failing for five minutes', '0+2x30', True), ('no failures', '0+0x30', False),
                                ('one failure then recovery', '0 1+0x29', False)]:
        scenario('collector uploads ' + name, [
            {'series': 'gradiated_collector_upload_failures_total{pod="collector-0"}', 'values': values}],
            uploads if fires else None, [uploads], eval_time='12m')

    disk = 'CollectorDiskHigh'
    for name, used, fires in [('above 80%', 2_600_000_000, True), ('below 80%', 2_500_000_000, False)]:
        scenario('collector disk ' + name, [
            {'series': 'gradiated_collector_disk_bytes{pod="collector-0"}', 'values': f'{used}+0x30'}],
            disk if fires else None, [disk], eval_time='8m')

    rejecting = 'CollectorRejectingContents'
    for name, reason, fires in [('disk full', 'disk_full', True), ('invalid records only', 'invalid', False)]:
        scenario('collector rejecting ' + name, [
            {'series': f'gradiated_collector_contents_rejected_total{{pod="collector-0",reason="{reason}"}}',
             'values': '0+5x30'}], rejecting if fires else None, [rejecting], eval_time='12m')

    for name, desired, ready, expected, duration in [
        ('healthy', 2, '2+0x80', None, '15m'),
        ('zero allocations and no readiness series', 2, None, 'ModelNoReadyReplicas', '6m'),
        ('running but not ready', 2, '0+0x80', 'ModelNoReadyReplicas', '6m'),
        ('missing job after serving', 2, '2+0x4 stale', 'ModelNoReadyReplicas', '10m'),
        ('partial capacity', 2, '1+0x80', 'ModelUnderReplicated', '11m'),
        ('brief restart', 2, '2+0x4 0+0x4 2+0x70', None, '15m'),
        ('recovered', 2, '0+0x20 2+0x60', None, '15m'),
        ('disabled in Git', 0, None, None, '15m'),
    ]:
        inputs = [{'series': 'gradiated_model_desired_replicas{model="kev/kev-9b",rollout="kev"}', 'values': f'{desired}+0x80'},
                  {'series': 'gradiated_model_minimum_replicas{model="kev/kev-9b",rollout="kev"}', 'values': f'{desired}+0x80'}]
        if ready is not None:
            inputs.append({'series': 'gradiated_worker_model_ready_replicas{instance="a",model="kev/kev-9b"}', 'values': ready})
            inputs.append({'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="a",loop="kubernetes_deployment_reconciliation"}', 'values': '1+30x80'})
        scenario('model replicas: ' + name, inputs, expected,
                 ['ModelNoReadyReplicas', 'ModelUnderReplicated'], {'model': 'kev/kev-9b'}, duration)

    for name, ready, expected, duration in [
        ('normal replica warmup', 2, None, '19m'),
        ('capacity never arrives', 2, 'ModelScaleUpStalled', '21m'),
        ('minimum lost during scale-up', 1, 'ModelUnderReplicated', '1m'),
        ('scale-up has completed', 3, None, '21m'),
    ]:
        scenario('autoscaled capacity: ' + name, [
            {'series': 'gradiated_model_desired_replicas{model="test/model"}', 'values': '3+0x80'},
            {'series': 'gradiated_model_minimum_replicas{model="test/model"}', 'values': '2+0x80'},
            {'series': 'gradiated_worker_model_ready_replicas{instance="a",model="test/model"}', 'values': f'{ready}+0x80'},
            {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="a",loop="kubernetes_deployment_reconciliation"}', 'values': '1+30x80'},
        ], expected, ['ModelNoReadyReplicas', 'ModelUnderReplicated', 'ModelScaleUpStalled'],
        {'model': 'test/model'}, duration)

    alerts_checked = ['ModelNoReadyReplicas', 'ModelUnderReplicated', 'ModelScaleUpStalled']
    worker_fresh = {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="a",loop="kubernetes_deployment_reconciliation"}',
                    'values': '1+30x80'}

    def pools(*targets, ready=None):
        """Per-pool desired and minimum replicas for one model, as the renderer records them."""
        series = []
        for rollout, desired, minimum in targets:
            series += [{'series': f'gradiated_model_desired_replicas{{model="test/model",rollout="{rollout}"}}', 'values': f'{desired}+0x80'},
                       {'series': f'gradiated_model_minimum_replicas{{model="test/model",rollout="{rollout}"}}', 'values': f'{minimum}+0x80'}]
        if ready is not None:
            series.append({'series': 'gradiated_worker_model_ready_replicas{instance="a",model="test/model"}', 'values': f'{ready}+0x80'})
        return series + [worker_fresh]

    # The floor fills pools in order, so one model's minimum can span pools.
    for name, ready, expected, duration in [
        ('both pools at their floor', 7, None, '21m'),
        ('the second pool loses its floor replica', 6, 'ModelUnderReplicated', '1m'),
        ('overflow pool warming above the floor', 7, None, '19m'),
        ('overflow pool never arrives', 7, 'ModelScaleUpStalled', '21m'),
        ('overflow pool serving', 9, None, '21m'),
    ]:
        overflow = 2 if name.startswith('overflow') else 0
        scenario('pooled capacity: ' + name, pools(('b300', 5, 5), ('h200', 2, 2), ('spill', overflow, 0), ready=ready),
                 expected, alerts_checked, {'model': 'test/model'}, duration)

    # A model whose floor is zero scales from zero on demand without paging.
    for name, desired, ready, expected, duration in [
        ('idle at zero', 0, None, None, '21m'),
        ('first replica warming', 1, None, None, '19m'),
        ('first replica never arrives', 1, None, 'ModelScaleUpStalled', '21m'),
        ('first replica serving', 1, 1, None, '21m'),
    ]:
        scenario('scale from zero: ' + name, pools(('pool', desired, 0), ready=ready),
                 expected, alerts_checked, {'model': 'test/model'}, duration)

    scenario('qualification and switched-off pools add no capacity demand',
             pools(('serving', 10, 10), ('qualification', 0, 0), ('off', 0, 0), ready=10),
             None, alerts_checked, {'model': 'test/model'}, '21m')

    probe_labels = '{instance="a",model="test/model"}'
    def probe_series(metric, values, labels=probe_labels):
        return {'series': metric + labels, 'values': values}

    probe_alerts = ['InferenceModelProbeFailed', 'InferenceProbeMonitoringStalled']
    for name, success, inventory, target, expected, duration in [
        ('healthy', '1+5x30', '1+5x30', '1+0x30', None, '60s'),
        ('never completed', '0+0x30', '1+5x30', '1+0x30', 'InferenceModelProbeFailed', '80s'),
        ('stops completing', '1+0x30', '1+5x30', '1+0x30', 'InferenceModelProbeFailed', '80s'),
        ('short transient', '1 1 1 16+5x27', '1+5x30', '1+0x30', None, '30s'),
        ('monitor stopped', '1+0x30', '1+0x30', '1+0x30', 'InferenceProbeMonitoringStalled', '95s'),
        ('retired target', '1+0x30', '1+5x30', '1+0x2 stale', None, '60s'),
    ]:
        scenario('public inference: ' + name, [
            probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', success),
            probe_series('gradiated_inference_routed_probe_target', target),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', inventory, '{instance="a"}'),
            probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
        ], expected, probe_alerts,
        {'model': 'test/model'} if expected == 'InferenceModelProbeFailed' else {},
        duration, interval='5s')

    scenario('public inference: slow ten-second phases keep monitoring fresh', [
        probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds',
                     ' '.join(str(1 + (i // 5) * 25) for i in range(61))),
        probe_series('gradiated_inference_routed_probe_target', '1+0x60'),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds',
                     ' '.join(str(1 + (i // 5) * 25) for i in range(61)), '{instance="a"}'),
        probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x60', '{instance="a"}'),
    ], None, probe_alerts, eval_time='5m', interval='5s')

    # A recovery shorter than five minutes must not close/reopen the model alert.
    recovery_success = ' '.join(str(0 if t < 90 else 100 if 115 <= t < 205 else t)
                                for t in range(0, 511, 5))
    for duration, expected in [('75s', None), ('80s', probe_alerts[0]),
                               ('90s', probe_alerts[0]), ('200s', probe_alerts[0]),
                               ('500s', probe_alerts[0]), ('505s', None)]:
        scenario('public inference: five-minute recovery hold at ' + duration, [
            probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', recovery_success),
            probe_series('gradiated_inference_routed_probe_target', '1+0x103'),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x103', '{instance="a"}'),
            probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
            probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x103',
                         probe_labels.replace('test/model', 'healthy/model')),
            probe_series('gradiated_inference_routed_probe_target', '1+0x103',
                         probe_labels.replace('test/model', 'healthy/model')),
        ], expected, probe_alerts, {'model': 'test/model'},
           duration, interval='5s')

    scenario('public inference: missing telemetry', [], 'InferenceProbeMonitoringStalled',
             ['InferenceProbeMonitoringStalled'], eval_time='65s', interval='5s')
    scenario('public inference: replacement leader masks stale failed worker', [
        probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '0+0x30'),
        probe_series('gradiated_inference_routed_probe_target', '1+0x30'),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+0x30', '{instance="a"}'),
        probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
        probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x30', probe_labels.replace('"a"', '"b"')),
        probe_series('gradiated_inference_routed_probe_target', '1+0x30', probe_labels.replace('"a"', '"b"')),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x30', '{instance="b"}'),
        probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="b"}'),
    ], None, probe_alerts, eval_time='60s', interval='5s')

    for name, include_target, include_success in [
        ('missing routed gauges', False, False),
        ('missing routed target', False, True),
        ('missing routed success', True, False),
    ]:
        inputs = [
            probe_series('gradiated_inference_probe_target', '1+0x30',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_probe_last_success_timestamp_seconds', '1+5x30',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x30', '{instance="a"}'),
            probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
        ]
        if include_target:
            inputs.append(probe_series('gradiated_inference_routed_probe_target', '1+0x30'))
        if include_success:
            inputs.append(probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x30'))
        scenario('routed monitoring: ' + name, inputs, 'InferenceProbeMonitoringStalled',
                 probe_alerts, {'model': 'test/model'}, '65s', interval='5s')

    scenario('routed monitoring: rollback cannot use the old leader gauges', [
        probe_series('gradiated_inference_routed_probe_target', '1+0x30'),
        probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x30'),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+0x30', '{instance="a"}'),
        probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
        probe_series('gradiated_inference_probe_target', '1+0x30',
                     '{instance="b",model="test/model",deployment="test-deployment"}'),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x30', '{instance="b"}'),
        probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="b"}'),
    ], 'InferenceProbeMonitoringStalled', probe_alerts, {'model': 'test/model'}, '100s', interval='5s')

    for healthy in (False, True):
        inputs = [
            probe_series('gradiated_inference_catalog_model_target', '1+0x30',
                         '{instance="catalog",model="test/model"}'),
            probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x30', '{instance="catalog"}'),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x30', '{instance="a"}'),
        ]
        if healthy:
            inputs.extend([
                probe_series('gradiated_inference_routed_probe_target', '1+0x30'),
                probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x30'),
            ])
        scenario('zero-replica routed watchdog: ' + str(healthy), inputs,
                 None if healthy else 'InferenceProbeMonitoringStalled',
                 probe_alerts, {'model': 'test/model'}, '65s', interval='5s')

    scenario('catalog watchdog: all workers rolled back to older instrumentation', [
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x30', '{instance="a"}'),
    ], 'InferenceProbeMonitoringStalled', probe_alerts, eval_time='65s', interval='5s')

    assert alerts['InferenceDeploymentProbeFailed']['labels']['severity'] == 'warning'
    assert alerts['InferenceDeploymentProbeFailed']['for'] == '1m'
    assert alerts['InferenceModelProbeFailed']['labels']['severity'] == 'critical'
    for duration, expected in [('30s', None), ('1m30s', None), ('2m', None), ('2m30s', 'InferenceDeploymentProbeFailed')]:
        scenario('targeted replica warning: ' + duration, [
            probe_series('gradiated_inference_probe_last_success_timestamp_seconds', '0+0x80',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_probe_target', '1+0x80',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_probe_discovered_timestamp_seconds', '1+0x80',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x80'),
            probe_series('gradiated_inference_routed_probe_target', '1+0x80'),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x80', '{instance="a"}'),
            probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
        ], expected, ['InferenceDeploymentProbeFailed', 'InferenceModelProbeFailed'],
           {'model': 'test/model', 'deployment': 'test-deployment'}, duration, interval='5s')

    scenario('healthy minute-spaced targeted checks never warn', [
        probe_series('gradiated_inference_probe_last_success_timestamp_seconds',
                     ' '.join(f'{1 + (i // 12) * 60}' for i in range(161)),
                     '{instance="a",model="test/model",deployment="test-deployment"}'),
        probe_series('gradiated_inference_probe_target', '1+0x160',
                     '{instance="a",model="test/model",deployment="test-deployment"}'),
        probe_series('gradiated_inference_probe_discovered_timestamp_seconds', '1+0x160',
                     '{instance="a",model="test/model",deployment="test-deployment"}'),
        probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x160'),
        probe_series('gradiated_inference_routed_probe_target', '1+0x160'),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x160', '{instance="a"}'),
        probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
    ], None, ['InferenceDeploymentProbeFailed', 'InferenceModelProbeFailed'],
       eval_time='13m', interval='5s')

    for duration, expected in [('2m', None), ('3m', None), ('3m30s', 'InferenceDeploymentProbeFailed')]:
        scenario('new targeted replica receives two attempts before warning: ' + duration, [
            probe_series('gradiated_inference_probe_last_success_timestamp_seconds', '0+0x80',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_probe_target', '_x12 1+0x68',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_probe_discovered_timestamp_seconds', '_x12 61+0x68',
                         '{instance="a",model="test/model",deployment="test-deployment"}'),
            probe_series('gradiated_inference_routed_probe_last_success_timestamp_seconds', '1+5x80'),
            probe_series('gradiated_inference_routed_probe_target', '1+0x80'),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x80', '{instance="a"}'),
            probe_series('gradiated_inference_catalog_inventory_timestamp_seconds', '1+5x200', '{instance="a"}'),
        ], expected, ['InferenceDeploymentProbeFailed', 'InferenceModelProbeFailed'],
           {'model': 'test/model', 'deployment': 'test-deployment'}, duration, interval='5s')

    for ready, expected, duration in [(0, 'ModelNoReadyReplicas', '60s'), (1, 'ModelUnderReplicated', '30s')]:
        scenario('fast capacity alert: ' + expected, [
            {'series': 'gradiated_model_desired_replicas{model="test/model"}', 'values': '2+0x20'},
            {'series': 'gradiated_model_minimum_replicas{model="test/model"}', 'values': '2+0x20'},
            {'series': 'gradiated_worker_model_ready_replicas{instance="a",model="test/model"}', 'values': f'{ready}+0x20'},
            {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="a",loop="kubernetes_deployment_reconciliation"}', 'values': '1+5x20'},
        ], expected, ['ModelNoReadyReplicas', 'ModelUnderReplicated'], {'model': 'test/model'}, duration, interval='5s')

    scenario('stale healthy worker cannot hide unavailable model', [
        {'series': 'gradiated_model_desired_replicas{model="test/model"}', 'values': '2+0x20'},
            {'series': 'gradiated_model_minimum_replicas{model="test/model"}', 'values': '2+0x20'},
        {'series': 'gradiated_worker_model_ready_replicas{instance="old",model="test/model"}', 'values': '2+0x20'},
        {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="old",loop="kubernetes_deployment_reconciliation"}', 'values': '1+0x20'},
        {'series': 'gradiated_worker_model_ready_replicas{instance="new",model="test/model"}', 'values': '0+0x20'},
        {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="new",loop="kubernetes_deployment_reconciliation"}', 'values': '1+5x20'},
    ], 'ModelNoReadyReplicas', ['ModelNoReadyReplicas'], {'model': 'test/model'}, '90s', interval='5s')

    for failed, succeeded, expected in [('0+6x60', '0+100x60', 'GatewayRuntimeFailures'),
                                        ('0+0x60', '0+100x60', None),
                                        ('0 1+0x59', '0+100x60', None)]:
        scenario('per-deployment runtime failures: ' + failed, [
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="failed"}', 'values': failed},
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="succeeded"}', 'values': succeeded},
            {'series': 'gradiated_gateway_generations_total{model="other/model",deployment="healthy-deployment",status="succeeded"}', 'values': '0+100000x60'},
        ], expected, ['GatewayRuntimeFailures'], {'model': 'test/model', 'deployment': 'test-deployment'}, '2m', interval='5s')

    for traffic, expected in [('verification', None), ('routed', 'GatewayRuntimeFailures')]:
        scenario('verification traffic does not page: ' + traffic, [
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="failed",error="runtime_unavailable",traffic="' + traffic + '"}', 'values': '0+6x60'},
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="succeeded",traffic="routed"}', 'values': '0+100x60'},
        ] + ([{'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="succeeded",traffic="verification"}', 'values': '0+100000x60'}] if traffic == 'routed' else []), expected, ['GatewayRuntimeFailures'], {'model': 'test/model', 'deployment': 'test-deployment'}, '2m', interval='5s')

    for alert, labels, ratio, window, succeeded in [
        ('GatewayRuntimeFailures', {'model': 'test/model', 'deployment': 'bad'}, 6, '2m', 100),
        ('GatewaySevereGenerationFailures', {'deployment': 'bad'}, 3, '3m', 1),
    ]:
        prefix = 'gradiated_gateway_generations_total{model="test/model",deployment="bad",traffic="routed",'
        capacity = {'series': prefix + 'status="failed",error="capacity_exceeded"}', 'values': '0+10000x60'}
        success = {'series': prefix + 'status="succeeded"}', 'values': f'0+{succeeded}x60'}
        scenario(alert + ' ignores capacity rejections', [capacity, success], None, [alert], labels, window, interval='5s')
        scenario(alert + ' capacity cannot dilute real faults', [capacity, success,
            {'series': prefix + 'status="failed",error="runtime_unavailable"}', 'values': f'0+{ratio}x60'},
        ], alert, [alert], labels, window, interval='5s')

    for source in ['routing', 'runtime', 'streaming']:
        for rejected, succeeded, expected in [(4, 96, None), (5, 95, None),
                (6, 94, 'GatewayCapacityRejections'), (100, 0, 'GatewayCapacityRejections')]:
            for traffic in ['routed', 'verification', None]:
                traffic_label = ',traffic="' + traffic + '"' if traffic else ''
                metric = ('gradiated_gateway_routing_capacity_rejections_total{model="test/model"'
                          if source == 'routing' else
                          'gradiated_gateway_generations_total{model="test/model",deployment="bad",status="failed",error="capacity_exceeded",stream="' + str(source == 'streaming').lower() + '"')
                scenario('capacity ratio: ' + str((source, rejected, traffic)), [
                    {'series': metric + traffic_label + '}', 'values': f'0+{rejected}x60'},
                    {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="good",status="succeeded",traffic="routed"}', 'values': f'0+{succeeded}x60'},
                    {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="verified",status="succeeded",traffic="verification"}', 'values': '0+100000x60'},
                    {'series': 'gradiated_gateway_http_requests_total{route="chat_completions",status="200",error="none",traffic="routed"}', 'values': '0+100000x60'},
                ], None if traffic == 'verification' else expected,
                   ['GatewayCapacityRejections'], eval_time='2m', interval='5s')

    scenario('routing and terminal capacity requests combine once', [
        {'series': 'gradiated_gateway_routing_capacity_rejections_total{model="test/model",traffic="routed"}', 'values': '0+3x60'},
        {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="bad",status="failed",error="capacity_exceeded",traffic="routed"}', 'values': '0+3x60'},
        {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="good",status="succeeded",traffic="routed"}', 'values': '0+94x60'},
    ], 'GatewayCapacityRejections', ['GatewayCapacityRejections'], eval_time='2m', interval='5s')
    scenario('HTTP 429 and terminal outcome are not counted twice', [
        {'series': 'gradiated_gateway_http_requests_total{route="chat_completions",status="429",error="capacity_exceeded",traffic="routed"}', 'values': '0+4x60'},
        {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="bad",status="failed",error="capacity_exceeded",traffic="routed"}', 'values': '0+4x60'},
        {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="good",status="succeeded",traffic="routed"}', 'values': '0+96x60'},
    ], None, ['GatewayCapacityRejections'], eval_time='2m', interval='5s')
    scenario('other rate limits and faults are not capacity rejections', [
        {'series': 'gradiated_gateway_http_requests_total{route="chat_completions",status="429",error="concurrency_exceeded",traffic="routed"}', 'values': '0+100x60'},
        {'series': 'gradiated_gateway_admission_rejections_total{model="test/model",deployment="bad",reason="concurrency_exceeded"}', 'values': '0+100x60'},
        {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="bad",status="failed",error="runtime_unavailable",traffic="routed"}', 'values': '0+100x60'},
    ], None, ['GatewayCapacityRejections'], eval_time='2m', interval='5s')

    for name, values, eval_time, expected in [
        ('one rejection stays quiet', '0 1+0x59', '2m', None),
        ('below sample floor', '0 0 4+0x58', '2m', None),
        ('sample floor', '0 0 5+0x58', '2m', 'GatewayCapacityRejections'),
        ('brief burst', '0+6x60', '30s', None),
        ('recovery', '0+6x24 144+0x96', '10m', None),
    ]:
        scenario('capacity rejection persistence: ' + name, [
            {'series': 'gradiated_gateway_routing_capacity_rejections_total{model="test/model",traffic="routed"}', 'values': values},
        ], expected, ['GatewayCapacityRejections'], eval_time=eval_time, interval='5s')

    for values in [None, '0+0x60']:
        inputs = [{'series': 'gradiated_gateway_generations_total{model="test/model",deployment="good",status="succeeded",traffic="routed"}', 'values': '0+10x60'}]
        if values:
            inputs.append({'series': 'gradiated_gateway_routing_capacity_rejections_total{model="test/model",traffic="routed"}', 'values': values})
        scenario('capacity rejection idle or missing: ' + str(values), inputs,
                 None, ['GatewayCapacityRejections'], eval_time='2m', interval='5s')

    for failed, succeeded, expected in [(4, 96, None), (5, 95, None), (6, 94, 'GatewayRuntimeFailures')]:
        scenario('five-percent runtime failure boundary: ' + str((failed, succeeded)), [
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="failed",traffic="routed"}', 'values': f'0+{failed}x60'},
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="succeeded",traffic="routed"}', 'values': f'0+{succeeded}x60'},
        ], expected, ['GatewayRuntimeFailures'], {'model': 'test/model', 'deployment': 'test-deployment'}, '2m', interval='5s')

    route = 'route="/v1/deployment-status"'
    for name, values, fires in [
        ('continuous rejections', '0+60x30', True),
        ('a short burst while a new replica registers', '0+5x2 10+0x28', False),
    ]:
        scenario(f'status reports rejected: {name}', [
            {'series': f'gradiated_api_http_requests_total{{instance="a",method="POST",{route},status="404"}}', 'values': values},
        ], 'DeploymentStatusRejected' if fires else None, ['DeploymentStatusRejected'], {'status': '404'}, eval_time='14m')

    leader_alert = 'SettlementLeaderMissing'
    for name, leader_value, fires in [('no leader', 0, True), ('leader exists', 1, False)]:
        scenario(name, [
            {'series': 'gradiated_worker_service_info{instance="a"}', 'values': '1+0x30'},
            {'series': 'gradiated_worker_settlement_leader{instance="a"}', 'values': f'{leader_value}+0x30'},
        ], leader_alert if fires else None, [leader_alert], eval_time='2m')
    scenario('old worker during mixed-version rollout', [
        {'series': 'gradiated_worker_service_info{instance="old"}', 'values': '1+0x30'},
        {'series': 'gradiated_worker_service_info{instance="new"}', 'values': '1+0x30'},
        {'series': 'gradiated_worker_settlement_leader{instance="new"}', 'values': '0+0x30'},
    ], None, [leader_alert])
    scenario('standby heartbeat cannot mask stalled settlement leader', [
        {'series': 'gradiated_worker_settlement_leader{instance="leader"}', 'values': '1+0x30'},
        {'series': 'gradiated_worker_settlement_leader{instance="standby"}', 'values': '0+0x30'},
        {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="leader",loop="settlement"}', 'values': '0+0x30'},
        {'series': 'gradiated_worker_loop_last_success_timestamp_seconds{instance="standby",loop="settlement"}', 'values': '0+30x30'},
    ], 'WorkerLoopStalled', ['WorkerLoopStalled'], {'loop': 'settlement'})

    for alert, metric in [
        ('GatewayFinalizationFailure', 'gradiated_gateway_last_finalization_failure_timestamp_seconds'),
    ]:
        for name, values, eval_time, fires in [
            ('first event before first scrape', '60+0x30', '2m', True),
            ('no prior event', '0+0x30', '2m', False),
            ('event ages out', '60+0x30', '8m', False),
            ('new process has no inherited event', '0+0x30', '8m', False),
        ]:
            scenario(alert + ': ' + name, [{'series': metric, 'values': values}],
                     alert if fires else None, [alert], eval_time=eval_time)

    for name, values, fires in [
        ('sustained rejection', '0+1x60', True),
        ('single rejection', '0 1+0x59', False),
        ('short burst', '0 10+0x59', False),
        ('no rejection', '0+0x60', False),
    ]:
        scenario('settlement backpressure: ' + name, [
            {'series': 'gradiated_gateway_admission_rejections_total{reason="settlement_backlog"}',
             'values': values},
        ], 'SettlementBackpressure' if fires else None, ['SettlementBackpressure'],
           eval_time='2m', interval='5s')

    app_alert = 'ApplicationReconciliationFailed'
    for name, health, sync, auto, fires in [
        ('healthy', 'Healthy', 'Synced', 'true', False),
        ('degraded', 'Degraded', 'Synced', 'true', True),
        ('missing automatic application', 'Missing', 'Synced', 'true', True),
        ('manual application staged but not deployed', 'Missing', 'OutOfSync', 'false', False),
        ('degraded manual application', 'Degraded', 'Synced', 'false', True),
        ('unknown manual application', 'Unknown', 'OutOfSync', 'false', True),
        ('automatic sync stalled', 'Healthy', 'OutOfSync', 'true', True),
        ('intentional manual drift', 'Healthy', 'OutOfSync', 'false', False),
    ]:
        inputs = [{'series': f'argocd_app_info{{name="api",health_status="{health}",sync_status="{sync}",autosync_enabled="{auto}"}}', 'values': '1+0x40'}]
        scenario('Argo ' + name, inputs, app_alert if fires else None, [app_alert], {'name': 'api'}, '16m')
    scenario('ordinary deployment converges before warning', [
        {'series': 'argocd_app_info{name="api",health_status="Healthy",sync_status="OutOfSync",autosync_enabled="true"}', 'values': '1+0x8 stale'},
        {'series': 'argocd_app_info{name="api",health_status="Healthy",sync_status="Synced",autosync_enabled="true"}', 'values': '_ _ _ _ _ _ _ _ _ 1+0x31'},
    ], None, [app_alert], eval_time='16m')
    host_service_alert = 'GpuHostServiceMissing'
    inventory = [{'series': f'gradiated_gpu_host_last_seen_seconds{{instance_id="test-host",pod="controller-{pod}"}}',
                  'values': '0+0x40'} for pod in ('a', 'b')]
    service = {'series': 'kube_service_info{namespace="tailscale-inference",service="gpu-test-host"}',
               'values': '1+0x40'}
    scraped = {'series': 'up{job="kube-state-metrics"}', 'values': '1+0x40'}
    for name, services, up, eval_time, fires in [
        ('never-seen host missing Service', [], scraped, '6m', True),
        ('Service present', [service], scraped, '6m', False),
        ('brief enrollment delay', [], scraped, '4m', False),
        ('deleted Service remains missing', [{**service, 'values': '1+0x4 stale'}], scraped, '8m', True),
        ('Service restored after firing', [{**service, 'values': '_x14 1+0x26'}], scraped, '8m', False),
        ('Service in wrong namespace', [{**service, 'series': service['series'].replace('tailscale-inference', 'other')}], scraped, '6m', True),
        ('another host cannot mask missing Service', [{**service, 'series': service['series'].replace('gpu-test-host', 'gpu-other-host')}], scraped, '6m', True),
        ('operator proxy cannot mask missing Service', [{**service, 'series': service['series'].replace('gpu-test-host', 'ts-gpu-test-host-proxy')}], scraped, '6m', True),
        ('Kubernetes state scrape failed', [], {**scraped, 'values': '0+0x40'}, '6m', False),
        ('Kubernetes state scrape absent', [], None, '6m', False),
    ]:
        scenario('GPU host Service ' + name, inventory + services + ([up] if up else []),
                 host_service_alert if fires else None, [host_service_alert],
                 {'instance_id': 'test-host'} if fires else None, eval_time)
    scenario('GPU host removed from inventory', [scraped], None, [host_service_alert], eval_time='6m')

    rollout_alert = 'GpuRolloutFailed'
    for name, phase, fires in [('completed', 'Completed', False), ('progressing', 'Progressing', False), ('paused', 'Paused', False),
                               ('aborted', 'Abort', True), ('deadline exceeded', 'Timeout', True), ('reconcile error', 'Error', True), ('invalid spec', 'InvalidSpec', True)]:
        scenario('GPU rollout ' + name, [{'series': f'rollout_info{{namespace="gpu-inference",name="glm",phase="{phase}"}}', 'values': '1+0x10'}],
                 rollout_alert if fires else None, [rollout_alert], {'namespace': 'gpu-inference', 'name': 'glm'}, '3m')
    for phase, fires in [('Healthy', False), ('Progressing', False), ('Paused', False),
                         ('Abort', True), ('Timeout', True), ('Error', True), ('InvalidSpec', True)]:
        alert = 'ApplicationRolloutFailed'
        scenario('application rollout ' + phase, [
            {'series': f'rollout_info{{namespace="gradiated",name="api",phase="{phase}"}}',
             'values': '1+0x10'}], alert if fires else None, [alert],
                 {'namespace': 'gradiated', 'name': 'api'}, '3m')
    blocked_alert = 'GpuRolloutBlocked'
    pod = 'namespace="gpu-inference",pod="glm-abc"'
    for name, owner, gpu, unschedulable, eval_time, fires in [
        ('blocked model pod', 'ReplicaSet', True, '1+0x40', '16m', True),
        ('briefly unschedulable', 'ReplicaSet', True, '1+0x40', '10m', False),
        ('scheduled', 'ReplicaSet', True, '0+0x40', '16m', False),
        ('training waits for capacity', 'Job', True, '1+0x40', '16m', False),
        ('controller pod without GPU', 'ReplicaSet', False, '1+0x40', '16m', False),
    ]:
        inputs = [{'series': f'kube_pod_status_unschedulable{{{pod}}}', 'values': unschedulable},
                  {'series': f'kube_pod_owner{{{pod},owner_kind="{owner}"}}', 'values': '1+0x40'}]
        if gpu:
            inputs.append({'series': f'kube_pod_container_resource_requests{{{pod},resource="nvidia_com_gpu"}}', 'values': '2+0x40'})
        scenario('GPU rollout ' + name, inputs, blocked_alert if fires else None, [blocked_alert], {'namespace': 'gpu-inference', 'pod': 'glm-abc'}, eval_time)
    monitoring_alert = 'RolloutMonitoringMissing'
    for name, values, fires in [('scraped', '1+0x40', False), ('scrape failing', '0+0x40', True)]:
        scenario('Argo Rollouts ' + name, [{'series': 'up{namespace="gpu-inference",service="argo-rollouts"}', 'values': values}],
                 monitoring_alert if fires else None, [monitoring_alert], eval_time='16m')
    scenario('Argo Rollouts never scraped', [{'series': 'up{namespace="gradiated",service="api"}', 'values': '1+0x40'}],
             monitoring_alert, [monitoring_alert], eval_time='16m')
    secret_alert = 'SecretRefreshFailed'
    for name, values, fires in [('ready', '1+0x40', False), ('not ready', '0+0x40', True), ('brief refresh error', '1+0x8 0+0x3 1+0x28', False)]:
        scenario('Secret ' + name, [{'series': 'externalsecret_status_condition{exported_namespace="gradiated",name="api",condition="Ready",status="True"}', 'values': values}], secret_alert if fires else None, [secret_alert], {'exported_namespace': 'gradiated', 'name': 'api'}, '16m')
    dns_alert = 'DnsSyncStalled'
    for name, values, fires in [('syncing', '0+30x40', False), ('stalled', '0+0x40', True), ('recovered', '0+0x24 750+30x15', False)]:
        scenario('DNS ' + name, [{'series': 'external_dns_controller_last_sync_timestamp_seconds', 'values': values}], dns_alert if fires else None, [dns_alert], eval_time='16m')

    # Each threshold applies only to its own instance, and the cache alerts ignore
    # samples CloudWatch omits when a count is zero.
    data_store_alerts = ['DatabaseStorageLow', 'MetabaseDatabaseStorageLow', 'DatabaseConnectionsHigh', 'DatabaseCpuHigh',
                         'DatabaseMemoryLow', 'CacheNearStorageLimit', 'CacheNearEcpuLimit',
                         'CacheThrottling', 'CacheEvictions', 'DataStoreMetricsMissing']
    def rds(metric, instance, values):
        return {'series': f'aws_rds_{metric}{{dbinstance_identifier="{instance}"}}', 'values': values}
    def cache(metric, values):
        return {'series': f'aws_elasticache_{metric}{{cluster_id="gradiated-prod"}}', 'values': values}
    healthy = {
        ('free_storage_space_minimum', 'gradiated-prod'): f'{50 * 2**30}+0x40',
        ('free_storage_space_minimum', 'gradiated-prod-metabase'): f'{10 * 2**30}+0x40',
        ('database_connections_maximum', 'gradiated-prod'): '40+0x40',
        ('database_connections_maximum', 'gradiated-prod-metabase'): '5+0x40',
        ('cpuutilization_average', 'gradiated-prod'): '20+0x40',
        ('cpuutilization_average', 'gradiated-prod-metabase'): '5+0x40',
        ('freeable_memory_minimum', 'gradiated-prod'): f'{2 * 2**30}+0x40',
        ('freeable_memory_minimum', 'gradiated-prod-metabase'): f'{2**30}+0x40',
        ('bytes_used_for_cache_maximum', None): '1e8+0x40',
        ('elasti_cache_processing_units_sum', None): '6000+0x40',
    }
    def data_store_inputs(**overrides):
        inputs = []
        for (metric, instance), values in healthy.items():
            values = overrides.pop(f'{metric}:{instance}', values)
            if values is not None:
                inputs.append(rds(metric, instance, values) if instance else cache(metric, values))
        for key, values in overrides.items():
            inputs.append(cache(key, values))
        return inputs
    gib = 2**30
    for name, overrides, expected, labels in [
        ('healthy', {}, None, None),
        ('product storage low', {'free_storage_space_minimum:gradiated-prod': f'{4 * gib}+0x40'}, 'DatabaseStorageLow', {'dbinstance_identifier': 'gradiated-prod'}),
        ('Metabase uses its own storage threshold', {'free_storage_space_minimum:gradiated-prod-metabase': f'{4 * gib}+0x40'}, None, None),
        ('Metabase storage low', {'free_storage_space_minimum:gradiated-prod-metabase': f'{gib // 2}+0x40'}, 'MetabaseDatabaseStorageLow', {'dbinstance_identifier': 'gradiated-prod-metabase'}),
        ('product connections high', {'database_connections_maximum:gradiated-prod': '400+0x40'}, 'DatabaseConnectionsHigh', {'dbinstance_identifier': 'gradiated-prod'}),
        ('product memory low', {'freeable_memory_minimum:gradiated-prod': f'{200 * 2**20}+0x40'}, 'DatabaseMemoryLow', {'dbinstance_identifier': 'gradiated-prod'}),
        ('cache storage high', {'bytes_used_for_cache_maximum:None': '9e9+0x40'}, 'CacheNearStorageLimit', {'cluster_id': 'gradiated-prod'}),
        ('cache ECPU high', {'elasti_cache_processing_units_sum:None': '270000+0x40'}, 'CacheNearEcpuLimit', {'cluster_id': 'gradiated-prod'}),
        ('cache throttling', {'throttled_cmds_sum': '3+0x40'}, 'CacheThrottling', {'cluster_id': 'gradiated-prod'}),
        ('cache evictions', {'evictions_sum': '1+0x40'}, 'CacheEvictions', {'cluster_id': 'gradiated-prod'}),
        ('cache metrics missing', {'bytes_used_for_cache_maximum:None': None}, 'DataStoreMetricsMissing', {'cluster_id': 'gradiated-prod'}),
        ('database metrics missing', {'free_storage_space_minimum:gradiated-prod-metabase': None}, 'DataStoreMetricsMissing', {'dbinstance_identifier': 'gradiated-prod-metabase'}),
        ('database CPU metric missing', {'cpuutilization_average:gradiated-prod': None}, 'DataStoreMetricsMissing', {'dbinstance_identifier': 'gradiated-prod'}),
        ('cache ECPU metric missing', {'elasti_cache_processing_units_sum:None': None}, 'DataStoreMetricsMissing', {'cluster_id': 'gradiated-prod'}),
    ]:
        scenario('Data store ' + name, data_store_inputs(**overrides), expected, data_store_alerts, labels, '20m')
    scenario('Data store CPU sustained', data_store_inputs(**{'cpuutilization_average:gradiated-prod': '95+0x80'}),
             'DatabaseCpuHigh', ['DatabaseCpuHigh'], {'dbinstance_identifier': 'gradiated-prod'}, '35m')
    scenario('Data store CPU brief spike', data_store_inputs(**{'cpuutilization_average:gradiated-prod': '95+0x20 20+0x60'}),
             None, ['DatabaseCpuHigh'], None, '35m')

    # Remediation-SLA alerts count only fixable findings for the same image repository
    # across redeploys, and need the full window. Hourly inputs keep multi-day tests fast.
    def cve(severity, values, tag='v1', fixed='1.2.4', vuln='CVE-2026-0001'):
        return {'series': 'trivy_vulnerability_id{namespace="gradiated",image_repository="gradiated/prod/product",'
                f'image_tag="{tag}",severity="{severity}",fixed_version="{fixed}",vuln_id="{vuln}"}}', 'values': values}
    cve_labels = {'namespace': 'gradiated', 'image_repository': 'gradiated/prod/product'}
    for severity, alert, days in [('Critical', 'VulnerabilityCriticalOverdue', 7), ('High', 'VulnerabilityHighOverdue', 30)]:
        hours = days * 24
        due = f'{days + 1}d'
        for name, inputs, fires in [
            ('present past the SLA', [cve(severity, f'1x{hours + 48}')], True),
            ('present within the SLA', [cve(severity, f'_x{hours - 24} 1x72')], False),
            ('unfixed', [cve(severity, f'1x{hours + 48}', fixed='')], False),
            ('remediated', [cve(severity, f'1x{hours} _x48')], False),
            ('redeployed with the same finding', [cve(severity, f'1x{hours // 2} _x{hours}'),
                                                  cve(severity, f'_x{hours // 2} 1x{hours}', tag='v2')], True),
        ]:
            scenario(f'{alert} {name}', inputs, alert if fires else None, [alert],
                     cve_labels if fires else None, due, '1h')
    scenario('VulnerabilityCriticalOverdue ignores High', [cve('High', '1x220')], None,
             ['VulnerabilityCriticalOverdue'], None, '8d', '1h')

    trivy_alert = 'TrivyOperatorNotReporting'
    trivy_up = lambda value: {'series': 'up{namespace="trivy-system",job="trivy-operator"}', 'values': f'{value}x300'}
    trivy_reports = {'series': 'trivy_image_vulnerabilities{namespace="gradiated",severity="Critical"}', 'values': '2x300'}
    scenario('Trivy reporting', [trivy_up(1), trivy_reports], None, [trivy_alert], eval_time='2h')
    scenario('Trivy operator unscraped', [trivy_up(0), trivy_reports], trivy_alert, [trivy_alert], eval_time='2h')
    scenario('Trivy exports no reports', [trivy_up(1)], trivy_alert, [trivy_alert], eval_time='2h')

    root_alert = 'AwsRootAccountUsed'
    root_missing = 'AwsRootUsageMonitoringMissing'
    assert alerts[root_alert]['labels']['severity'] == 'critical', 'Root account activity must page'
    root_metric = 'gradiated_security_root_usage_maximum'
    def root_usage(values, instance='exporter-a', namespace='observability'):
        return {'series': f'{root_metric}{{namespace="{namespace}",job="cloudwatch-exporter",service="cloudwatch-exporter",instance="{instance}"}}', 'values': values}
    scenario('AWS root unused', [root_usage('0x80')], None, [root_alert, root_missing], eval_time='35m')
    scenario('AWS root use first scrape', [root_usage('_x10 1x30')], root_alert, [root_alert, root_missing], eval_time='6m')
    scenario('AWS root zero neighbor cannot mask use', [root_usage('0x40'), root_usage('1x40', instance='exporter-b')], root_alert, [root_alert], eval_time='6m')
    scenario('AWS root ignores application metric impersonation', [root_usage('0x40'), root_usage('1x40', namespace='gradiated')], None, [root_alert, root_missing], eval_time='6m')
    scenario('AWS root window recovered', [root_usage('1x10 0x40')], None, [root_alert, root_missing], eval_time='8m')
    scenario('AWS root missing startup grace', [], None, [root_alert, root_missing], eval_time='20m')
    scenario('AWS root missing telemetry', [], root_missing, [root_alert, root_missing], eval_time='35m')
    scenario('AWS root telemetry recovered', [root_usage('_x64 0x20')], None, [root_alert, root_missing], eval_time='35m')

    for alert, metric_name, severity in [('AwsUrgentSecurityFinding', 'urgent_findings', 'warning'), ('AwsSecurityFindingNeedsReview', 'review_findings', 'warning')]:
        assert alerts[alert]['labels']['severity'] == severity
        def finding_series(values, namespace='observability'):
            return {'series': f'gradiated_security_{metric_name}_maximum{{namespace="{namespace}",job="cloudwatch-exporter",service="cloudwatch-exporter"}}', 'values': values}
        scenario(alert + ' first positive scrape', [finding_series('_x10 1x30')], alert, [alert], eval_time='6m')
        scenario(alert + ' idle', [finding_series('0x40')], None, [alert])
        scenario(alert + ' application impersonation ignored', [finding_series('0x40'), finding_series('1x40', namespace='gradiated')], None, [alert])
        scenario(alert + ' expired event is not current finding status', [finding_series('1x10 0x40')], None, [alert])

    recovery_failure = 'DatabaseRestoreVerificationFailed'
    def recovery_series(metric, values, cronjob='restore-postgres'):
        return {'series': f'{metric}{{namespace="gradiated",cronjob="{cronjob}"}}', 'values': values}
    failure_series = {'series': 'kube_job_status_failed{namespace="gradiated",job_name="restore-postgres-123"}', 'values': '1x80'}
    scenario('restore verification failure reports', [failure_series], recovery_failure, [recovery_failure], {'namespace': 'gradiated', 'job_name': 'restore-postgres-123'})
    scenario('no failed restore job', [], None, [recovery_failure])
    weekly = 'DatabaseRestoreVerificationOverdue'
    weekly_labels = {'namespace': 'gradiated', 'cronjob': 'restore-postgres'}
    scenario('weekly restore overdue', [recovery_series('kube_cronjob_status_last_successful_time', '1x900')], weekly, [weekly], weekly_labels, '9d', '15m')
    scenario('weekly restore recent', [recovery_series('kube_cronjob_status_last_successful_time', '1+900x900')], None, [weekly], eval_time='9d', interval='15m')
    scenario('weekly restore first-run grace', [recovery_series('kube_cronjob_created', '0x80')], None, [weekly], eval_time='8h', interval='15m')
    scenario('weekly restore never commissioned', [recovery_series('kube_cronjob_created', '0x200')], weekly, [weekly], weekly_labels, '2d', '15m')
    maintenance = 'DatabaseRecoveryCleanupOverdue'
    cleanup_labels = {'namespace': 'gradiated', 'cronjob': 'restore-cleanup'}
    scenario('daily recovery maintenance overdue', [recovery_series('kube_cronjob_status_last_successful_time', '1x200', 'restore-cleanup')], maintenance, [maintenance], cleanup_labels, '2d', '15m')
    scenario('daily recovery maintenance recent', [recovery_series('kube_cronjob_status_last_successful_time', '120000x200', 'restore-cleanup')], None, [maintenance], eval_time='2d', interval='15m')
    scenario('daily maintenance never commissioned', [recovery_series('kube_cronjob_created', '0x200', 'restore-cleanup')], maintenance, [maintenance], cleanup_labels, '2d', '15m')
    scenario('daily maintenance first-run grace', [recovery_series('kube_cronjob_created', '0x80', 'restore-cleanup')], None, [maintenance], eval_time='8h', interval='15m')
    missing = 'DatabaseRestoreScheduleMissing'
    other_schedules = [recovery_series('kube_cronjob_info', '1x80', cronjob) for cronjob in ['restore-clickhouse', 'restore-cleanup']]
    scenario('weekly recovery schedule missing', other_schedules, missing, [missing], weekly_labels, '35m')
    scenario('all recovery schedules present', other_schedules + [recovery_series('kube_cronjob_info', '1x80')], None, [missing], eval_time='35m')

    falco_alert = 'FalcoCriticalEvents'
    assert alerts[falco_alert]['labels']['severity'] == 'critical', 'Critical runtime detections must route to urgent incident.io paging'
    def falco(values, priority='2', pod='falco-a'):
        return {'series': f'falcosecurity_falco_rules_matches_total{{namespace="falco",pod="{pod}",priority="{priority}",'
                'rule_name="Drop and execute new binary in container"}', 'values': values}
    falco_labels = {'rule_name': 'Drop and execute new binary in container', 'pod': 'falco-a'}
    scenario('Falco first critical match', [falco('_x10 1x30')], falco_alert, [falco_alert], falco_labels, '8m')
    scenario('Falco repeated critical match', [falco('3x20 4x20')], falco_alert, [falco_alert], falco_labels, '12m')
    scenario('Falco old critical match', [falco('3x60')], None, [falco_alert], eval_time='20m')
    scenario('Falco warning match', [falco('_x10 1x30', priority='4')], None, [falco_alert], eval_time='8m')

    falco_down = 'FalcoDown'
    def falco_state(unavailable, up):
        series = [] if up is None else [{'series': 'up{namespace="falco",job="falco-metrics",pod="falco-a"}', 'values': f'{up}x40'}]
        if unavailable is not None:
            series.append({'series': 'kube_daemonset_status_number_unavailable{namespace="falco",daemonset="falco"}',
                           'values': f'{unavailable}x40'})
        return series
    scenario('Falco healthy', falco_state(0, 1), None, [falco_down], eval_time='16m')
    scenario('Falco sensor unavailable', falco_state(1, 1), falco_down, [falco_down], eval_time='16m')
    scenario('Falco scrape failing', falco_state(0, 0), falco_down, [falco_down], eval_time='16m')
    scenario('Falco not installed', falco_state(None, 1), falco_down, [falco_down],
             {'namespace': 'falco', 'daemonset': 'falco'}, '16m')
    scenario('Falco scrape targets missing', falco_state(0, None), falco_down, [falco_down],
             {'namespace': 'falco', 'job': 'falco-metrics'}, '16m')

    kyverno_alert = 'KyvernoPolicyViolationsRising'
    host_stale = 'GpuHostTelemetryStale'
    for name, timestamp, fires in [('fresh', '0+30x40', False), ('stale', '0x40', True)]:
        scenario('GPU host telemetry ' + name,
                 [{'series': 'gradiated_gpu_host_last_seen_seconds{instance_id="test-host"}', 'values': timestamp}],
                 host_stale if fires else None, [host_stale],
                 {'instance_id': 'test-host', 'node': 'gpu-test-host'} if fires else None)

    def report(values, namespace='gradiated', name='r1'):
        return {'series': f'kube_policyreport_fail{{namespace="{namespace}",name="{name}"}}', 'values': values}
    # Instant selectors need a sample within five minutes of each 15-minute evaluation.
    scenario('Kyverno violations steady', [report('2x240')], None, [kyverno_alert], eval_time='2d', interval='15m')
    scenario('Kyverno violations rising', [report('2x240'), report('_x120 1x120', name='r2')], kyverno_alert,
             [kyverno_alert], {'namespace': 'gradiated'}, '2d', '15m')
    scenario('Kyverno violations in a new namespace', [report('2x240'), report('_x120 1x120', namespace='metabase')],
             kyverno_alert, [kyverno_alert], {'namespace': 'metabase'}, '2d', '15m')
    scenario('Kyverno violations fell', [report('3x120 1x120')], None, [kyverno_alert], eval_time='2d', interval='15m')
    scenario('Kyverno first day after install', [report('1x40 3x80')], None, [kyverno_alert], eval_time='20h', interval='15m')

    fleet_degraded = 'GpuFleetHostDegraded'
    fleet_labels = {'instance_id': 'test-host', 'reason': 'Unreachable'}
    degraded = 'gradiated_gpu_fleet_host_degraded{instance_id="test-host",reason="Unreachable"}'
    scenario('GPU fleet host degraded for ten minutes', [{'series': degraded, 'values': '1+0x40'}],
             fleet_degraded, [fleet_degraded], fleet_labels, '12m')
    scenario('GPU fleet host degraded briefly', [{'series': degraded, 'values': '1+0x10 0+0x30'}],
             None, [fleet_degraded], fleet_labels, '12m')
    stalled = 'GpuFleetNotReconciling'
    reconciled = 'gradiated_gpu_fleet_last_reconcile_timestamp_seconds'
    scenario('GPU fleet operator reconciling', [{'series': reconciled, 'values': '0+30x80'}],
             None, [stalled], eval_time='30m')
    scenario('GPU fleet operator stalled', [{'series': reconciled, 'values': '0+0x80'}],
             stalled, [stalled], eval_time='30m')
    scenario('GPU fleet operator missing', [{'series': 'up{job="other"}', 'values': '1+0x80'}],
             stalled, [stalled], eval_time='30m')
    sync_failing = 'GpuFleetPostgresSyncFailing'
    for name, configured, synced, fires in [
        ('without PostgreSQL credentials', 0, '0+0x100', False),
        ('PostgreSQL syncing', 1, '0+30x100', False),
        ('PostgreSQL sync stopped', 1, '0+0x100', True),
        ('PostgreSQL never synced', 1, None, True),
        ('never synced without credentials', 0, None, False),
    ]:
        inputs = [{'series': 'gradiated_gpu_fleet_postgres_configured', 'values': f'{configured}+0x100'}]
        if synced is not None:
            inputs.append({'series': 'gradiated_gpu_fleet_postgres_last_sync_timestamp_seconds', 'values': synced})
        scenario(f'GPU fleet {name}', inputs, sync_failing if fires else None, [sync_failing], eval_time='45m')

    # Promtool's clock starts at zero, so a lease due at 600s is overdue by 75 minutes at 85m.
    for name, due, fires in [('lease still running', 10_000, False), ('lease due back an hour ago', 600, True)]:
        scenario(f'GPU host {name}', [
            {'series': 'gradiated_gpu_fleet_lease_until_timestamp_seconds{instance_id="h1",holder="agent"}',
             'values': f'{due}+0x200'},
        ], 'GpuHostLeaseOverdue' if fires else None, ['GpuHostLeaseOverdue'],
           {'instance_id': 'h1', 'holder': 'agent'}, eval_time='85m')

    mcp_alerts = ['McpHighErrorRate', 'McpToolFailures', 'McpSlow', 'McpAuthenticationErrors',
                  'McpCredentialCacheDown', 'McpTelemetryMissing']
    mcp_info = {'series': 'gradiated_mcp_service_info{instance="a"}', 'values': '1+0x60'}
    def mcp_requests(status, values, route='/mcp'):
        return {'series': f'gradiated_mcp_http_requests_total{{route="{route}",status="{status}"}}', 'values': values}
    for name, failed, ok, fires in [
        ('9% server errors', '0+3x40', '0+30x40', True),
        ('3% server errors', '0+1x40', '0+30x40', False),
        ('low traffic stays quiet', '0+1x40', '0+0x40', False),
    ]:
        scenario('MCP errors: ' + name, [mcp_info, mcp_requests('500', failed), mcp_requests('200', ok),
                                         mcp_requests('500', '0+100x40', '/health/live')],
                 'McpHighErrorRate' if fires else None, mcp_alerts, eval_time='11m')

    def mcp_tools(outcome, values):
        return {'series': f'gradiated_mcp_tool_calls_total{{tool="list_models",outcome="{outcome}"}}', 'values': values}
    for name, inputs, fires in [
        ('sustained failures', [mcp_tools('failed', '0+2x60'), mcp_tools('success', '0+10x60')], True),
        ('caller rejections are excluded', [mcp_tools('rejected', '0+5x60'), mcp_tools('success', '0+5x60')], False),
        ('below the failure floor', [mcp_tools('failed', '0+0.2x60')], False),
        ('one failure then recovery', [mcp_tools('failed', '0 1+0x59'), mcp_tools('success', '0+10x60')], False),
    ]:
        scenario('MCP tools: ' + name, [mcp_info] + inputs, 'McpToolFailures' if fires else None,
                 mcp_alerts, eval_time='21m')

    for name, fast, samples, fires in [('slow', 0, 1, True), ('fast', 1, 1, False), ('slow but sparse', 0, 0.2, False)]:
        metric = 'gradiated_mcp_http_request_duration_seconds'
        selector = 'route="/mcp",method="POST",status_class="2xx"'
        scenario('MCP latency: ' + name, [mcp_info,
            {'series': f'{metric}_bucket{{{selector},le="5"}}', 'values': f'0+{fast}x60'},
            {'series': f'{metric}_bucket{{{selector},le="10"}}', 'values': f'0+{samples}x60'},
            {'series': f'{metric}_bucket{{{selector},le="+Inf"}}', 'values': f'0+{samples}x60'},
            {'series': f'{metric}_count{{{selector}}}', 'values': f'0+{samples}x60'},
        ], 'McpSlow' if fires else None, mcp_alerts, eval_time='21m')

    for name, values, fires in [('API unreachable', '0+1x60', True), ('brief API error', '0+1x4 4+0x56', False)]:
        scenario('MCP authentication: ' + name, [mcp_info,
            {'series': 'gradiated_mcp_authentications_total{result="error"}', 'values': values},
            {'series': 'gradiated_mcp_authentications_total{result="rejected"}', 'values': '0+5x60'},
        ], 'McpAuthenticationErrors' if fires else None, mcp_alerts, eval_time='12m')

    for healthy in [0, 1]:
        scenario(f'MCP credential cache: healthy neighbor {healthy}', [mcp_info,
            {'series': 'gradiated_mcp_dependency_ready{instance="a",dependency="valkey"}', 'values': '0+0x40'},
            {'series': 'gradiated_mcp_dependency_ready{instance="b",dependency="valkey"}', 'values': f'{healthy}+0x40'},
        ], None if healthy else 'McpCredentialCacheDown', mcp_alerts, {'dependency': 'valkey'}, '11m')

    scenario('MCP telemetry present', [mcp_info], None, mcp_alerts, eval_time='8m')
    scenario('MCP telemetry missing', [{'series': 'gradiated_api_service_info{instance="a"}', 'values': '1+0x30'}],
             'McpTelemetryMissing', mcp_alerts, eval_time='8m')

    with tempfile.TemporaryDirectory(prefix='observability-check-') as directory:
        temp = Path(directory)
        (temp / 'rules.yaml').write_text(yaml.safe_dump({'groups': groups}))
        (temp / 'charts.yaml').write_text(yaml.safe_dump({
            'groups': [{'name': 'dashboard_syntax', 'rules': chart_rules}]}))
        subprocess.run([args.promtool, 'check', 'rules', str(temp / 'rules.yaml'),
                        str(temp / 'charts.yaml')], check=True)
        from rule_tests import run_rule_tests

        suites = run_rule_tests(args.promtool,
            [group for group in groups if group['name'] != 'gradiated.models.desired'], tests, temp)
        print(f'All {len(tests)} behavioral fixtures passed in {suites} isolated rule suites')
    print(f'Validated {len(alerts)} alert panel links, {len(chart_rules)} chart queries, '
          f'and {len(tests)} behavioral scenarios.')


if __name__ == '__main__':
    main()
