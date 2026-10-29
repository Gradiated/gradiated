import hmac
import json
import os
import secrets
import subprocess
import time
import urllib.error
import urllib.request

from . import files, schema, seed
from .paths import AGENT_PORT, DESMOND, DOWNLOADER, Layout
from .tailscale import BOOTSTRAP_TAG, INFERENCE_TAG, Tailscale, tags

PRODUCTS = {'B300': 'B300', 'RTX PRO 6000': 'RTX-PRO-6000'}


# Its messages never include payload values, which hold credentials.
class EnrollmentError(ValueError):
    pass


def nvidia_smi(*arguments):
    return subprocess.run(['nvidia-smi', *arguments], capture_output=True, text=True, check=True,
                          timeout=30).stdout.splitlines()


def read_json(path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None


def check_identity(layout, instance, token):
    existing = read_json(layout.config)
    if existing is None:
        if [line for line in nvidia_smi('--query-compute-apps=pid', '--format=csv,noheader') if line.strip()]:
            raise EnrollmentError('GPU workloads must drain before enrollment')
        return None
    try:
        enrolled_token = layout.management_token.read_text()
    except FileNotFoundError:
        enrolled_token = ''
    if existing.get('instance_id') != instance or not hmac.compare_digest(enrolled_token, token):
        raise EnrollmentError('This host is enrolled with a different identity; rotate credentials separately')
    return existing


def wait_for_agent(instance, token, port, seconds):
    request = urllib.request.Request(f'http://127.0.0.1:{port}/_kubelet', data=b'{"operation":"ping"}',
                                     headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'})
    deadline = time.monotonic() + seconds
    while True:
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                if json.load(response).get('instance_id') == instance:
                    return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        if time.monotonic() > deadline:
            raise EnrollmentError('The host agent did not start')
        time.sleep(1)


def inventory(layout):
    names = nvidia_smi('--query-gpu=name', '--format=csv,noheader')
    products = {product for name in names for marker, product in PRODUCTS.items() if marker in name}
    if not names or len(set(names)) != 1 or len(products) != 1:
        raise EnrollmentError('Enrollment needs a homogeneous B300 or RTX PRO 6000 GPU set')
    quota = (layout.cgroup / 'cpu.max').read_text().split()
    cpu = os.cpu_count() if quota[0] == 'max' else int(quota[0]) // int(quota[1])
    limit = (layout.cgroup / 'memory.max').read_text().strip()
    if limit == 'max':
        total = next(line for line in layout.meminfo.read_text().splitlines() if line.startswith('MemTotal:'))
        limit = int(total.split()[1]) * 1024
    # Headroom for the host agent, Tailscale and the page cache.
    return {'gpu_count': len(names), 'gpu_product': products.pop(), 'cpu': max(1, int(cpu * 0.9)),
            'memory_gib': max(1, int(limit) // 1024 ** 3 - 16)}


# Every step checks what is already there, so enrolling again with the same payload is safe.
def enroll(document, layout=Layout(), download=seed.fetch, agent_port=AGENT_PORT, agent_seconds=120):
    payload = schema.payload(document)
    instance, token = payload['instance_id'], payload['management_token']
    root = layout.account('root')
    existing = check_identity(layout, instance, token)
    tailscale = Tailscale(layout)
    current = tailscale.config()
    if current is None or current.get('instance_id', instance) != instance:
        raise EnrollmentError('Tailscale must run as this pod\'s bootstrap identity or as this host')

    gpus = nvidia_smi('--query-gpu=uuid', '--format=csv,noheader')

    seed.install(layout, payload['host_bundle'], download)
    # The host agent stages runtime bundles here as the downloader account.
    files.directory(layout.state / 'bundles', 0o755, layout.account(DOWNLOADER))
    files.write(layout.control_config, json.dumps({'api': payload['api_endpoint']}), 0o644, root)
    files.write(layout.management_token, token, 0o600, root)
    if not layout.runtime_token.exists():
        files.write(layout.runtime_token, secrets.token_urlsafe(48), 0o600, layout.account(DESMOND))
    # gradiated-host start launches the host agent once this file exists, so it is written last.
    # An enrolled host keeps its own: the host agent rewrites it as it stages runtimes.
    if existing is None:
        config = {'instance_id': instance, 'gpu_uuids': gpus, 'token_file': str(layout.management_token),
                  'runtimes': {}}
        files.write(layout.config, json.dumps(config), 0o600, root)
    wait_for_agent(instance, token, agent_port, agent_seconds)

    # A bootstrap device is promoted; a failed promotion leaves one, so a retry promotes it again.
    status = tailscale.status() or {}
    live = tags(status)
    bootstrap = BOOTSTRAP_TAG in live
    address = next((ip for ip in status.get('TailscaleIPs') or [] if '.' in ip), None)
    if not address or not (bootstrap or INFERENCE_TAG in live):
        raise EnrollmentError('The tailnet identity is not ready')
    result = schema.result({'version': 1, 'tailscale_ip': address, **inventory(layout), 'promotion': bootstrap})
    if bootstrap:
        tailscale.stage_promotion(instance, payload['auth_key'])
    return result
