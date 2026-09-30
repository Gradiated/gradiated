#!/usr/bin/env python3
"""Validate the pinned UI and OAuth proxy offline, using only fixture credentials."""
import base64
import json
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
import uuid

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / 'infra/environments/prod/us-east-1/kubernetes/workloads/temporal-ui'


def main():
    documents = list(yaml.safe_load_all((CONFIG / 'workload.yaml').read_text()))
    deployment = next(d for d in documents if d['kind'] == 'Deployment')
    images = {c['name']: c['image'] for c in deployment['spec']['template']['spec']['containers']}
    host = os.environ.get('DOCKER_HOST') or subprocess.check_output(
        ['docker', 'context', 'inspect', '--format', '{{.Endpoints.docker.Host}}'], text=True).strip()
    if not host.startswith('unix://'):
        raise RuntimeError('These checks require a local Docker socket')
    docker_base = ['docker', '--host', host]
    docker = docker_base + ['run', '--rm', '--network', 'none', '--user', '1000:1000',
              '--read-only', '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
              '-v', f'{CONFIG}:/config:ro']
    with tempfile.TemporaryDirectory(prefix='temporal-ui-fixture-') as directory:
        auth = Path(directory)
        auth.chmod(0o755)
        (auth / 'client-secret').write_text('local-fixture-client-secret')
        (auth / 'authorization').write_text('Bearer local-fixture-reader-token')
        for path in auth.iterdir():
            path.chmod(0o644)
        result = subprocess.run(docker + ['-v', f'{auth}:/auth:ro',
            '-e', 'TEMPORAL_NAMESPACE=fixture', '-e', 'OAUTH2_PROXY_COOKIE_SECRET=' +
            base64.urlsafe_b64encode(secrets.token_bytes(32)).decode(), images['oauth2-proxy'],
            '--config=/config/oauth2-proxy.cfg', '--alpha-config=/config/oauth2-proxy.yaml',
            '--config-test'], capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr

    container = 'temporal-ui-check-' + uuid.uuid4().hex[:12]
    start = docker + ['--name', container, '-d', '--tmpfs', '/tmp:rw,uid=1000,gid=1000,size=16m',
        '-e', 'TEMPORAL_ADDRESS=fixture.example:7233', '-e', 'TEMPORAL_NAMESPACE=fixture',
        '--entrypoint', '/bin/sh', images['ui'], '/config/start-ui.sh']
    subprocess.run(start, check=True, capture_output=True, timeout=60)
    try:
        for _ in range(50):
            result = subprocess.run(docker_base + ['exec', container, 'wget', '-q', '-O', '-',
                'http://127.0.0.1:8080/api/v1/settings'], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                break
            time.sleep(0.1)
        else:
            raise RuntimeError('Pinned Temporal UI startup timed out')
        settings = json.loads(result.stdout)
        assert settings['DisableWriteActions'] is True
        assert settings['DefaultNamespace'] == 'fixture'
        config = yaml.safe_load(subprocess.check_output(docker_base + ['exec', container, 'cat',
            '/tmp/ui-config/development.yaml'], text=True, timeout=5))
        assert config['host'] == '127.0.0.1'
        assert config['tls'] == {'serverName': 'fixture.example', 'enableHostVerification': True}
    finally:
        subprocess.run(docker_base + ['rm', '-f', container], capture_output=True, timeout=30)

    for variable, value in [('TEMPORAL_ADDRESS', 'fixture:7233\nenableUi: false'),
                            ('TEMPORAL_NAMESPACE', 'fixture\ndisableWriteActions: false')]:
        environment = {'TEMPORAL_ADDRESS': 'fixture.example:7233', 'TEMPORAL_NAMESPACE': 'fixture',
                       variable: value}
        env_args = [arg for k, v in environment.items() for arg in ['-e', k + '=' + v]]
        result = subprocess.run(docker + env_args + ['--entrypoint', '/bin/sh', images['ui'],
            '/config/start-ui.sh'], capture_output=True, timeout=15)
        assert result.returncode != 0, 'Unsafe configuration input was accepted'
    print('Pinned OAuth config and UI startup, loopback binding, verified TLS, write controls and input rejection pass.')


if __name__ == '__main__':
    main()
