#!/usr/bin/env python3
"""Run development training work on spot or on-demand GPU VMs from any supported provider.

  dev_training.py search [--provider P[,P]] [--gpu G] [--term T] [--region R] [--min-gpus N]
                         [--max-gpus N] [--max-price USD_PER_GPU_HOUR] [--all] [--json]
                                                         compute available now, cheapest per GPU-hour first
                                                         (alias: prices)
  dev_training.py platforms --provider P [--region R]    GPU platforms and presets
  dev_training.py up NAME --platform X [--preset Y] [--provider P] [--region R] [--term spot|on-demand]
                         [--max-price USD_PER_GPU_HOUR] [--disk-gib N]
  dev_training.py ls [--provider P[,P]]
  dev_training.py ssh [--vm N] NAME [command...]       N picks one of the VMs Ornn splits a node into
  dev_training.py s3 NAME                                give the VM the development bucket key
  dev_training.py start NAME | stop NAME                 preemption stops a VM, it is not deleted
  dev_training.py down NAME                              delete the VM, its disk and its tailnet device

Providers: nebius and ornn, both virtual machines. --provider picks one or more
(repeat it or separate with commas); without it, search and ls cover every
provider, commands that take NAME find the VM on whichever provider has it, and
up takes the provider from the platform's name. `search` lists what each sells
with what is available now and the arguments for `up`. Spot VMs can be taken back at any time;
on-demand VMs cost more and run until stopped (Ornn's also end when the seller's
listing ends).

A VM joins the tailnet as <provider>-<NAME> with tag:dev-training and
tag:dev-training-<provider>. It can reach other VMs from the same provider, for
multi-node training, and nothing else on the tailnet: not production, EKS, people's
devices, or another provider's VMs. tag:dev-machine devices and administrators can reach it, including
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
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nebius import Nebius  # noqa: E402
from ornn import Ornn  # noqa: E402

PROVIDERS = {'nebius': Nebius, 'ornn': Ornn}
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


def provider_list(value):
    names = [name.strip() for name in value.split(',') if name.strip()]
    unknown = [name for name in names if name not in PROVIDERS]
    if unknown or not names:
        raise argparse.ArgumentTypeError(f"choose from {', '.join(sorted(PROVIDERS))}")
    return names


def each_provider(only, run):
    """Run for the chosen providers, or every provider, skipping one that cannot be reached when none was chosen."""
    for name in sorted(set(only)) if only else sorted(PROVIDERS):
        try:
            run(name, provider(name))
        # A provider error, or any failure such as a hung CLI or a malformed answer.
        except (SystemExit, Exception) as error:
            if only:
                raise
            print(f'skipping {name}: {error}', file=sys.stderr)


def locate(args, strict=True):
    """The provider and VM for args.name: on --provider, or on whichever provider has it.

    A provider that cannot be checked is not proof the VM is absent: strict
    lookups, used by every command but `up`, stop rather than act on a guess.
    """
    if args.provider:
        cloud = provider(args.provider)
        return cloud, cloud.find(args.name)
    found, unchecked = [], []
    for name in sorted(PROVIDERS):
        try:
            cloud = provider(name)
            vm = cloud.find(args.name)
        except (SystemExit, Exception) as error:
            unchecked.append(f'{name} ({error})')
            continue
        if vm:
            found.append((cloud, vm))
    if unchecked and (strict or not found):
        message = f"Could not check {'; '.join(unchecked)} for {args.name}"
        if strict:
            sys.exit(f'{message}; pass --provider')
        print(message, file=sys.stderr)
    if len(found) > 1:
        sys.exit(f"{args.name} exists on {' and '.join(c.name for c, _ in found)}; pass --provider")
    return found[0] if found else (None, None)


def tailscale_token(client='TAILSCALE_DEV_TRAINING'):
    data = urllib.parse.urlencode({'client_id': secret(f'{client}_CLIENT_ID'),
                                   'client_secret': secret(f'{client}_CLIENT_SECRET'),
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


def join_key(cloud, host):
    """A single-use, hour-long, pre-authorized key that joins as tag:dev-training and the provider's tag.

    The provider tag confines node-to-node traffic to one provider, so a VM on
    one provider's hardware cannot reach VMs on another's. The provider's own
    OAuth client holds exactly these two tags, as Tailscale requires.
    """
    token = tailscale_token(f'TAILSCALE_DEV_TRAINING_{cloud.name.upper()}')
    return tailscale('POST', '/tailnet/-/keys', token, {
        'capabilities': {'devices': {'create': {'reusable': False, 'ephemeral': cloud.ephemeral,
                                                'preauthorized': True,
                                                'tags': [TAG, f'{TAG}-{cloud.name}']}}},
        'expirySeconds': 3600, 'description': f'dev training {host}'[:50]})['key']


def hosts(host, vm):
    """Tailnet names of a VM's machines: <provider>-<NAME>, then <provider>-<NAME>--2 and on for a split node.

    NAME cannot contain --, so these never collide with another VM's name.
    """
    return [host if i == 0 else f'{host}--{i + 1}' for i in range(max(len(vm['machines']), 1))]


def join_over_ssh(cloud, name, host, vm):
    """Join each machine of a provider without cloud-init to the tailnet.

    Each gets its own single-use key, on stdin, never in a command line.
    """
    for index, machine_host in enumerate(hosts(host, vm)):
        join_machine(cloud, name, machine_host, index)


def join_machine(cloud, name, host, index):
    script = '; '.join([
        'set -eu',
        'umask 077',
        'mkdir -p /run/gradiated',
        'cat > /run/gradiated/tailscale-auth-key',
        '(command -v tailscale >/dev/null || curl -fsSL https://tailscale.com/install.sh | sh) </dev/null',
        f'tailscale up --auth-key=file:/run/gradiated/tailscale-auth-key --hostname={host} --ssh',
        'rm -f /run/gradiated/tailscale-auth-key',
    ])
    key = join_key(cloud, host)
    for _ in range(10):
        ssh, *options = ssh_command(cloud, name, index)
        # The SSH port can open before the account key is installed; retry until it is.
        result = subprocess.run([ssh, '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=20', *options,
                                 'sudo sh -c ' + shlex.quote(script)], input=key + '\n', text=True, timeout=600)
        if result.returncode == 0:
            return
        time.sleep(15)
    sys.exit(f'Could not join {name} to the tailnet over SSH; run `down` and try again')


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
        f'    content: {join_key(cloud, host)}',
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


def located(args):
    cloud, vm = locate(args)
    if not vm:
        sys.exit(f"No VM named {args.name}{' on ' + args.provider if args.provider else ''}")
    return cloud


def platforms(args):
    cloud = provider(args.provider)
    for line in cloud.platforms(args.region or cloud.default_region):
        print(line)


def matches(args, offer):
    return ((not args.gpu or args.gpu.lower() in offer['gpu'].lower())
            and (not args.region or args.region.lower() in offer['region'].lower())
            and offer['gpus'] >= args.min_gpus and (not args.max_gpus or offer['gpus'] <= args.max_gpus)
            and (args.max_price is None or offer['gpu_hour'] <= args.max_price)
            # Hide offers known to be sold out; a provider that cannot tell shows as unknown.
            and (args.all or offer['available'] is None or offer['available'] > 0))


def search(args):
    rows = []

    def collect(name, cloud):
        rows.extend({**offer, 'provider': name, 'virtualization': cloud.virtualization}
                    for offer in cloud.offers(args.term) if matches(args, offer))
    each_provider(args.provider, collect)
    rows.sort(key=lambda r: (r['gpu_hour'], r['hour'], -(r['available'] or 0)))
    if args.json:
        print(json.dumps(rows, indent=1))
        return
    print(f"{'$/GPU-hr':>8} {'$/hr':>8} {'GPUS':>4} {'TERM':9} {'PROVIDER':8} {'VIRT':10} {'AVAIL':>5} "
          f"{'GPU':18} {'REGION':12} UP")
    for r in rows:
        available = '-' if r['available'] is None else str(r['available'])
        print(f"{r['gpu_hour']:8.2f} {r['hour']:8.2f} {r['gpus']:4} {r['term']:9} {r['provider']:8} "
              f"{r['virtualization']:10} {available:>5} {r['gpu']:18} {r['region']:12} {r['up']} --term {r['term']}")


def up(args):
    if not re.fullmatch('[a-z][a-z0-9-]{1,40}', args.name) or '--' in args.name or args.name.endswith('-'):
        sys.exit('NAME must be lowercase letters, digits and single dashes')
    if not args.provider:
        owners = [name for name, cls in PROVIDERS.items() if re.match(cls.platform_pattern, args.platform)]
        if len(owners) != 1:
            sys.exit(f'Cannot tell the provider of platform {args.platform}; pass --provider')
        args.provider = owners[0]
    cloud = provider(args.provider)
    # Names are unique across providers because the other commands find VMs by name alone.
    other, existing = locate(argparse.Namespace(name=args.name, provider=None), strict=False)
    if existing:
        sys.exit(f"{args.name} already exists in {other.name} {existing['region']}")
    region = args.region or cloud.default_region
    host = f'{cloud.name}-{args.name}'
    cloud.create(args.name, region, args.platform, args.preset, args.disk_gib, args.image,
                 lambda: cloud_init(cloud, host), term=args.term, max_price=args.max_price)
    print(f"Creating {args.term} {args.name} in {cloud.name} {region or ''}; waiting for it to run")
    started = time.time()
    while time.time() < started + 1800:
        vm = cloud.find(args.name)
        if not vm and time.time() > started + 120:
            # Ornn ends a reservation whose VMs cannot start.
            sys.exit(f'{args.name} disappeared before it ran; check `ls` and the provider console')
        if vm and vm['state'] == 'RUNNING' and vm['address']:
            if cloud.cloud_init:
                print(f"{args.name} is running at {vm['address']}; it joins the tailnet as {host} "
                      'a minute or two after boot')
            else:
                join_over_ssh(cloud, args.name, host, vm)
                print(f"{args.name} is running at {vm['address']} and joined the tailnet as "
                      f"{', '.join(hosts(host, vm))}")
            return
        if vm and vm['state'] in ('ERROR', 'COMPLETED', 'CANCELLED'):
            sys.exit(f"{args.name} is {vm['state']}; check `ls` and run `down`")
        time.sleep(15)
    sys.exit(f'{args.name} did not start within 30 minutes; check `ls` and run `down`')


def ls(args):
    def show(name, cloud):
        for vm in cloud.list():
            print(f"{vm['name']:24} {name:8} {vm['term']:9} {vm['region']:12} {vm['state']:10} {vm['shape']:36} "
                  f"{vm['address'] or '-'}")
    each_provider(args.provider, show)


def ssh_command(cloud, name, index=0):
    vm = find(cloud, name)
    if index >= len(vm['machines']):
        sys.exit(f'{name} has no running VM {index + 1}; is it running? (`ls` shows how many VMs it has)')
    machine = vm['machines'][index]
    key = state() / f'{cloud.name}-ssh-key'
    content = secret(f'{cloud.name.upper()}_SSH_PRIVATE_KEY_B64').strip() + '\n'
    if not key.exists() or key.read_text() != content:
        key.touch(mode=0o600)
        key.write_text(content)
    return ['ssh', '-i', str(key), '-p', str(machine['port']), '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={state() / "known_hosts"}',
            f"{machine['user']}@{machine['address']}"]


def ssh(args):
    command = ssh_command(located(args), args.name, args.vm - 1)
    os.execvp('ssh', [*command, *args.command])


def s3(args):
    """Install the bucket-only key as the VM user's default AWS profile, over stdin."""
    credentials = '\n'.join(['[default]', f"aws_access_key_id = {secret('DEV_TRAINING_AWS_ACCESS_KEY_ID')}",
                             f"aws_secret_access_key = {secret('DEV_TRAINING_AWS_SECRET_ACCESS_KEY')}", ''])
    cloud = located(args)
    vm = find(cloud, args.name)
    if vm['state'] != 'RUNNING':
        # A split Ornn node lists only its running VMs; configure them all at once.
        sys.exit(f"{args.name} is {vm['state']}; run `s3` once every VM runs")
    for index in range(len(vm['machines'])):
        subprocess.run([*ssh_command(cloud, args.name, index), 'umask 077 && mkdir -p ~/.aws && '
                        'cat > ~/.aws/credentials && printf "[default]\\nregion = us-east-1\\n" > ~/.aws/config'],
                       input=credentials, text=True, check=True, timeout=120)
    print(f"{args.name} can now read and write s3://{secret('DEV_TRAINING_S3_BUCKET')}")


def lifecycle(action):
    def run(args):
        cloud = located(args)
        getattr(cloud, action)(find(cloud, args.name))
        print(f'{action}: {args.name}')
    return run


def down(args):
    # Rerunnable: with the VM already gone it still removes the tailnet device.
    cloud, vm = locate(args)
    if vm:
        cloud.delete(vm)
        print(f'Deleted {args.name} and its boot disk')
        for machine in vm['machines'] if (state() / 'known_hosts').exists() else []:
            # A later VM may get the same address with a new host key.
            known = machine['address'] if machine['port'] == 22 else f"[{machine['address']}]:{machine['port']}"
            subprocess.run(['ssh-keygen', '-R', known, '-f', str(state() / 'known_hosts')],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    else:
        print(f'No VM named {args.name}; removing its tailnet device if one is left')
    names = [f'{name}-{args.name}' for name in ([cloud.name] if cloud else [args.provider] if args.provider
                                                 else PROVIDERS)]
    token = tailscale_token()
    for device in tailscale('GET', '/tailnet/-/devices', token).get('devices', []):
        hostname = device.get('hostname', '')
        # Also the --2, --3 ... machines of a split Ornn node.
        if TAG in device.get('tags', []) and any(re.fullmatch(re.escape(n) + r'(--\d+)?', hostname) for n in names):
            tailscale('DELETE', f"/device/{device['id']}", token)
            print(f"Removed tailnet device {device['name']}")


def positive(value):
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError('must be 1 or more')
    return int(value)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)

    def command(name, run, vm=False, many=False, aliases=()):
        sub = commands.add_parser(name, aliases=list(aliases))
        if many:
            sub.add_argument('--provider', type=provider_list, action='extend',
                             help=f"one or more of {', '.join(sorted(PROVIDERS))}; default: all")
        else:
            sub.add_argument('--provider', choices=sorted(PROVIDERS),
                             required=not vm and name != 'up', help='default: found from NAME or the platform')
        if vm:
            sub.add_argument('name')
        sub.set_defaults(run=run)
        return sub

    sub = command('search', search, many=True, aliases=['prices'])
    sub.add_argument('--term', choices=['spot', 'on-demand'], help='default: both')
    sub.add_argument('--gpu', help='substring of the GPU platform, for example h100 or b300')
    sub.add_argument('--region', help='substring of the region, for example us- or eu-north1')
    sub.add_argument('--min-gpus', type=int, default=1, help='GPUs per VM')
    sub.add_argument('--max-gpus', type=int, help='GPUs per VM')
    sub.add_argument('--max-price', type=float, help='USD per GPU-hour')
    sub.add_argument('--all', action='store_true', help='include offers that are sold out now')
    sub.add_argument('--json', action='store_true')
    command('platforms', platforms).add_argument('--region')
    sub = command('up', up, vm=True)
    sub.add_argument('--platform', required=True,
                     help='Nebius platform (gpu-h100-sxm) or Ornn GPU slug (nvidia_h100_sxm); see `search`')
    sub.add_argument('--preset', help='Nebius only, for example 1gpu-16vcpu-200gb; Ornn sells whole nodes')
    sub.add_argument('--region', help='Ornn default: the cheapest region')
    sub.add_argument('--term', choices=['spot', 'on-demand'], default='spot')
    sub.add_argument('--max-price', type=float,
                     help='refuse to create the VM above this USD per GPU-hour now; spot prices can move later')
    sub.add_argument('--disk-gib', type=int, help='Nebius boot disk, default 250; Ornn nodes have their own disk')
    sub.add_argument('--image', help='Nebius image family (default Ubuntu 24.04 with CUDA) or Ornn disk ID')
    command('ls', ls, many=True)
    sub = command('ssh', ssh, vm=True)
    sub.add_argument('--vm', type=positive, default=1, help='which VM of a node Ornn split into several (1, 2, ...)')
    sub.add_argument('command', nargs=argparse.REMAINDER)
    command('s3', s3, vm=True)
    for action in ('start', 'stop'):
        command(action, lifecycle(action), vm=True)
    command('down', down, vm=True)
    args = parser.parse_args()
    args.run(args)


if __name__ == '__main__':
    main()
