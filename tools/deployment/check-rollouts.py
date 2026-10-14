#!/usr/bin/env python3
"""Render the pinned controller and validate application Rollouts and analysis CRDs."""
from pathlib import Path
import subprocess
import tempfile

from jsonschema import Draft7Validator
import yaml

ROOT = Path(__file__).resolve().parents[2]
KUBE = ROOT / 'infra/environments/prod/us-east-1/kubernetes'


def main():
    app = yaml.safe_load((KUBE / 'platform/argo-rollouts.yaml').read_text())
    spec = app['spec']
    source = spec['source']
    with tempfile.TemporaryDirectory(prefix='core-rollouts-') as directory:
        values = Path(directory) / 'values.yaml'
        values.write_text(yaml.safe_dump(source['helm']['valuesObject']))
        rendered = subprocess.check_output([
            'helm', 'template', app['metadata']['name'], source['chart'],
            '--repo', source['repoURL'], '--version', source['targetRevision'],
            '--namespace', spec['destination']['namespace'], '--include-crds', '-f', str(values),
        ], text=True)
    resources = [r for r in yaml.safe_load_all(rendered) if r]
    schemas = {r['spec']['names']['kind']: next(
        v['schema']['openAPIV3Schema'] for v in r['spec']['versions'] if v['name'] == 'v1alpha1')
        for r in resources if r['kind'] == 'CustomResourceDefinition'}
    controller = next(r for r in resources if r['kind'] == 'Deployment')
    pod = controller['spec']['template']['spec']
    assert '--namespaced' not in pod['containers'][0]['args']
    assert not any(arg.startswith('--instance-id') for arg in pod['containers'][0]['args'])
    assert controller['spec']['replicas'] == 3
    role = next(r for r in resources if r['kind'] == 'ClusterRole'
                and r['metadata']['name'] == app['metadata']['name'])
    assert any('rollouts' in rule.get('resources', []) and 'update' in rule['verbs']
               for rule in role['rules'])
    binding = next(r for r in resources if r['kind'] == 'ClusterRoleBinding'
                   and r['roleRef']['name'] == role['metadata']['name'])
    assert any(subject['name'] == pod['serviceAccountName'] and
               subject['namespace'] == spec['destination']['namespace'] for subject in binding['subjects'])
    monitors = list(yaml.safe_load_all((KUBE / 'workloads/observability/controller-monitors.yaml').read_text()))
    monitor = next(m for m in monitors if m['metadata']['name'] == 'controller-argo-rollouts')['spec']
    assert monitor['namespaceSelector']['matchNames'] == [spec['destination']['namespace']]
    # Rollout metrics must retain the managed workload's namespace, not the controller's.
    assert monitor['podMetricsEndpoints'][0]['honorLabels'] is True
    print('Validated one cluster-wide Rollouts controller with HA replicas and cluster RBAC')
    rendered = subprocess.check_output(['kubectl', 'kustomize', str(KUBE / 'workloads')], text=True)
    resources = [r for r in yaml.safe_load_all(rendered) if r]
    templates = {r['metadata']['name']: r for r in resources if r['kind'] == 'AnalysisTemplate'}
    for resource in resources:
        if resource['kind'] in ('Rollout', 'AnalysisTemplate'):
            Draft7Validator(schemas[resource['kind']]).validate(resource)
        if resource['kind'] != 'Rollout':
            continue
        name = resource['metadata']['name']
        spec = resource['spec']
        assert spec['progressDeadlineAbort'] is True
        assert spec['workloadRef']['scaleDown'] == 'onsuccess'
        canary = spec['strategy']['canary']
        assert canary['maxUnavailable'] == 0
        assert canary['analysis']['startingStep'] == 1
        for ref in canary['analysis']['templates']:
            assert ref['templateName'] in templates
        assert [s['setWeight'] for s in canary['steps'] if 'setWeight' in s] == [33, 67, 100]
        print(f'Validated Rollout and analysis references: {name}')


if __name__ == '__main__':
    main()
