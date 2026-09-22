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
    groups = [g for name in ('prometheus-rules.yaml', 'logging-prometheus-rules.yaml')
              for g in yaml.safe_load((OBS / name).read_text())['spec']['groups']]
    alerts = {rule['alert']: rule for group in groups for rule in group['rules']}
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
                expr = expr.replace('$deployment', '.*')
                assert '$' not in expr, expr
                chart_rules.append({'record': f'check:panel_{len(chart_rules)}', 'expr': expr})

    tests = []
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

    for service, title, down in [('api', 'Api', 'GradiatedApiPublicUnavailable'),
                                 ('console', 'Console', 'GradiatedConsoleUnavailable'),
                                 ('metabase', 'Metabase', 'GradiatedMetabaseUnavailable')]:
        missing = f'Gradiated{title}ProbeMissing'
        for case, values, expected in [('healthy', '1+0x30', None),
                                       ('transient', '1+0x5 0 1+0x24', None),
                                       ('down', '0+0x30', down),
                                       ('recovered', '0+0x10 1+0x20', None),
                                       ('missing', None, missing)]:
            inputs = [] if values is None else [
                {'series': f'probe_success{{service="{service}"}}', 'values': values}]
            scenario(f'{service}: {case}', inputs, expected, [down, missing])

    stall = 'GradiatedGatewayGenerationsStuck'
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

    replica_alert = 'GradiatedDeploymentUnavailable'
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

    for service, alert in [('api', 'GradiatedApiPublicUnavailable'),
                           ('console', 'GradiatedConsoleUnavailable')]:
        inputs = [{'series': f'probe_success{{service="{service}"}}',
                   'values': '1+0x5 0+0x30'}]
        scenario(f'{service} brief outage stays quiet', inputs, None, [alert], eval_time='4m')
        scenario(f'{service} outage fires after two minutes', inputs, alert, [alert], eval_time='5m')

    for alert, metric, threshold, hold, labels in [
        ('GradiatedGenerationIngestionStuck',
         'gradiated_worker_ingestion_backlog{kind="oldest_pending_age_seconds"}', 300, '1m', {}),
        ('GradiatedSettlementLagging', 'gradiated_worker_settlement_lag_seconds', 300, '2m', {}),
    ]:
        leader_input = ([{'series': 'gradiated_worker_settlement_leader', 'values': '1+0x30'}]
                        if alert == 'GradiatedSettlementLagging' else [])
        scenario(alert + ' threshold stays quiet', [{'series': metric, 'values': f'{threshold}+0x30'}] + leader_input,
                 None, [alert], labels)
        inputs = [{'series': metric, 'values': f'{threshold+1}+0x30'}] + leader_input
        scenario(alert + ' does not fire immediately', inputs, None, [alert], labels, '0m')
        scenario(alert + ' fires at promised duration', inputs, alert, [alert], labels, hold)

    for alert, metric, failure_labels, success_labels, labels in [
        ('GradiatedApiSevereErrors', 'gradiated_api_http_requests_total',
         'route="/v1/test",status="500"', 'route="/v1/test",status="200"', {}),
        ('GradiatedGatewaySevereErrors', 'gradiated_gateway_http_requests_total',
         'status="500"', 'status="200"', {}),
        ('GradiatedGatewaySevereGenerationFailures', 'gradiated_gateway_generations_total',
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

    leader_alert = 'GradiatedSettlementLeaderMissing'
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
    ], 'GradiatedWorkerLoopStalled', ['GradiatedWorkerLoopStalled'], {'loop': 'settlement'})

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
