import base64
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import uuid


def validate_runtime_update(previous, config, states):
    active = {state['pod']['spec']['containers'][0]['image'].rsplit('@sha256:', 1)[-1] for state in states}
    for key in active:
        if config.get('runtimes', {}).get(key) != previous.get('runtimes', {}).get(key):
            raise ValueError('Cannot alter an active runtime')


def install(payload):
    root = Path('/var/lib/gradiated-kubelet')
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / 'config.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        install_locked(payload)


def install_locked(payload):
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
        validate_runtime_update(previous, config, [json.loads(path.read_text()) for path in (root / 'pods').glob('*/state.json')])
    token_path = Path(config['token_file'])
    if token_path.exists() and token_path.read_text() != payload['management_token']:
        raise ValueError('Rotate management credentials separately')
    digests = config.get('runtimes', {}).keys() if config.get('runtimes') else [config['bundle_sha256']]
    for digest in digests:
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('Invalid runtime digest')
        marker = root / 'bundles' / digest / '.bundle-sha256'
        if marker.read_text().strip() != digest:
            raise ValueError('Runtime bundle is not staged and verified')
    base_path = Path('/etc/gradiated/base-id')
    base_id = payload.get('base_id') or (base_path.read_text().strip() if base_path.exists() else '')
    if not re.fullmatch('[A-Za-z0-9._-]+', base_id):
        raise ValueError('Confirm the retained host base ID before installing the launcher')
    if base_path.exists() and base_path.read_text().strip() != base_id:
        raise ValueError('Cannot change the host base ID in place')
    shared = {}
    exec(compile(payload['host_state.py'], 'host_state.py', 'exec'), shared)
    shared['atomic_write'](token_path, payload['management_token'].encode())
    shared['atomic_json'](config_path, config)
    if not base_path.exists():
        shared['atomic_write'](base_path, (base_id + '\n').encode())
    pid_path = root / 'supervisor.json'
    owner = json.loads(pid_path.read_text()) if pid_path.exists() else None
    supervisor_alive = False
    direct_launcher = False
    if owner:
        try:
            stat = Path(f"/proc/{owner['pid']}/stat").read_text().rsplit(')', 1)[1].split()
            command = Path(f"/proc/{owner['pid']}/cmdline").read_bytes()
            supervisor_alive = stat[0] != 'Z' and stat[19] == owner['birth'] and (
                b'/opt/gradiated/kubelet/supervise.py' in command or b'/opt/gradiated/kubelet/host-launcher.py' in command)
            status_path = root / 'host' / 'status.json'
            status = json.loads(status_path.read_text()) if status_path.exists() else {}
            direct_launcher = supervisor_alive and status.get('launcher_pid') == owner['pid'] and status.get('launcher_birth') == owner['birth']
            legacy_path = root / 'launcher.json'
            if legacy_path.exists():
                direct_launcher |= supervisor_alive and json.loads(legacy_path.read_text()) == owner
        except (OSError, ValueError):
            pass
    shared['atomic_write'](destination / 'host_state.py', payload['host_state.py'].encode())
    (destination / 'host_state.py').chmod(0o644)
    recovery = destination / 'recovery'
    recovery.mkdir(exist_ok=True)
    for name in ['host_state.py', 'host_bundle.py', 'host-agent.py']:
        shared['atomic_write'](recovery / name, payload[name].encode())
        (recovery / name).chmod(0o644)
    shared['atomic_write'](recovery / 'desmondd', base64.b64decode(payload['desmondd']))
    (recovery / 'desmondd').chmod(0o755)
    if not direct_launcher:
        shared['atomic_write'](destination / 'host-launcher.py', payload['supervise.py'].encode())
        shim = "import os\nos.execv('/usr/bin/python3', ['python3', '/opt/gradiated/kubelet/host-launcher.py'])\n"
        shared['atomic_write'](destination / 'host-agent.py', shim.encode())
    if supervisor_alive:
        os.kill(owner['pid'], signal.SIGHUP)
        print(json.dumps({'instance_id': instance, 'updated': True}))
        return
    with (root / 'supervisor.log').open('ab') as log:
        process = subprocess.Popen(['python3', str(destination / 'host-launcher.py')],
            env={'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'},
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    birth = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()[19]
    shared['atomic_json'](pid_path, {'pid': process.pid, 'birth': birth, 'host_launcher': True})
    print(json.dumps({'instance_id': instance, 'supervisor_pid': process.pid}))
