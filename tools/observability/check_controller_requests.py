"""Render pinned controller charts and require scheduler reservations."""
from pathlib import Path
import re
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    bootstrap = ROOT / 'infra/modules/argocd-bootstrap'
    terraform = (bootstrap / 'main.tf').read_text()
    assert 'file("${path.module}/resources.yaml")' in terraform
    version = re.search(r'chart\s*=\s*"argo-cd"\s*\n\s*version\s*=\s*"([^"]+)"', terraform)[1]
    argo_values = yaml.safe_load((bootstrap / 'resources.yaml').read_text())
    argo_values['notifications'] = {'enabled': False}
    external = yaml.safe_load((ROOT / 'infra/environments/prod/us-east-1/kubernetes/platform/external-secrets.yaml').read_text())['spec']
    source = external['source']
    charts = [
        ('argocd', 'argocd', 'argo-cd', 'https://argoproj.github.io/argo-helm', version, argo_values),
        ('external-secrets', external['destination']['namespace'], source['chart'], source['repoURL'],
         source['targetRevision'], source['helm']['valuesObject']),
    ]
    with tempfile.TemporaryDirectory(prefix='controller-requests-') as directory:
        for release, namespace, chart, repository, version, values in charts:
            values_file = Path(directory) / f'{release}.yaml'
            values_file.write_text(yaml.safe_dump(values))
            output = subprocess.check_output([
                'helm', 'template', release, chart, '--repo', repository, '--version', version,
                '--namespace', namespace, '--kube-version', '1.36.3', '-f', str(values_file),
            ], text=True)
            checked = 0
            for resource in yaml.safe_load_all(output):
                if not resource or resource['kind'] not in ('Deployment', 'StatefulSet', 'Job'):
                    continue
                pod = resource['spec']['template']['spec']
                for container in pod.get('containers', []) + pod.get('initContainers', []):
                    requests = container.get('resources', {}).get('requests', {})
                    assert requests.get('cpu') and requests.get('memory'), (
                        f'{namespace}/{resource["metadata"]["name"]}/{container["name"]} lacks CPU or memory requests')
                    checked += 1
            assert checked > 0, f'No controller containers rendered for {chart}'
            print(f'Validated CPU and memory requests for {checked} {release} containers')


if __name__ == '__main__':
    main()
