#!/usr/bin/env python3
"""Run development training work on spot GPU VMs from any supported provider.

  dev_training.py platforms [--provider P] [--region R]   GPU platforms and presets
  dev_training.py capacity [PLATFORM] [--provider P]      where each GPU can launch now (spot and on-demand)
  dev_training.py up NAME --platform X --preset Y [--provider P] [--region R] [--disk-gib N]
  dev_training.py ls [--provider P]
  dev_training.py ssh NAME [command...]
  dev_training.py s3 NAME                                give the VM the development bucket key
  dev_training.py start NAME | stop NAME                 preemption stops a VM, it is not deleted
  dev_training.py down NAME                              delete the VM, its disk and its tailnet device

Providers: nebius. A VM joins the tailnet as <provider>-<NAME> with tag:dev-training.
It can reach other tag:dev-training nodes, for multi-node training, and nothing else
on the tailnet. tag:dev-machine devices and administrators can reach it, including
with `tailscale ssh root@<provider>-<NAME>`. A machine that is not on the tailnet
joins as tag:dev-machine with
`tailscale up --auth-key="$TAILSCALE_DEV_MACHINE_AUTH_KEY" --advertise-tags=tag:dev-machine`
(ephemeral; userspace networking works).

Credentials come from gradiated/dev/env: from the environment (an ignored .env
loaded as AGENTS.md describes) or, if unset, read with the AWS profile in
AWS_PROFILE (default gradiated-readonly). VMs start with no credentials; `s3`
installs a key that can only use the development training bucket
(DEV_TRAINING_S3_BUCKET), so jobs on the VM can save checkpoints themselves.
These are spot VMs: save results to S3 regularly. A stopped VM still pays for
its disk.
"""

import argparse
import base64
import functools
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nebius import Nebius  # noqa: E402

PROVIDERS = {'nebius': Nebius}
STATE = Path.home() / '.config/gradiated/dev-training'
TAILSCALE = 'https://api.tailscale.com/api/v2'
TAG = 'tag:dev-training'


@functools.lru_cache(maxsize=None)
def dev_env():
    result = subprocess.run(['aws', '--profile', os.environ.get('AWS_PROFILE', 'gradiated-readonly'),
                             '--region', 'us-east-1', 'secretsmanager', 'get-secret-value', '--secret-id',
                             'gradiated/dev/env', '--query', 'SecretString', '--output', 'text'],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=60)
    return json.loads(result.stdout) if result.returncode == 0 else {}


def secret(name):
    value = os.environ.get(name) or dev_env().get(name)
    if not value:
        sys.exit(f'{name} is not set and gradiated/dev/env could not be read (see AGENTS.md)')
    return base64.b64decode(value).decode() if name.endswith('_B64') else value


def state():
    STATE.mkdir(parents=True, exist_ok=True)
    STATE.chmod(0o700)
    return STATE


def provider(name):
    return PROVIDERS[name](secret, state())


def tailscale_token():
    data = urllib.parse.urlencode({'client_id': secret('TAILSCALE_DEV_TRAINING_CLIENT_ID'),
                                   'client_secret': secret('TAILSCALE_DEV_TRAINING_CLIENT_SECRET'),
                                   'grant_type': 'client_credentials'}).encode()
    with urllib.request.urlopen(urllib.request.Request(TAILSCALE + '/oauth/token', data=data), timeout=30) as r:
        return json.load(r)['access_token']


def tailscale(method, path, token, body=None):
    request = urllib.request.Request(TAILSCALE + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={'Authorization': 'Bearer ' + token,
                                              'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        content = response.read()
    return json.loads(content) if content else {}


def join_key(host):
    """A single-use, hour-long, pre-authorized key that can only join as tag:dev-training."""
    return tailscale('POST', '/tailnet/-/keys', tailscale_token(), {
        'capabilities': {'devices': {'create': {'reusable': False, 'ephemeral': False,
                                                'preauthorized': True, 'tags': [TAG]}}},
        'expirySeconds': 3600, 'description': f'dev training {host}'[:50]})['key']


def cloud_init(cloud, host):
    public_key = secret(f'{cloud.name.upper()}_SSH_PUBLIC_KEY_B64').strip()
    return '\n'.join([
        '#cloud-config',
        'users:',
        f'  - name: {cloud.ssh_user}',
        '    sudo: ALL=(ALL) NOPASSWD:ALL',
        '    shell: /bin/bash',
        '    ssh_authorized_keys:',
        f'      - {public_key}',
        'write_files:',
        '  - path: /run/gradiated/tailscale-auth-key',
        "    permissions: '0600'",
        f'    content: {join_key(host)}',
        'runcmd:',
        '  - [sh, -c, "curl -fsSL https://tailscale.com/install.sh | sh"]',
        f'  - [sh, -c, "tailscale up --auth-key=file:/run/gradiated/tailscale-auth-key --hostname={host} --ssh"]',
        '  - [rm, -f, /run/gradiated/tailscale-auth-key]',
        '',
    ])


def find(cloud, name):
    vm = cloud.find(name)
    if not vm:
        sys.exit(f'No {cloud.name} VM named {name}')
    return vm


def platforms(args):
    cloud = provider(args.provider)
    for line in cloud.platforms(args.region or cloud.default_region):
        print(line)


def capacity(args):
    for line in provider(args.provider).capacity(args.platform):
        print(line)


def ssh_ready(address):
    try:
        with socket.create_connection((address, 22), timeout=5):
            return True
    except OSError:
        return False


def up(args):
    if not re.fullmatch('[a-z][a-z0-9-]{1,40}', args.name):
        sys.exit('NAME must be lowercase letters, digits and dashes')
    cloud = provider(args.provider)
    # Names are unique per provider because the other commands find VMs by name alone.
    existing = cloud.find(args.name)
    if existing:
        sys.exit(f"{args.name} already exists in {cloud.name} {existing['region']}")
    region = args.region or cloud.default_region
    host = f'{cloud.name}-{args.name}'
    cloud.create(args.name, region, args.platform, args.preset, args.disk_gib, args.image, cloud_init(cloud, host))
    print(f'Creating {args.name} in {cloud.name} {region}; waiting for it to run')
    deadline = time.time() + 1200
    while time.time() < deadline:
        vm = cloud.find(args.name)
        # Cloud-init starts SSH a minute or so after the provider reports RUNNING.
        if vm and vm['state'] == 'RUNNING' and vm['address'] and ssh_ready(vm['address']):
            print(f"{args.name} is running at {vm['address']}; it joins the tailnet as {host} "
                  'a minute or two after boot')
            return
        time.sleep(15)
    sys.exit(f'{args.name} did not start within 20 minutes; check `ls` and run `down`')


def ls(args):
    for name in [args.provider] if args.provider else sorted(PROVIDERS):
        for vm in provider(name).list():
            print(f"{vm['name']:24} {name:8} {vm['region']:12} {vm['state']:10} {vm['shape']:36} "
                  f"{vm['address'] or '-'}")


def ssh_command(args):
    cloud = provider(args.provider)
    vm = find(cloud, args.name)
    if not vm['address']:
        sys.exit(f'{args.name} has no public IP; is it running?')
    key = state() / f'{cloud.name}-ssh-key'
    content = secret(f'{cloud.name.upper()}_SSH_PRIVATE_KEY_B64').strip() + '\n'
    if not key.exists() or key.read_text() != content:
        key.touch(mode=0o600)
        key.write_text(content)
    return ['ssh', '-i', str(key), '-o', 'IdentitiesOnly=yes', '-o', 'StrictHostKeyChecking=accept-new',
            '-o', f'UserKnownHostsFile={state() / "known_hosts"}', f"{cloud.ssh_user}@{vm['address']}"]


def ssh(args):
    command = ssh_command(args)
    os.execvp('ssh', [*command, *args.command])


def s3(args):
    """Install the bucket-only key as the VM user's default AWS profile, over stdin."""
    credentials = '\n'.join(['[default]', f"aws_access_key_id = {secret('DEV_TRAINING_AWS_ACCESS_KEY_ID')}",
                             f"aws_secret_access_key = {secret('DEV_TRAINING_AWS_SECRET_ACCESS_KEY')}", ''])
    subprocess.run([*ssh_command(args), 'umask 077 && mkdir -p ~/.aws && cat > ~/.aws/credentials && '
                    'printf "[default]\\nregion = us-east-1\\n" > ~/.aws/config'],
                   input=credentials, text=True, check=True, timeout=120)
    print(f"{args.name} can now read and write s3://{secret('DEV_TRAINING_S3_BUCKET')}")


def lifecycle(action):
    def run(args):
        cloud = provider(args.provider)
        getattr(cloud, action)(find(cloud, args.name))
        print(f'{action}: {args.name}')
    return run


def down(args):
    cloud = provider(args.provider)
    # Rerunnable: with the VM already gone it still removes the tailnet device.
    vm = cloud.find(args.name)
    if vm:
        cloud.delete(vm)
        print(f'Deleted {args.name} and its boot disk')
        if vm['address'] and (state() / 'known_hosts').exists():
            # A later VM may get the same address with a new host key.
            subprocess.run(['ssh-keygen', '-R', vm['address'], '-f', str(state() / 'known_hosts')],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    else:
        print(f'No {cloud.name} VM named {args.name}; removing its tailnet device if one is left')
    token = tailscale_token()
    for device in tailscale('GET', '/tailnet/-/devices', token).get('devices', []):
        if device.get('hostname') == f'{cloud.name}-{args.name}' and TAG in device.get('tags', []):
            tailscale('DELETE', f"/device/{device['id']}", token)
            print(f"Removed tailnet device {device['name']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)

    def command(name, run, vm=False, provider_default='nebius'):
        sub = commands.add_parser(name)
        sub.add_argument('--provider', choices=sorted(PROVIDERS), default=provider_default)
        if vm:
            sub.add_argument('name')
        sub.set_defaults(run=run)
        return sub

    command('platforms', platforms).add_argument('--region')
    command('capacity', capacity).add_argument('platform', nargs='?', help='filter, for example b300')
    sub = command('up', up, vm=True)
    sub.add_argument('--platform', required=True, help='for example gpu-h100-sxm; see `platforms`')
    sub.add_argument('--preset', required=True, help='for example 1gpu-16vcpu-200gb')
    sub.add_argument('--region')
    sub.add_argument('--disk-gib', type=int, default=250)
    sub.add_argument('--image', help='provider image family; defaults to Ubuntu 24.04 with CUDA')
    command('ls', ls, provider_default=None)
    command('ssh', ssh, vm=True).add_argument('command', nargs=argparse.REMAINDER)
    command('s3', s3, vm=True)
    for action in ('start', 'stop'):
        command(action, lifecycle(action), vm=True)
    command('down', down, vm=True)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
