"""Argo CD's health for a GpuHost, evaluated by the Argo CD CLI. Needs Docker."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'infra/modules/argocd-bootstrap'
VERSION = re.search(r'global\s*=\s*\{\s*image\s*=\s*\{\s*tag\s*=\s*"([^"]+)"', (BOOTSTRAP / 'main.tf').read_text())[1]


def health(status):
    host = {'apiVersion': 'fleet.gradiated.com/v1alpha1', 'kind': 'GpuHost', 'metadata': {'name': 'gpu-x'}, 'spec': {}}
    if status is not None:
        host['status'] = status
    with tempfile.TemporaryDirectory() as directory:
        directory = Path(directory)
        (directory / 'argocd-cm.yaml').write_text(yaml.safe_dump({
            'apiVersion': 'v1', 'kind': 'ConfigMap', 'metadata': {'name': 'argocd-cm'},
            'data': {'resource.customizations.health.fleet.gradiated.com_GpuHost':
                     (BOOTSTRAP / 'gpuhost-health.lua').read_text()}}))
        (directory / 'host.yaml').write_text(yaml.safe_dump(host))
        directory.chmod(0o755)
        result = subprocess.run(
            ['docker', 'run', '--rm', '-v', f'{directory}:/w:ro', f'quay.io/argoproj/argocd:{VERSION}',
             'argocd', 'admin', 'settings', 'resource-overrides', 'health', '/w/host.yaml',
             '--argocd-cm-path', '/w/argocd-cm.yaml'], capture_output=True, text=True)
    if result.returncode:
        raise AssertionError(result.stderr)
    return dict(line.split(': ', 1) for line in result.stdout.strip().splitlines() if ': ' in line)


class GpuHostHealthTest(unittest.TestCase):
    def test_phases_map_to_argo_health(self):
        degraded = {'phase': 'Degraded', 'conditions': [
            {'type': 'Ready', 'status': 'False'},
            {'type': 'Degraded', 'status': 'True', 'message': 'The host agent is unreachable'}]}
        for status, expected, message in (
            (None, 'Progressing', 'Waiting for the gpu-fleet operator'),
            ({'phase': 'Pending'}, 'Progressing', 'Waiting for the host agent to answer'),
            ({'phase': 'Ready'}, 'Healthy', 'The host agent answers'),
            ({'phase': 'Draining'}, 'Progressing', 'Deleted; held until no pods run on the host'),
            (degraded, 'Degraded', 'The host agent is unreachable'),
        ):
            with self.subTest(status=status):
                self.assertEqual(health(status), {'STATUS': expected, 'MESSAGE': message})


if __name__ == '__main__':
    unittest.main()
