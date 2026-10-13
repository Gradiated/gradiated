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
    dashboards = {d['uid']: d for p in OBS.glob('*.json')
                  if (d := json.loads(p.read_text()))}
    groups = [g for name in ('prometheus-rules.yaml', 'logging-prometheus-rules.yaml', 'controller-prometheus-rules.yaml', 'autoscaling-prometheus-rules.yaml', 'model-replica-rules.yaml')
              for g in yaml.safe_load((OBS / name).read_text())['spec']['groups']]
    alerts = {rule['alert']: rule for group in groups for rule in group['rules'] if 'alert' in rule}
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
                assert '$' not in expr, expr
                chart_rules.append({'record': f'check:panel_{len(chart_rules)}', 'expr': expr})

    from autoscaling_checks import check_autoscaling

    from gpu_autoscaling_checks import check_gpu_autoscaling

    tests = check_autoscaling(ROOT) + check_gpu_autoscaling(ROOT)
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

    for missing in (None, 'api', 'gateway', 'proxy', 'worker'):
        inputs = [{'series': 'kube_horizontalpodautoscaler_spec_max_replicas'
                   + f'{{namespace="gradiated",horizontalpodautoscaler="keda-hpa-{service}"}}',
                   'values': '20+0x8'} for service in ('api', 'gateway', 'proxy', 'worker') if service != missing]
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
        scenario(name, inputs, replica_alert if fires else None, [replica_alert],
                 {'namespace': 'gradiated', 'deployment': 'api'})

    for service, alert in [('api', 'ApiPublicUnavailable'),
                           ('console', 'ConsoleUnavailable'),
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

    alb_errors = 'PublicLoadBalancerErrors'
    alb_series = 'aws_applicationelb_httpcode_elb_5_xx_count_sum{load_balancer="app/gradiated-prod-public-api/abc"}'
    for name, values, eval_time, fires in [
        ('sustained ALB 5xx', '6+0x20', '3m', True),
        ('below threshold', '4+0x20', '3m', False),
        ('one-minute spike', '6 6 stale', '3m', False),
        ('no errors reported', None, '3m', False),
    ]:
        inputs = [] if values is None else [{'series': alb_series, 'values': values}]
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

    probe_labels = '{instance="a",model="test/model",deployment="test-deployment"}'
    def probe_series(metric, values, labels=probe_labels):
        return {'series': metric + labels, 'values': values}

    probe_alerts = ['InferenceDeploymentProbeFailed', 'InferenceProbeMonitoringStalled']
    for name, success, inventory, target, expected, duration in [
        ('healthy', '1+5x30', '1+5x30', '1+0x30', None, '60s'),
        ('never completed', '0+0x30', '1+5x30', '1+0x30', 'InferenceDeploymentProbeFailed', '30s'),
        ('stops completing', '1+0x30', '1+5x30', '1+0x30', 'InferenceDeploymentProbeFailed', '30s'),
        ('short transient', '1 1 1 16+5x27', '1+5x30', '1+0x30', None, '30s'),
        ('monitor stopped', '1+0x30', '1+0x30', '1+0x30', 'InferenceProbeMonitoringStalled', '35s'),
        ('retired target', '1+0x30', '1+5x30', '1+0x2 stale', None, '60s'),
    ]:
        scenario('public inference: ' + name, [
            probe_series('gradiated_inference_probe_last_success_timestamp_seconds', success),
            probe_series('gradiated_inference_probe_target', target),
            probe_series('gradiated_inference_probe_inventory_timestamp_seconds', inventory, '{instance="a"}'),
        ], expected, probe_alerts,
        {'model': 'test/model', 'deployment': 'test-deployment'} if expected == 'InferenceDeploymentProbeFailed' else {},
        duration, interval='5s')

    scenario('public inference: missing telemetry', [], 'InferenceProbeMonitoringStalled',
             ['InferenceProbeMonitoringStalled'], eval_time='15s', interval='5s')
    scenario('public inference: replacement leader masks stale failed worker', [
        probe_series('gradiated_inference_probe_last_success_timestamp_seconds', '0+0x30'),
        probe_series('gradiated_inference_probe_target', '1+0x30'),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+0x30', '{instance="a"}'),
        probe_series('gradiated_inference_probe_last_success_timestamp_seconds', '1+5x30', probe_labels.replace('"a"', '"b"')),
        probe_series('gradiated_inference_probe_target', '1+0x30', probe_labels.replace('"a"', '"b"')),
        probe_series('gradiated_inference_probe_inventory_timestamp_seconds', '1+5x30', '{instance="b"}'),
    ], None, probe_alerts, eval_time='60s', interval='5s')

    for ready, expected, duration in [(0, 'ModelNoReadyReplicas', '15s'), (1, 'ModelUnderReplicated', '30s')]:
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
    ], 'ModelNoReadyReplicas', ['ModelNoReadyReplicas'], {'model': 'test/model'}, '40s', interval='5s')

    for failed, succeeded, expected in [('0+1x60', '0+100x60', 'GatewayRuntimeFailures'),
                                        ('0+0x60', '0+100x60', None),
                                        ('0 1+0x59', '0+100x60', None)]:
        scenario('per-deployment runtime failures: ' + failed, [
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="failed"}', 'values': failed},
            {'series': 'gradiated_gateway_generations_total{model="test/model",deployment="test-deployment",status="succeeded"}', 'values': succeeded},
            {'series': 'gradiated_gateway_generations_total{model="other/model",deployment="healthy-deployment",status="succeeded"}', 'values': '0+100000x60'},
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
        ('SettlementBackpressure', 'gradiated_gateway_last_settlement_backpressure_timestamp_seconds'),
    ]:
        for name, values, eval_time, fires in [
            ('first event before first scrape', '60+0x30', '2m', True),
            ('no prior event', '0+0x30', '2m', False),
            ('event ages out', '60+0x30', '8m', False),
            ('new process has no inherited event', '0+0x30', '8m', False),
        ]:
            scenario(alert + ': ' + name, [{'series': metric, 'values': values}],
                     alert if fires else None, [alert], eval_time=eval_time)

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
    rollout_alert = 'GpuRolloutFailed'
    for name, phase, fires in [('completed', 'Completed', False), ('progressing', 'Progressing', False), ('paused', 'Paused', False),
                               ('aborted', 'Abort', True), ('deadline exceeded', 'Timeout', True), ('reconcile error', 'Error', True), ('invalid spec', 'InvalidSpec', True)]:
        scenario('GPU rollout ' + name, [{'series': f'rollout_info{{namespace="gpu-inference",name="glm",phase="{phase}"}}', 'values': '1+0x10'}],
                 rollout_alert if fires else None, [rollout_alert], {'namespace': 'gpu-inference', 'name': 'glm'}, '3m')
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
    monitoring_alert = 'GpuRolloutMonitoringMissing'
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

    with tempfile.TemporaryDirectory(prefix='observability-check-') as directory:
        temp = Path(directory)
        (temp / 'rules.yaml').write_text(yaml.safe_dump({'groups': groups}))
        (temp / 'charts.yaml').write_text(yaml.safe_dump({
            'groups': [{'name': 'dashboard_syntax', 'rules': chart_rules}]}))
        (temp / 'test-rules.yaml').write_text(yaml.safe_dump({'groups': [g for g in groups if g['name'] != 'gradiated.models.desired']}))
        (temp / 'tests.yaml').write_text(yaml.safe_dump({
            'rule_files': ['test-rules.yaml'], 'evaluation_interval': '30s', 'tests': [test for test in tests if test['interval'] != '5s']}))
        (temp / 'fast-tests.yaml').write_text(yaml.safe_dump({
            'rule_files': ['test-rules.yaml'], 'evaluation_interval': '5s',
            'tests': [test for test in tests if test['interval'] == '5s']}))
        subprocess.run([args.promtool, 'test', 'rules', str(temp / 'fast-tests.yaml')], check=True)
        subprocess.run([args.promtool, 'check', 'rules', str(temp / 'rules.yaml'),
                        str(temp / 'charts.yaml')], check=True)
        subprocess.run([args.promtool, 'test', 'rules', str(temp / 'tests.yaml')], check=True)
    print(f'Validated {len(alerts)} alert panel links, {len(chart_rules)} chart queries, '
          f'and {len(tests)} behavioral scenarios.')


if __name__ == '__main__':
    main()
