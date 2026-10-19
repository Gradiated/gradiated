#!/usr/bin/env python3
"""Render Falco's production chart and optionally check the patched image's plugin ABI."""
import argparse
from pathlib import Path
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
APPLICATION = ROOT / 'infra/environments/prod/us-east-1/kubernetes/platform/falco.yaml'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chart-dir', help='Already downloaded copy of the pinned chart')
    parser.add_argument('--image', help='Locally available image for the optional Docker ABI check')
    args = parser.parse_args()
    app = yaml.safe_load(APPLICATION.read_text())
    source = app['spec']['source']
    values = source['helm']['valuesObject']
    artifact = values['falcoctl']['config']['artifact']
    assert artifact['allowedTypes'] == ['rulesfile']
    assert artifact['install']['resolveDeps'] is False
    assert artifact['install']['refs'] == ['falco-rules:5.2.0']
    assert values['falcoctl']['artifact']['follow']['enabled'] is False
    assert values['collectors']['containerEngine']['enabled'] is False
    assert '@sha256:' in values['image']['tag'], 'Pin the scanned private image digest'

    with tempfile.TemporaryDirectory(prefix='falco-config-check-') as directory:
        folder = Path(directory)
        folder.chmod(0o755)
        values_file = folder / 'values.yaml'
        values_file.write_text(yaml.safe_dump(values))
        chart = [args.chart_dir] if args.chart_dir else [source['chart'], '--repo', source['repoURL'],
                                                       '--version', source['targetRevision']]
        rendered = subprocess.check_output(['helm', 'template', 'falco', *chart,
            '--namespace', 'falco', '-f', str(values_file)], text=True, timeout=120)
        docs = [d for d in yaml.safe_load_all(rendered) if d]
        daemon = next(d for d in docs if d['kind'] == 'DaemonSet')
        assert daemon['spec']['updateStrategy']['rollingUpdate']['maxUnavailable'] == 1
        pod = daemon['spec']['template']['spec']
        sensor = next(c for c in pod['containers'] if c['name'] == 'falco')
        assert not sensor['securityContext'].get('privileged', False)
        assert set(sensor['securityContext']['capabilities']['add']) == {
            'BPF', 'SYS_RESOURCE', 'PERFMON', 'SYS_PTRACE'}
        assert not any(m['mountPath'] == '/usr/share/falco/plugins' for m in sensor['volumeMounts']), \
            'An emptyDir would hide the patched image plugin'
        config_mount = next(m for m in sensor['volumeMounts'] if m['mountPath'] == '/etc/falco/config.d')
        config_volume = next(v for v in pod['volumes'] if v['name'] == config_mount['name'])
        assert 'emptyDir' in config_volume, 'Hide the upstream automatic plugin configuration snippet'
        socket = next(m for m in sensor['volumeMounts'] if m['mountPath'] == '/host/run/containerd')
        assert socket['readOnly'] is True
        volume = next(v for v in pod['volumes'] if v['name'] == socket['name'])
        assert volume['hostPath'] == {'path': '/run/containerd', 'type': 'Directory'}
        assert any(d['kind'] == 'ServiceMonitor' for d in docs)

        config = next(yaml.safe_load(d['data']['falco.yaml']) for d in docs
                      if d['kind'] == 'ConfigMap' and 'falco.yaml' in d.get('data', {}))
        assert config['engine']['kind'] == 'modern_ebpf'
        assert config['metrics']['enabled'] is True
        assert config['load_plugins'] == ['container']
        plugin = next(p for p in config['plugins'] if p['name'] == 'container')
        assert plugin['library_path'] == 'libcontainer.so'
        engines = plugin['init_config']['engines']
        assert engines['cri'] == {'enabled': True, 'sockets': ['/run/containerd/containerd.sock']}
        assert all(not e['enabled'] for name, e in engines.items() if name != 'cri')

        if args.image:
            config_file = folder / 'falco.yaml'
            config_file.write_text(yaml.safe_dump(config))
            empty_config = folder / 'config.d'
            empty_config.mkdir(mode=0o755)
            result = subprocess.run(['docker', 'run', '--rm', '--network', 'none',
                '--cap-drop', 'ALL', '--entrypoint', '/usr/bin/falco',
                '-v', f'{config_file}:/check.yaml:ro',
                '-v', f'{empty_config}:/etc/falco/config.d:ro', args.image,
                '-c', '/check.yaml', '--list-plugins'], capture_output=True, text=True, timeout=45)
            assert result.returncode == 0, result.stderr
            for field in ['Name: container', 'Version: 0.7.5', 'Async Events', 'Field Extraction']:
                assert field in result.stdout, result.stdout
    print('Falco pinned plugin, CRI metadata configuration, socket, least privilege, metrics and rolling update checks pass.')


if __name__ == '__main__':
    main()
