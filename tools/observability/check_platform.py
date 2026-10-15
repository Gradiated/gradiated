#!/usr/bin/env python3
"""Render the pinned monitoring chart and exercise its incident routing."""
import argparse
import base64
from pathlib import Path
import shutil
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
APPLICATION = ROOT / 'infra/environments/prod/us-east-1/kubernetes/platform/observability.yaml'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--amtool', default=shutil.which('amtool'))
    parser.add_argument('--chart', help='Local archive of the pinned kube-prometheus-stack chart')
    args = parser.parse_args()
    if not args.amtool:
        parser.error('amtool is required')

    application = yaml.safe_load(APPLICATION.read_text())['spec']
    source = application['source']
    with tempfile.TemporaryDirectory(prefix='observability-platform-') as directory:
        temporary = Path(directory)
        values = temporary / 'values.yaml'
        values.write_text(yaml.safe_dump(source['helm']['valuesObject']))
        command = ['helm', 'template', source['helm']['releaseName'],
                   args.chart or source['chart'], '--namespace', application['destination']['namespace'],
                   '--kube-version', '1.36.3', '-f', str(values)]
        if not args.chart:
            command += ['--repo', source['repoURL'], '--version', source['targetRevision']]
        for parameter in source['helm'].get('parameters', []):
            command += ['--set-string' if parameter.get('forceString') else '--set',
                        f'{parameter["name"]}={parameter["value"]}']
        output = subprocess.check_output(command, text=True)
        resources = [resource for resource in yaml.safe_load_all(output) if resource]
        grafana = next(resource for resource in resources if resource['kind'] == 'Deployment'
                       and resource['metadata']['name'] == 'observability-grafana')
        assert grafana['spec']['strategy'] == {'type': 'Recreate', 'rollingUpdate': None}
        assert grafana['spec']['replicas'] == 1

        secret = next(resource for resource in resources if resource['kind'] == 'Secret'
                      and 'alertmanager.yaml' in resource.get('data', {}))
        configuration = temporary / 'alertmanager.yaml'
        configuration.write_bytes(base64.b64decode(secret['data']['alertmanager.yaml']))
        cases = [
            ('null', name, 'gradiated', 'warning')
            for name in ('KubeHpaMaxedOut', 'AutoscalingLimited', 'RequestPathAutoscalingLimited')
        ] + [
            ('incident-webhook', 'KubeHpaMaxedOut', 'observability', 'warning'),
            ('incident-webhook', 'AutoscalingLimited', 'gradiated', 'critical'),
            ('incident-webhook', 'AutoscalingLimited', 'gradiated', 'unexpected'),
            ('incident-webhook', 'AutoscalingUnavailable', 'gradiated', 'warning'),
            ('incident-webhook', 'ApplicationReconciliationFailed', 'argocd', 'warning'),
            ('incident-webhook', 'GpuRolloutFailed', 'gpu-inference', 'warning'),
            ('incident-webhook', 'GpuRolloutBlocked', 'gpu-inference', 'warning'),
            ('incident-webhook', 'WorkerLoopStalled', 'gradiated', 'critical'),
            ('incident-webhook', 'InferenceDeploymentProbeFailed', 'gradiated', 'critical'),
            ('incident-webhook', 'ModelUnderReplicated', 'gradiated', 'warning'),
            ('incident-webhook', 'GatewayHighErrorRate', 'gradiated', 'critical'),
            ('incident-webhook', 'ProxyHighErrorRate', 'gradiated', 'critical'),
            ('incident-webhook', 'VulnerabilityCriticalOverdue', 'gradiated', 'warning'),
            ('incident-webhook', 'VulnerabilityHighOverdue', 'gpu-inference', 'warning'),
            ('incident-webhook', 'KyvernoPolicyViolationsRising', 'gradiated', 'warning'),
            ('incident-webhook', 'FalcoCriticalEvents', 'falco', 'warning'),
            ('incident-webhook', 'FalcoDown', 'falco', 'warning'),
            ('heartbeat', 'Watchdog', 'observability', 'none'),
            ('null', 'InfoInhibitor', 'observability', 'none'),
        ]
        for receiver, alert, namespace, severity in cases:
            subprocess.run([
                args.amtool, 'config', 'routes', 'test', f'--config.file={configuration}',
                f'--verify.receivers={receiver}', f'alertname={alert}',
                f'namespace={namespace}', f'severity={severity}',
            ], check=True, stdout=subprocess.DEVNULL)
        print(f'Validated Grafana Recreate strategy and {len(cases)} incident-routing scenarios')


if __name__ == '__main__':
    main()
