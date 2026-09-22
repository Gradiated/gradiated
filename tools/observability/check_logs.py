#!/usr/bin/env python3
"""Exercise the real dashboard LogQL against disposable localhost Loki fixtures.

Start Loki on 127.0.0.1:23100; never run this against a production datasource.
"""
import json
from pathlib import Path
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = 'http://127.0.0.1:23100'
ROOT = Path(__file__).resolve().parents[2]
DASHBOARD = ROOT / 'infra/environments/prod/us-east-1/kubernetes/workloads/observability/logs.json'
IDS = {key: f'00000000-0000-4000-8000-{i:012d}' for i, key in enumerate(
    ['organization_id', 'workspace_id', 'api_key_id', 'user_id'], 1)}
GENERATION = '00000000-0000-4000-8000-000000000099'


def main():
    for attempt in range(60):
        try:
            with urlopen(BASE + '/ready', timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            if attempt == 59:
                raise
            time.sleep(1)

    now = time.time_ns()
    namespace = f'fixture-{now}'
    streams = []
    for workload, level, body in [
        ('api', 'info', {**IDS, 'event': 'request_completed'}),
        ('gateway', 'warn', {'span': {**IDS, 'user_id': '', 'api_key_id': GENERATION,
                                    'generation_id': GENERATION}, 'fields': {'event': 'failure'}}),
        ('api', 'warn', {'event': 'unauthenticated'}),
        ('worker', 'info', 'legacy unstructured log'),
    ]:
        streams.append({'stream': {'environment': 'prod', 'cluster': 'fixture',
                                  'namespace': namespace, 'workload': workload, 'level': level},
                        'values': [[str(now), json.dumps(body) if isinstance(body, dict) else body]]})
    payload = json.dumps({'streams': streams}).encode()
    with urlopen(Request(BASE + '/loki/api/v1/push', data=payload,
                         headers={'Content-Type': 'application/json'}), timeout=10) as response:
        assert response.status == 204

    dashboard = json.loads(DASHBOARD.read_text())
    panels = {p['id']: p['targets'][0]['expr'] for p in dashboard['panels'] if p['type'] == 'logs'}
    cases = [({}, 5, 4), ({}, 6, 2), ({'organization_id': IDS['organization_id']}, 5, 2),
             ({'workspace_id': IDS['workspace_id']}, 5, 2),
             ({'api_key_id': IDS['api_key_id']}, 5, 1), ({'user_id': IDS['user_id']}, 5, 1),
             ({'api_key_id': IDS['api_key_id'], 'user_id': GENERATION}, 5, 0),
             ({'correlation': GENERATION}, 5, 1), ({'workspace_id': GENERATION}, 5, 0),
             ({'workload': 'worker'}, 5, 1), ({'workspace_id': IDS['workspace_id']}, 6, 1)]
    for filters, panel, expected in cases:
        values = {'cluster': 'fixture', 'namespace': namespace, 'workload': '.*',
                  'search': '.*', 'correlation': '', **{key: '.*' for key in IDS}, **filters}
        expr = panels[panel]
        for key, value in values.items():
            expr = expr.replace('${' + key + ':doublequote}', json.dumps(value))
            expr = expr.replace('$' + key, value)
        params = urlencode({'query': expr, 'start': str(now - 1_000_000_000),
                            'end': str(now + 1_000_000_000), 'limit': 100})
        with urlopen(BASE + '/loki/api/v1/query_range?' + params, timeout=10) as response:
            data = json.load(response)
        count = sum(len(stream['values']) for stream in data['data']['result'])
        assert count == expected, (filters, panel, count, expected)
    print(f'Passed {len(cases)} service, tenant, key, user, severity and correlation filter scenarios.')


if __name__ == '__main__':
    main()
