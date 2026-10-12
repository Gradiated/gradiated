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
    gpu = subprocess.check_output(['nvidia-smi', '--query-gpu=uuid', '--format=csv,noheader'], text=True).strip()
    if gpu != payload['gpu_uuid']:
        raise ValueError('This Kev worker requires its pinned single-GPU host')
    root = Path('/var/lib/gradiated-kubelet')
    destination = Path('/opt/gradiated/kubelet')
    for directory in [root, root / 'pods', destination]:
        directory.mkdir(parents=True, exist_ok=True)
        directory.chmod(0o755)
    config_path = Path('/etc/gradiated/kubelet.json')
    config = {key: payload[key] for key in ['instance_id', 'gpu_uuid', 'bundle_sha256', 'model_id', 'release']}
    config['token_file'] = '/etc/gradiated/kubelet-management.token'
    if config_path.exists() and list((root / 'pods').glob('*/state.json')):
        if json.loads(config_path.read_text()) != config:
            raise ValueError('Cannot change a host release with active workloads')
    token_path = Path(config['token_file'])
    if token_path.exists() and token_path.read_text() != payload['management_token']:
        raise ValueError('Rotate management credentials separately')
    token_path.write_text(payload['management_token'])
    token_path.chmod(0o600)
    config_path.write_text(json.dumps(config))
    config_path.chmod(0o600)
    marker = root / 'bundles' / config['bundle_sha256'] / '.bundle-sha256'
    if marker.read_text().strip() != config['bundle_sha256']:
        raise ValueError('Runtime bundle is not staged and verified')
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
