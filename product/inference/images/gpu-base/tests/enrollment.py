from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import importlib.util
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
import types
import uuid

TEST = Path('/opt/enrollment-test')
FILES = TEST / 'www'
RESULT = TEST / 'result.json'
ARTIFACTS = 'gradiated-test-artifacts.s3.amazonaws.com'
ARTIFACTS_URL = f'https://{ARTIFACTS}:8443'
ROOT = Path('/var/lib/gradiated-kubelet')
CONFIG = Path('/etc/gradiated/kubelet.json')
GPUS = ['GPU-00000000-0000-0000-0000-000000000001', 'GPU-00000000-0000-0000-0000-000000000002']
POD = '6a8f2a52-7b0e-4c1d-9a64-2f1d3c5b8e01'

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

# Replaces install-tailscale.py, which needs the Tailscale control server.
TAILSCALE_INSTALLER = '''
import json, urllib.request
def install(payload):
    with urllib.request.urlopen(f"http://127.0.0.1:{payload['proxy_port']}/healthz", timeout=5) as response:
        assert response.status == 200
    with open("/opt/enrollment-test/tailscale-install.json", "w") as output:
        json.dump(sorted(payload), output)
'''


class Artifacts(BaseHTTPRequestHandler):

    def log_message(self, *_):
        pass

    def do_GET(self):
        path = FILES / self.path.lstrip('/')
        if not re.fullmatch(r'/[A-Za-z0-9._-]+', self.path) or not path.is_file():
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
    grants = ThreadingHTTPServer(('127.0.0.1', 3004), Grants)
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
    return {'image': f'gradiated/test-bundle@sha256:{digest}', 'model_id': 'test/model',
            'release': {'model_path': 'test/model', 'model_revision': 'main', 'runtime_revision': 'test'},
            'gpus': 2, 'cpu': '4', 'memory': '8Gi', 'startup_timeout': 300}


def step(results, name, action):
    try:
        results[name] = {'ok': True, 'value': action()}
    except BaseException:
        results[name] = {'ok': False, 'error': traceback.format_exc()}
    RESULT.write_text(json.dumps(results, indent=2))
    return results[name]['ok']


def install_seed(results):
    # Loads the installer the way ops-mcp's in-place bootstrap script does.
    archive = (TEST / 'host-bundle.tar.gz').read_bytes()
    digest = hashlib.sha256(archive).hexdigest()
    (FILES / 'host-bundle.tar.gz').write_bytes(archive)
    for name in ('host_state', 'host_bundle', 'supervise', 'install_seed'):
        module = types.ModuleType(name)
        module.__file__ = f'/opt/gradiated/kubelet/{name}.py'
        sys.modules[name] = module
        source = (TEST / 'installer' / (name.replace('_seed', '-seed') + '.py')).read_text()
        exec(compile(source, module.__file__, 'exec'), module.__dict__)
    release = {'url': f'{ARTIFACTS_URL}/host-bundle.tar.gz', 'sha256': digest,
               'base_id': Path('/etc/gradiated/base-id').read_text().strip()}
    results['host_bundle'] = digest
    return str(sys.modules['install_seed'].install(release))


def enroll(results, bootstrap_path, runtime):
    spec = importlib.util.spec_from_file_location('gpu_bootstrap', bootstrap_path)
    bootstrap = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bootstrap)
    locate = importlib.util.spec_from_file_location
    installer = TEST / 'install-tailscale.py'
    installer.write_text(TAILSCALE_INSTALLER)

    def tailscale_installer(name, path, *args, **kwargs):
        return locate(name, installer if name == 'tailscale_install' else path, *args, **kwargs)

    bootstrap.importlib = types.SimpleNamespace(util=types.SimpleNamespace(
        spec_from_file_location=tailscale_installer, module_from_spec=importlib.util.module_from_spec))
    instance = str(uuid.uuid4())
    bootstrap.enroll({'instance_id': instance, 'management_token': 'enrollment_test_' + 'a' * 40,
                      'auth_key': 'tskey-auth-enrollment-test', 'api_endpoint': '100.64.0.1',
                      'config': {'instance_id': instance, 'gpu_uuids': GPUS, 'runtimes': {runtime: profile(runtime)}}})


def load_agent(results):
    path = ROOT / 'host' / results['host_bundle'] / 'host-agent.py'
    spec = importlib.util.spec_from_file_location('host_agent', path)
    agent = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(agent)
    return agent


def stage(results, catalogue):
    module = load_agent(results)
    module.atomic_json(ROOT / 'fence.json', {'epoch': 1})
    agent = module.Agent(json.loads(CONFIG.read_text()), ROOT, CONFIG)
    agent.configure(catalogue, 1)
    deadline = time.monotonic() + 180
    while not agent.catalogue_ready:
        if agent.catalogue_task is None or time.monotonic() > deadline:
            log = ROOT / 'bundle-download.log'
            raise RuntimeError('Runtime staging failed:\n' + (log.read_text() if log.exists() else ''))
        time.sleep(.5)
    return sorted(json.loads(CONFIG.read_text())['runtimes'])


def start_task(results, runtime):
    module = load_agent(results)
    directory = ROOT / 'pods' / POD
    directory.mkdir(parents=True)
    state = {'pod': {'metadata': {'uid': POD, 'name': 'enrollment-test'},
                     'spec': {'containers': [{'image': f'gradiated/test-bundle@sha256:{runtime}'}]}},
             'gpu_uuids': GPUS, 'port_base': 18080}
    module.atomic_json(directory / 'state.json', state)
    module.pod_cgroup(POD).mkdir(parents=True, exist_ok=True)
    agent = module.Agent(json.loads(CONFIG.read_text()), ROOT, CONFIG)
    agent.ensure_task(state)
    return state['pod']['metadata']['uid']


def main():
    if sys.argv[1] == 'serve':
        serve()
        return
    results = {'umask': oct(os.umask(0o077))}
    os.umask(int(results['umask'], 8))
    first, second = runtime_bundle('first'), runtime_bundle('second')
    results['runtimes'] = [first, second, runtime_bundle('third')]
    if not step(results, 'install_seed', lambda: install_seed(results)):
        return
    if not step(results, 'enroll', lambda: enroll(results, results['install_seed']['value'], first)):
        return
    step(results, 'stage', lambda: stage(results, {first: profile(first), second: profile(second)}))
    step(results, 'task', lambda: start_task(results, first))


if __name__ == '__main__':
    main()
