"""Evaluate each fixture with its referenced rules and recording-rule closure."""

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
import subprocess

import yaml


def referenced_names(text, names):
    return {name for name in names if re.search(r'(?<![a-zA-Z0-9_:])' + re.escape(name) + r'(?![a-zA-Z0-9_:])', text)}


def fixture_rules(groups, test):
    rules = [rule for group in groups for rule in group['rules']]
    records = {rule['record'] for rule in rules if 'record' in rule}
    alerts = {rule['alert'] for rule in rules if 'alert' in rule}
    required = {case['alertname'] for case in test.get('alert_rule_test', [])}
    assert required <= alerts, f'Unknown alerts: {required - alerts}'
    encoded = json.dumps(test)
    if 'ALERTS' in encoded:
        required |= alerts
    required |= referenced_names(encoded, records)
    while True:
        expressions = ' '.join(str(rule['expr']) for rule in rules
                               if rule.get('record', rule.get('alert')) in required)
        dependencies = referenced_names(expressions, records)
        if dependencies <= required:
            break
        required |= dependencies
    return [{**group, 'rules': selected} for group in groups
            if (selected := [rule for rule in group['rules']
                             if rule.get('record', rule.get('alert')) in required])]


def run_rule_tests(promtool, groups, tests, directory, workers=None):
    suites = {}
    for test in tests:
        interval = '5s' if test['interval'] == '5s' else '15m' if test['interval'] in ('15m', '1h') else '30s'
        selected = fixture_rules(groups, test)
        key = json.dumps([interval, selected], sort_keys=True)
        suites.setdefault(key, {'groups': selected, 'interval': interval, 'tests': []})['tests'].append(test)
    commands = []
    for index, suite in enumerate(suites.values()):
        path = Path(directory) / f'fixture-{index}'
        path.mkdir()
        (path / 'rules.yaml').write_text(yaml.safe_dump({'groups': suite['groups']}))
        (path / 'tests.yaml').write_text(yaml.safe_dump({'rule_files': ['rules.yaml'],
            'evaluation_interval': suite['interval'], 'tests': suite['tests']}))
        commands.append([promtool, 'test', 'rules', str(path / 'tests.yaml')])
    def execute(command):
        result = subprocess.run(command, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
    with ThreadPoolExecutor(max_workers=workers or min(4, os.cpu_count() or 1)) as executor:
        list(executor.map(execute, commands))
    return len(suites)
