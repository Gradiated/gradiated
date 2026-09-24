#!/usr/bin/env python3
"""Render pinned autoscaling charts and validate ScaledObjects with their CRD."""
from pathlib import Path
import subprocess
import tempfile

from jsonschema import Draft7Validator
import yaml

ROOT = Path(__file__).resolve().parents[2]
KUBERNETES = ROOT / 'infra/environments/prod/us-east-1/kubernetes'


def main():
    with tempfile.TemporaryDirectory(prefix='autoscaling-platform-') as directory:
        values = Path(directory) / 'values.yaml'
        rendered = {}
        for name in ('keda', 'metrics-server', 'cluster-autoscaler'):
            application = yaml.safe_load((KUBERNETES / 'platform' / f'{name}.yaml').read_text())['spec']
            source = application['source']
            values.write_text(yaml.safe_dump(source['helm']['valuesObject']))
            output = subprocess.check_output([
                'helm', 'template', name, source['chart'], '--repo', source['repoURL'],
                '--version', source['targetRevision'], '--namespace', application['destination']['namespace'],
                '--kube-version', '1.36.3', '--include-crds', '-f', str(values)], text=True)
            rendered[name] = [d for d in yaml.safe_load_all(output) if d]
            deployments = [d for d in rendered[name] if d['kind'] == 'Deployment']
            assert len(deployments) == (3 if name == 'keda' else 1)
            for deployment in deployments:
                assert deployment['spec']['replicas'] == 2
                assert deployment['spec']['template']['spec']['affinity']['podAntiAffinity']
                for container in deployment['spec']['template']['spec']['containers']:
                    assert container['resources']['requests']['cpu']
                    assert container['resources']['requests']['memory']
            if name == 'cluster-autoscaler':
                pod = deployments[0]['spec']['template']['spec']
                assert pod['serviceAccountName'] == 'cluster-autoscaler'
                container = pod['containers'][0]
                assert container['image'].endswith(':v1.36.1')
                assert '--max-graceful-termination-sec=700' in container['command']
                assert '--expendable-pods-priority-cutoff=-10' in container['command']
                assert any('node-group-auto-discovery=asg:tag=' in arg and 'gradiated-prod' in arg
                           for arg in container['command'])
            print(f'Rendered {name} {source["targetRevision"]}: {len(deployments)} HA Deployments')

        crd = next(d for d in rendered['keda'] if d['kind'] == 'CustomResourceDefinition'
                   and d['metadata']['name'] == 'scaledobjects.keda.sh')
        schema = next(v['schema']['openAPIV3Schema'] for v in crd['spec']['versions']
                      if v['name'] == 'v1alpha1')
        validator = Draft7Validator(schema)
        for service in ('api', 'worker', 'gateway', 'proxy'):
            obj = yaml.safe_load((KUBERNETES / 'workloads' / f'{service}-autoscaling.yaml').read_text())
            validator.validate(obj)
        print('Validated every service ScaledObject against the pinned KEDA CRD')


if __name__ == '__main__':
    main()
