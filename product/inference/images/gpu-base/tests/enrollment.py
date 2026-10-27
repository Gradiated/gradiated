from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import io
import json
import os
from pathlib import Path
import re
import ssl
import subprocess
import sys
import tarfile
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid

TEST = Path('/opt/enrollment-test')
FILES = TEST / 'www'
RESULT = TEST / 'result.json'
ARTIFACTS = 'gradiated-test-artifacts.s3.amazonaws.com'
ARTIFACTS_URL = f'https://{ARTIFACTS}:8443'
ROOT = Path('/var/lib/gradiated-kubelet')
CONFIG = Path('/etc/gradiated/kubelet.json')
INSTANCE = '6a8f2a52-7b0e-4c1d-9a64-2f1d3c5b8e00'
TOKEN = 'enrollment_test_' + 'a' * 40
GPUS = ['GPU-00000000-0000-0000-0000-000000000001', 'GPU-00000000-0000-0000-0000-000000000002']
POD = '6a8f2a52-7b0e-4c1d-9a64-2f1d3c5b8e01'
LOGS = ['/var/log/gradiated-kubelet.log', '/var/log/gradiated-control.log', '/var/log/gradiated-tailscale.log',
        str(ROOT / 'bundle-download.log')]

# Stands in for a model runtime writing its torch compile, Triton and Hugging Face caches.
ENTRYPOINT = r'''#!/bin/bash
for directory in "$TORCHINDUCTOR_CACHE_DIR" "$TRITON_CACHE_DIR" "$HF_HOME/hub"; do
  if mkdir -p "$directory" && echo probe >"$directory/enrollment-test"; then
    echo "cache writable: $directory"
  else
    echo "cache not writable: $directory"
  fi
done
echo "runtime started as $(id -un)"
exec sleep infinity
'''


class Artifacts(BaseHTTPRequestHandler):

    def log_message(self, *_):
        pass

    def do_GET(self):
        path = FILES / self.path.split('?')[0].lstrip('/')
        if not re.fullmatch(r'/[A-Za-z0-9._-]+(\?.*)?', self.path) or not path.is_file():
            self.send_error(404)
            return
        data = path.read_bytes()
        start, end = 0, len(data) - 1
        match = re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers.get('Range', ''))
        if match:
            start, end = int(match[1]), min(int(match[2]), len(data) - 1)
            self.send_response(206)
            self.send_header('Content-Range', f'bytes {start}-{end}/{len(data)}')
        else:
            self.send_response(200)
        self.send_header('Content-Length', str(end - start + 1))
        self.end_headers()
        self.wfile.write(data[start:end + 1])


class Grants(BaseHTTPRequestHandler):
    """Stands in for the control API; it is reached through the host's control bridge."""

    def log_message(self, *_):
        pass

    def do_GET(self):
        match = re.fullmatch(r'/api/internal/v1/runtime-bundles/([0-9a-f]{64})', self.path)
        if not match:
            self.send_error(404)
            return
        body = json.dumps({'url': f'{ARTIFACTS_URL}/{match[1]}.tar.gz'}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def serve():
    FILES.mkdir(parents=True, exist_ok=True)
    key, certificate = TEST / 'artifacts.key', TEST / 'artifacts.crt'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '2',
                    '-subj', f'/CN={ARTIFACTS}', '-addext', f'subjectAltName=DNS:{ARTIFACTS}',
                    '-keyout', str(key), '-out', str(certificate)], check=True, capture_output=True)
    Path('/usr/local/share/ca-certificates/enrollment-test.crt').write_bytes(certificate.read_bytes())
    subprocess.run(['update-ca-certificates'], check=True, capture_output=True)
    with open('/etc/hosts', 'a') as hosts:
        hosts.write(f'127.0.0.1 {ARTIFACTS}\n')
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, key)
    artifacts = ThreadingHTTPServer(('127.0.0.1', 8443), Artifacts)
    artifacts.socket = context.wrap_socket(artifacts.socket, server_side=True)
    grants = ThreadingHTTPServer(('127.0.0.1', 13004), Grants)
    threading.Thread(target=grants.serve_forever, daemon=True).start()
    (TEST / 'serving').touch()
    artifacts.serve_forever()


def runtime_bundle(name):
    base_id = Path('/etc/gradiated/base-id').read_bytes()
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz') as archive:
        for member, data, mode in (('base-id', base_id, 0o644), ('entrypoint', ENTRYPOINT.encode(), 0o755),
                                   ('name', name.encode(), 0o644)):
            info = tarfile.TarInfo(member)
            info.size, info.mode = len(data), mode
            archive.addfile(info, io.BytesIO(data))
    digest = hashlib.sha256(output.getvalue()).hexdigest()
    (FILES / f'{digest}.tar.gz').write_bytes(output.getvalue())
    return digest


def profile(digest):
    # The agent must stage this base's bundle; the older base's does not exist.
    bundles = {'older-base': 'f' * 64, Path('/etc/gradiated/base-id').read_text().strip(): digest}
    return {'image': f'gradiated/test-bundle@sha256:{digest}', 'bundles': bundles, 'model_id': 'test/model',
            'release': {'model_path': 'test/model', 'model_revision': 'main', 'runtime_revision': 'test'},
            'gpus': 2, 'cpu': '4', 'memory': '8Gi', 'startup_timeout': 300}


def logs():
    return ''.join(f'--- {path}\n{Path(path).read_text()[-4000:]}\n' for path in LOGS if Path(path).exists())


def step(results, name, action):
    try:
        results[name] = {'ok': True, 'value': action()}
    except BaseException:
        results[name] = {'ok': False, 'error': traceback.format_exc() + logs()}
    RESULT.write_text(json.dumps(results, indent=2))
    return results[name]['ok']


def enroll(results):
    archive = (TEST / 'host-bundle.tar.gz').read_bytes()
    digest = hashlib.sha256(archive).hexdigest()
    (FILES / 'host-bundle.tar.gz').write_bytes(archive)
    results['host_bundle'] = digest
    payload = {'version': 1, 'instance_id': INSTANCE, 'management_token': TOKEN,
               'auth_key': 'tskey-auth-enrollment-test', 'api_endpoint': '100.64.0.1',
               'host_bundle': {'sha256': digest, 'base_id': Path('/etc/gradiated/base-id').read_text().strip(),
                               'url': f'{ARTIFACTS_URL}/host-bundle.tar.gz?X-Amz-Signature=test'}}
    # Runs as ops-mcp runs it over Tailscale SSH: root, with this process's umask 077.
    result = subprocess.run(['/usr/local/bin/gradiated-host', 'enroll'], input=json.dumps(payload),
                            capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError(f'gradiated-host enroll failed: {result.stderr}')
    return json.loads(result.stdout)


def agent(body):
    request = urllib.request.Request('http://127.0.0.1:8887/_kubelet', data=json.dumps(body).encode(),
                                     headers={'Authorization': f'Bearer {TOKEN}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def claim():
    """Takes the host the way the controller does: fence, then claim a new epoch with a term."""
    term = str(uuid.uuid4())
    epoch = agent({'operation': 'claim', 'epoch': agent({'operation': 'fence'})['epoch'], 'term': term})['epoch']
    return {'epoch': epoch, 'term': term}


def stage(results, catalogue):
    lease = results['lease'] = claim()
    agent({'operation': 'configure', 'runtimes': catalogue, **lease})
    deadline = time.monotonic() + 180
    while set(json.loads(CONFIG.read_text()).get('runtimes', {})) != set(catalogue):
        if time.monotonic() > deadline:
            raise RuntimeError('Runtime staging did not finish')
        time.sleep(.5)
    return sorted(json.loads(CONFIG.read_text())['runtimes'])


def start_task(results, runtime):
    lease = results['lease']
    details = profile(runtime)
    resources = {'nvidia.com/gpu': '2', 'cpu': details['cpu'], 'memory': details['memory']}
    pod = {'metadata': {'uid': POD, 'name': 'enrollment-test', 'annotations': {
               'gradiated.com/model-id': details['model_id'], 'gradiated.com/release': json.dumps(details['release'])}},
           'spec': {'nodeName': f'gpu-{INSTANCE}', 'containers': [{
               'name': 'runtime', 'image': details['image'], 'resources': {'limits': resources, 'requests': resources}}]}}
    return agent({'operation': 'create', 'uid': POD, 'pod': pod, **lease})


def main():
    if sys.argv[1] == 'serve':
        serve()
        return
    results = {'umask': oct(os.umask(0o077))}
    os.umask(int(results['umask'], 8))
    first, second = runtime_bundle('first'), runtime_bundle('second')
    results['runtimes'] = [first, second, runtime_bundle('third')]
    if not step(results, 'enroll', lambda: enroll(results)):
        return
    if not step(results, 'stage', lambda: stage(results, {first: profile(first), second: profile(second)})):
        return
    step(results, 'task', lambda: start_task(results, first))


if __name__ == '__main__':
    main()
