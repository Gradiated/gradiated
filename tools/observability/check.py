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
    groups = [g for name in ('prometheus-rules.yaml', 'logging-prometheus-rules.yaml', 'controller-prometheus-rules.yaml', 'autoscaling-prometheus-rules.yaml')
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

    tests = check_autoscaling(ROOT)
    def scenario(name, inputs, expected, checks, labels=None, eval_time="8m"):
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
        tests.append({'name': name, 'interval': '30s', 'input_series': inputs,
                      'alert_rule_test': cases})

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

    for desired, limited, fires in [(2, 1, False), (20, 0, False), (20, 1, True)]:
        labels = {'namespace': 'gradiated', 'horizontalpodautoscaler': 'keda-hpa-api'}
        selector = 'namespace="gradiated",horizontalpodautoscaler="keda-hpa-api"'
        inputs = [
            {'series': 'kube_horizontalpodautoscaler_status_desired_replicas{' + selector + '}',
             'values': f'{desired}+0x30'},
            {'series': 'kube_horizontalpodautoscaler_spec_max_replicas{' + selector + '}',
             'values': '20+0x30'},
            {'series': 'kube_horizontalpodautoscaler_status_condition{' + selector +
             ',condition="ScalingLimited",status="true"}', 'values': f'{limited}+0x30'},
        ]
        scenario(f'autoscaling cap desired={desired} limited={limited}', inputs,
                 'AutoscalingLimited' if fires else None,
                 ['AutoscalingLimited'],
                 {**labels, 'condition': 'ScalingLimited', 'status': 'true'}, '10m')

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
        ('automatic sync stalled', 'Healthy', 'OutOfSync', 'true', True),
        ('intentional manual drift', 'Healthy', 'OutOfSync', 'false', False),
    ]:
        inputs = [{'series': f'argocd_app_info{{name="api",health_status="{health}",sync_status="{sync}",autosync_enabled="{auto}"}}', 'values': '1+0x40'}]
        scenario('Argo ' + name, inputs, app_alert if fires else None, [app_alert], {'name': 'api'}, '16m')
    scenario('ordinary deployment converges before warning', [
        {'series': 'argocd_app_info{name="api",health_status="Healthy",sync_status="OutOfSync",autosync_enabled="true"}', 'values': '1+0x8 stale'},
        {'series': 'argocd_app_info{name="api",health_status="Healthy",sync_status="Synced",autosync_enabled="true"}', 'values': '_ _ _ _ _ _ _ _ _ 1+0x31'},
    ], None, [app_alert], eval_time='16m')
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
        (temp / 'tests.yaml').write_text(yaml.safe_dump({
            'rule_files': ['rules.yaml'], 'evaluation_interval': '30s', 'tests': tests}))
        subprocess.run([args.promtool, 'check', 'rules', str(temp / 'rules.yaml'),
                        str(temp / 'charts.yaml')], check=True)
        subprocess.run([args.promtool, 'test', 'rules', str(temp / 'tests.yaml')], check=True)
    print(f'Validated {len(alerts)} alert panel links, {len(chart_rules)} chart queries, '
          f'and {len(tests)} behavioral scenarios.')


if __name__ == '__main__':
    main()
