import base64
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import uuid


def install(payload):
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", payload['management_token']):
        raise ValueError('A strong host-specific management credential is required')
    instance = str(uuid.UUID(payload['instance_id']))
    inventory = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'], text=True).splitlines()
    root = Path('/var/lib/gradiated-kubelet')
    destination = Path('/opt/gradiated/kubelet')
    for directory in [root, root / 'pods', destination]:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)
    config_path = Path('/etc/gradiated/kubelet.json')
    config = payload.get('config') or {key: payload[key] for key in ['instance_id', 'gpu_uuid', 'bundle_sha256', 'model_id', 'release']}
    config['instance_id'] = instance
    devices = config.get('gpu_uuids') or [config['gpu_uuid']]
    if not devices or len(set(devices)) != len(devices) or not set(devices).issubset(set(inventory)):
        raise ValueError('GPU pool does not match this host')
    config['token_file'] = '/etc/gradiated/kubelet-management.token'
    if config_path.exists() and list((root / 'pods').glob('*/state.json')):
        previous = json.loads(config_path.read_text())
        for key in ['instance_id', 'gpu_uuid', 'gpu_uuids', 'hf_home', 'bundle_sha256', 'model_id', 'release']:
            if previous.get(key) != config.get(key):
                raise ValueError('Cannot change host identity or execution settings with active workloads')
        for key, value in previous.get('runtimes', {}).items():
            if config.get('runtimes', {}).get(key) != value:
                raise ValueError('Cannot alter an enrolled runtime with active workloads')
    token_path = Path(config['token_file'])
    if token_path.exists() and token_path.read_text() != payload['management_token']:
        raise ValueError('Rotate management credentials separately')
    token_path.write_text(payload['management_token'])
    token_path.chmod(0o600)
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    digests = config.get('runtimes', {}).keys() if config.get('runtimes') else [config['bundle_sha256']]
    for digest in digests:
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid runtime digest')
        marker = root / 'bundles' / digest / '.bundle-sha256'
        if marker.read_text().strip() != digest:
            raise ValueError('Runtime bundle is not staged and verified')
    if any(profile.get('environment', {}).get('HOST_IDENTITY_FILE') for profile in config.get('runtimes', {}).values()):
        identity = Path('/etc/gradiated/host-identity.json')
        if not identity.exists():
            subprocess.run(['install', '-m', '600', '-o', 'runtime', '-g', 'runtime',
                            '/etc/nomad/tls/renewal.json', str(identity)], check=True)
    for name in ['host-agent.py', 'supervise.py']:
        path = destination / name
        temporary = path.with_suffix('.new')
        temporary.write_text(payload[name])
        temporary.chmod(0o755)
        temporary.replace(path)
    binary = destination / 'desmondd'
    temporary = binary.with_suffix('.new')
    temporary.write_bytes(base64.b64decode(payload['desmondd']))
    temporary.chmod(0o755)
    temporary.replace(binary)
    pid_path = root / 'supervisor.json'
    if pid_path.exists():
        owner = json.loads(pid_path.read_text())
        try:
            stat = Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(')', 1)[1].split()
            command = Path(f"/proc/{owner['pid']}/cmdline").read_bytes()
            if stat[19] == owner['birth'] and b'/opt/gradiated/kubelet/supervise.py' in command:
                os.kill(owner['pid'], signal.SIGHUP)
                print(json.dumps({'instance_id': instance, 'updated': True}))
                return
        except FileNotFoundError:
            pass
    with (root / 'supervisor.log').open('ab') as log:
        process = subprocess.Popen(['python3', str(destination / 'supervise.py')],
            env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'},
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    birth = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    pid_path.write_text(json.dumps({'pid': process.pid, 'birth': birth}))
    pid_path.chmod(0o600)
    print(json.dumps({'instance_id': instance, 'supervisor_pid': process.pid}))
