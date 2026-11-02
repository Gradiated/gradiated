"""Exercise the rendered production inhibition rules against Alertmanager."""
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.error import URLError
from urllib.request import Request, urlopen

import yaml


def check_inhibitions(binary, configuration, directory):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]

    configuration = yaml.safe_load(configuration.read_text())
    configuration['route'] = {'receiver': 'local'}
    configuration['receivers'] = [{'name': 'local'}]
    local_config = Path(directory) / 'inhibitions.yaml'
    local_config.write_text(yaml.safe_dump(configuration))
    base = f'http://127.0.0.1:{port}'

    def request(path, body=None):
        payload = None if body is None else json.dumps(body).encode()
        with urlopen(Request(base + path, data=payload,
                             headers={'Content-Type': 'application/json'}), timeout=2) as response:
            content = response.read()
            return json.loads(content) if content else None

    def wait_for(read, predicate):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                result = read()
                if predicate(result):
                    return result
            except (URLError, TimeoutError):
                pass
            if process.poll() is not None:
                raise AssertionError('Local Alertmanager exited before inhibition checks completed')
            time.sleep(0.1)
        raise AssertionError('Timed out waiting for local Alertmanager inhibition state')

    source = {'alertname': 'DatabaseRestoreVerificationFailed', 'namespace': 'gradiated',
              'job_name': 'restore-clickhouse-check-a', 'severity': 'warning', 'service': 'security'}
    generic = {**source, 'alertname': 'KubeJobFailed', 'service': 'kube-state-metrics'}
    host = {'alertname': 'GpuHostTelemetryStale', 'node': 'gpu-test-host',
            'instance_id': 'test-host', 'severity': 'warning', 'service': 'inference'}
    node = {'alertname': 'KubeNodeNotReady', 'node': 'gpu-test-host',
            'severity': 'warning', 'service': 'kube-state-metrics'}
    monitor = {'alertname': 'InferenceProbeMonitoringStalled', 'service': 'worker', 'severity': 'critical'}
    capacity = {'alertname': 'ModelNoReadyReplicas', 'model': 'test/model', 'severity': 'critical'}
    severe = {'alertname': 'GatewaySevereGenerationFailures', 'deployment': 'test-a', 'severity': 'critical'}
    loop = {'alertname': 'WorkerLoopDown', 'loop': 'inference_probes', 'service': 'worker', 'severity': 'critical'}
    probe = {'alertname': 'InferenceModelProbeFailed', 'model': 'test/model', 'severity': 'critical'}
    runtime = {'alertname': 'GatewayRuntimeFailures', 'deployment': 'test-a', 'severity': 'critical'}
    cases = [
        ('matching recovery job', generic, True),
        ('different recovery job', {**generic, 'job_name': 'restore-postgres-check-b'}, False),
        ('other namespace', {**generic, 'namespace': 'other'}, False),
        ('critical generic alert', {**generic, 'severity': 'critical', 'pod': 'other-exporter'}, False),
        ('unrelated job', {**generic, 'job_name': 'application-maintenance'}, False),
        ('GPU node readiness duplicate', node, True),
        ('GPU node reachability duplicate', {**node, 'alertname': 'KubeNodeUnreachable'}, True),
        ('other GPU node', {**node, 'node': 'gpu-other-host'}, False),
        ('CPU node', {**node, 'node': 'cpu-node'}, False),
        ('critical node alert', {**node, 'severity': 'critical', 'pod': 'other-exporter'}, False),
        ('probe loop duplicate', loop, True),
        ('other worker loop', {**loop, 'loop': 'settlement'}, False),
        ('same unavailable model', probe, True),
        ('other unavailable model', {**probe, 'model': 'other/model'}, False),
        ('same failing deployment', runtime, True),
        ('other failing deployment', {**runtime, 'deployment': 'test-b'}, False),
    ]
    with (Path(directory) / 'alertmanager.log').open('w') as log:
        process = subprocess.Popen([
            binary, f'--config.file={local_config}', f'--storage.path={directory}/state',
            f'--web.listen-address=127.0.0.1:{port}', '--cluster.listen-address=',
        ], stdout=log, stderr=log)
        try:
            wait_for(lambda: request('/api/v2/status'), lambda result: bool(result))
            sources = [source, host, monitor, capacity, severe]
            request('/api/v2/alerts', [{'labels': labels} for labels in sources] +
                    [{'labels': labels} for _, labels, _ in cases])

            def verified(alerts):
                for _, labels, inhibited in cases:
                    matching = [alert for alert in alerts if alert['labels'] == labels]
                    if len(matching) != 1 or bool(matching[0]['status']['inhibitedBy']) != inhibited:
                        return False
                return True

            wait_for(lambda: request('/api/v2/alerts'), verified)
            request('/api/v2/alerts', [{'labels': labels, 'endsAt': '2000-01-01T00:00:01Z',
                                      'startsAt': '2000-01-01T00:00:00Z'} for labels in sources])
            wait_for(lambda: request('/api/v2/alerts'),
                     lambda alerts: all(any(alert['labels'] == labels and
                                            not alert['status']['inhibitedBy'] for alert in alerts)
                                        for labels in [generic, node, loop, probe, runtime]))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    print(f'Validated {len(cases)} inhibition cases and source resolution')
