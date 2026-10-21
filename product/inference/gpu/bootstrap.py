#!/usr/bin/env python3
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import hmac
import json
import os
from pathlib import Path
import pwd
import re
import secrets
import sys
import subprocess
import threading
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host_state import atomic_json, atomic_write

ROOT = Path('/var/lib/gradiated-kubelet')
CONFIG = Path('/etc/gradiated/kubelet.json')


def private_json(path, value, uid=0, gid=0):
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, value, uid, gid)


def validate(payload, inventory):
    instance = str(uuid.UUID(payload['instance_id']))
    if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', payload['management_token']):
        raise ValueError('A host-specific management key is required')
    config = payload['config']
    if config['instance_id'] != instance:
        raise ValueError('Bootstrap identity mismatch')
    devices = config.get('gpu_uuids') or inventory
    if not devices or len(set(devices)) != len(devices) or not set(devices).issubset(inventory):
        raise ValueError('Bootstrap GPU inventory mismatch')
    if not config.get('runtimes'):
        raise ValueError('At least one pinned runtime is required')
    for digest, profile in config['runtimes'].items():
        if not re.fullmatch('[0-9a-f]{64}', digest) or not profile['image'].endswith('@sha256:' + digest):
            raise ValueError('Runtime digest mismatch')
    return {**config, 'gpu_uuids': devices, 'token_file': '/etc/gradiated/kubelet-management.token'}


def promotion_pending(config=Path('/etc/gradiated/tailscale.json'), reauth=Path('/var/lib/gradiated-tailscale/reauth')):
    """True while the pod is still tag:gpu-bootstrap, before its staged re-authentication."""
    return reauth.exists() or (config.exists() and json.loads(config.read_text()).get('bootstrap') is True)


def enroll(payload):
    active = list((ROOT / 'pods').glob('*/state.json'))
    if active and not CONFIG.exists():
        raise ValueError('Bootstrap cannot replace an active GPU worker')
    inventory = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'], text=True).splitlines()
    config = validate(payload, inventory)
    if CONFIG.exists():
        previous = json.loads(CONFIG.read_text())
        token_path = Path(previous.get('token_file', config['token_file']))
        devices = previous.get('gpu_uuids', [])
        matching = previous.get('instance_id') == config['instance_id'] and previous.get('token_file') == config['token_file'] and bool(devices) and set(devices).issubset(inventory) and token_path.exists() and hmac.compare_digest(token_path.read_text(), payload['management_token'])
        staged = all((ROOT / 'bundles' / digest / '.bundle-sha256').exists() and (ROOT / 'bundles' / digest / '.bundle-sha256').read_text().strip() == digest for digest in previous.get('runtimes', {}))
        if matching and staged and previous.get('runtimes'):
            subprocess.run(['bash', '/opt/gradiated/bin/start-tailscale'], check=True, timeout=10)
            return
        if active:
            raise ValueError('Bootstrap cannot replace an active GPU worker')
    # A bootstrap pod cannot reach the control API until its staged
    # re-authentication promotes it to tag:gpu-inference after enrollment. The
    # host agent stages runtime bundles from the controller catalogue then.
    if promotion_pending():
        config['runtimes'] = {}
    ROOT.mkdir(parents=True, exist_ok=True)
    ROOT.chmod(0o755)
    (ROOT / 'pods').mkdir(exist_ok=True)
    private_json(Path('/etc/gradiated/host-identity.json'), {'instance_id': config['instance_id']})
    private_json(CONFIG, config)
    token_path = Path(config['token_file'])
    atomic_write(token_path, payload['management_token'].encode())
    account = pwd.getpwnam('desmond')
    local_key = Path('/etc/gradiated/runtime-access.token')
    atomic_write(local_key, secrets.token_urlsafe(48).encode(), account.pw_uid, account.pw_gid)

    class Health(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            self.send_response(200 if self.path == '/healthz' else 404)
            self.end_headers()

    health = ThreadingHTTPServer(('127.0.0.1', 8889), Health)
    threading.Thread(target=health.serve_forever, daemon=True).start()
    try:
        scripts = Path(__file__).resolve().parent
        if not (scripts / 'install-tailscale.py').is_file():scripts = Path('/opt/gradiated/tailscale-scripts')
        spec = importlib.util.spec_from_file_location('tailscale_install', scripts / 'install-tailscale.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        names = {'run-tailscale': 'run-tailscale.sh', 'start-tailscale': 'start-tailscale.sh',
                 'forward-control': 'control-listener.py' if (scripts / 'control-listener.py').exists() else 'forward-control.py', 'run-control': 'run-control.sh', 'start-control': 'start-control.sh'}
        module.install({'instance_id': config['instance_id'], 'auth_key': payload['auth_key'], 'proxy_port': 8889,
                        'control_endpoints': {'api': payload['api_endpoint']},
                        'scripts': {name: (scripts / filename).read_text() for name, filename in names.items()}})
        bundles = ROOT / 'bundles'
        bundles.mkdir(exist_ok=True)
        downloader = pwd.getpwnam('downloader')
        os.chown(bundles, downloader.pw_uid, downloader.pw_gid)
        fetch = scripts / "fetch-runtime"
        if not fetch.is_file():fetch = Path("/opt/gradiated/bin/fetch-runtime")
        for digest in config['runtimes']:
            subprocess.run(['runuser', '-u', 'downloader', '--', str(fetch),
                f's3::https://gradiated-prod-model-artifacts-873716897517.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz',
                digest, str(bundles / digest)], check=True, timeout=1800)
    finally:
        health.shutdown()
        health.server_close()


def main():
    public_key = os.environ.pop('PUBLIC_KEY', '')
    break_glass = os.environ.pop('GRADIATED_BREAK_GLASS_SSH', '') == '1'
    encoded = os.environ.pop('GRADIATED_GPU_BOOTSTRAP', '')
    if public_key and break_glass:
        ssh = Path('/root/.ssh')
        ssh.mkdir(mode=0o700, exist_ok=True)
        key = ssh / 'authorized_keys'
        key.write_text(public_key + '\n')
        key.chmod(0o600)
        subprocess.run(['ssh-keygen', '-A'], check=True)
        subprocess.run(['/usr/sbin/sshd'], check=True)
    if encoded:
        try:
            enroll(json.loads(base64.b64decode(encoded)))
        except Exception as error:
            print(f'GPU bootstrap failed: {type(error).__name__}; Tailscale SSH remains available.', flush=True)
            while True:
                time.sleep(60)
    if not CONFIG.exists():
        print('GPU enrollment is required; Tailscale SSH remains available.', flush=True)
        while True:
            time.sleep(60)
    subprocess.run(['bash', '/opt/gradiated/bin/start-tailscale'], check=True, timeout=10)
    birth = Path(f'/proc/{os.getpid()}/stat').read_text().rsplit(')', 1)[1].split()[19]
    private_json(ROOT / 'supervisor.json', {'pid': os.getpid(), 'birth': birth})
    os.execv('/usr/bin/python3', ['python3', '/opt/gradiated/kubelet/supervise.py'])


if __name__ == '__main__':
    main()
