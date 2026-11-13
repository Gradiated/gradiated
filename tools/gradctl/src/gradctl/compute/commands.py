"""`gradctl compute`: run development training work on spot or on-demand GPU VMs from any supported provider.

  gradctl compute search [--provider P[,P]] [--gpu G] [--term T] [--region R] [--min-gpus N]
                         [--max-gpus N] [--max-price USD_PER_GPU_HOUR] [--all] [--json]
                                                         compute available now, cheapest per GPU-hour first
                                                         (alias: prices)
  gradctl compute platforms --provider P [--region R]    GPU platforms and presets
  gradctl compute up NAME --platform X [--preset Y] [--provider P] [--region R] [--term spot|on-demand]
                         [--max-price USD_PER_GPU_HOUR] [--disk-gib N]
  gradctl compute ls [--provider P[,P]]
  gradctl compute ssh [--vm N] NAME [command...]       N picks one of the VMs Ornn splits a node into
  gradctl compute s3 NAME                                give the VM the development bucket key
  gradctl compute start NAME | stop NAME                 preemption stops a VM, it is not deleted
  gradctl compute down NAME                              delete the VM, its disk and its tailnet device

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
`gradctl tailnet join` (ephemeral; userspace networking works).

Credentials come from gradiated/dev/env: from the environment (an ignored .env
loaded as AGENTS.md describes) or, if unset, read with the AWS profile in
AWS_PROFILE (default gradiated-readonly). VMs start with no credentials; `s3`
installs a key that can only use the development training bucket
(DEV_TRAINING_S3_BUCKET), so jobs on the VM can save checkpoints themselves.
These are spot VMs: save results to S3 regularly. A stopped VM still pays for
its disk.
"""

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from ..core import Meta, Result, UsageError, group, leaf
from ..devenv import secret
from .nebius import Nebius
from .ornn import Ornn

PROVIDERS = {'nebius': Nebius, 'ornn': Ornn}
TAILSCALE = 'https://api.tailscale.com/api/v2'
TAG = 'tag:dev-training'


def state():
    # Resolved on use, so a machine without a home directory can still run other commands.
    directory = Path.home() / '.config/gradiated/dev-training'
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    return directory


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
    sys.exit(f'Could not join {name} to the tailnet over SSH; run `gradctl compute down {name}` and try again')


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
    lines = list(cloud.platforms(args.region or cloud.default_region))
    return Result(data=lines, text='\n'.join(lines))


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
    for row in rows:
        # The exact command that creates this offer, for an agent to run.
        row['up_args'] = f"{row['up']} --term {row['term']}"
    lines = [f"{'$/GPU-hr':>8} {'$/hr':>8} {'GPUS':>4} {'TERM':9} {'PROVIDER':8} {'VIRT':10} {'AVAIL':>5} "
             f"{'GPU':18} {'REGION':12} UP"]
    for r in rows:
        available = '-' if r['available'] is None else str(r['available'])
        lines.append(f"{r['gpu_hour']:8.2f} {r['hour']:8.2f} {r['gpus']:4} {r['term']:9} {r['provider']:8} "
                     f"{r['virtualization']:10} {available:>5} {r['gpu']:18} {r['region']:12} {r['up_args']}")
    return Result(data=rows, text='\n'.join(lines))


def up(args):
    if not re.fullmatch('[a-z][a-z0-9-]{1,40}', args.name) or '--' in args.name or args.name.endswith('-'):
        raise UsageError('NAME must be lowercase letters, digits and single dashes')
    if not args.provider:
        owners = [name for name, cls in PROVIDERS.items() if re.match(cls.platform_pattern, args.platform)]
        if len(owners) != 1:
            raise UsageError(f'Cannot tell the provider of platform {args.platform}; pass --provider')
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
    print(f"Creating {args.term} {args.name} in {cloud.name} {region or ''}; waiting for it to run", file=sys.stderr)
    started = time.time()
    while time.time() < started + 1800:
        vm = cloud.find(args.name)
        if not vm and time.time() > started + 120:
            # Ornn ends a reservation whose VMs cannot start.
            sys.exit(f'{args.name} disappeared before it ran; check `gradctl compute ls` and the provider console')
        if vm and vm['state'] == 'RUNNING' and vm['address']:
            data = {'name': args.name, 'provider': cloud.name, 'region': vm['region'], 'term': args.term,
                    'address': vm['address'], 'tailnet_hosts': hosts(host, vm)}
            if cloud.cloud_init:
                return Result(data={**data, 'tailnet_joined': False},
                              text=f"{args.name} is running at {vm['address']}; it joins the tailnet as {host} "
                                   'a minute or two after boot')
            print(f"{args.name} is running at {vm['address']}; joining it to the tailnet", file=sys.stderr, flush=True)
            join_over_ssh(cloud, args.name, host, vm)
            return Result(data={**data, 'tailnet_joined': True},
                          text=f"{args.name} is running at {vm['address']} and joined the tailnet as "
                               f"{', '.join(hosts(host, vm))}")
        if vm and vm['state'] in ('ERROR', 'COMPLETED', 'CANCELLED'):
            sys.exit(f"{args.name} is {vm['state']}; check `gradctl compute ls` and run `gradctl compute down`")
        time.sleep(15)
    sys.exit(f'{args.name} did not start within 30 minutes; check `gradctl compute ls` and run '
             '`gradctl compute down`')


def ls(args):
    rows = []

    def collect(name, cloud):
        rows.extend({**vm, 'provider': name} for vm in cloud.list())
    each_provider(args.provider, collect)
    text = '\n'.join(f"{vm['name']:24} {vm['provider']:8} {vm['term']:9} {vm['region']:12} {vm['state']:10} "
                     f"{vm['shape']:36} {vm['address'] or '-'}" for vm in rows)
    return Result(data=rows, text=text or 'no VMs')


def ssh_command(cloud, name, index=0):
    vm = find(cloud, name)
    if index >= len(vm['machines']):
        sys.exit(f'{name} has no running VM {index + 1}; is it running? (`gradctl compute ls` shows how many '
                 'VMs it has)')
    machine = vm['machines'][index]
    key = state() / f'{cloud.name}-ssh-key'
    content = secret(f'{cloud.name.upper()}_SSH_PRIVATE_KEY_B64').strip() + '\n'
    if not key.exists() or key.read_text() != content:
        key.touch(mode=0o600)
        key.write_text(content)
    return ['ssh', '-i', str(key), '-p', str(machine['port']), '-o', 'IdentitiesOnly=yes',
            '-o', 'StrictHostKeyChecking=accept-new', '-o', f'UserKnownHostsFile={state() / "known_hosts"}',
            f"{machine['user']}@{machine['address']}"]


def ssh(args, as_json=False):
    command = [*args.command]
    if command[:1] == ['--json']:
        raise UsageError('put --json before NAME; everything after NAME runs on the VM',
                         hint='gradctl --json compute ssh NAME -- nvidia-smi')
    if command[:1] == ['--']:
        command = command[1:]
    if as_json and not command:
        raise UsageError('--json needs a command to run; an interactive shell has no JSON result',
                         hint='gradctl --json compute ssh NAME -- nvidia-smi')
    ssh_args = ssh_command(located(args), args.name, args.vm - 1)
    if not as_json:
        os.execvp('ssh', [*ssh_args, *command])
    # Options go before the destination, the last element; after it they would be the remote command.
    result = subprocess.run([*ssh_args[:-1], '-o', 'BatchMode=yes', ssh_args[-1], *command],
                            capture_output=True, text=True)
    return Result(data={'exit_code': result.returncode, 'stdout': result.stdout, 'stderr': result.stderr},
                  ok=result.returncode == 0, exit_code=0 if result.returncode == 0 else 1,
                  error=f'the remote command exited with status {result.returncode}', error_code='remote_failed')


def s3(args):
    """Install the bucket-only key as the VM user's default AWS profile, over stdin."""
    credentials = '\n'.join(['[default]', f"aws_access_key_id = {secret('DEV_TRAINING_AWS_ACCESS_KEY_ID')}",
                             f"aws_secret_access_key = {secret('DEV_TRAINING_AWS_SECRET_ACCESS_KEY')}", ''])
    cloud = located(args)
    vm = find(cloud, args.name)
    if vm['state'] != 'RUNNING':
        # A split Ornn node lists only its running VMs; configure them all at once.
        sys.exit(f"{args.name} is {vm['state']}; run `gradctl compute s3` once every VM runs")
    for index in range(len(vm['machines'])):
        subprocess.run([*ssh_command(cloud, args.name, index), 'umask 077 && mkdir -p ~/.aws && '
                        'cat > ~/.aws/credentials && printf "[default]\\nregion = us-east-1\\n" > ~/.aws/config'],
                       input=credentials, text=True, check=True, timeout=120, stdout=sys.stderr)
    bucket = secret('DEV_TRAINING_S3_BUCKET')
    return Result(data={'name': args.name, 'bucket': bucket, 'machines': len(vm['machines'])},
                  text=f'{args.name} can now read and write s3://{bucket}')


def lifecycle(action):
    def run(args):
        cloud = located(args)
        getattr(cloud, action)(find(cloud, args.name))
        return Result(data={'action': action, 'name': args.name, 'provider': cloud.name},
                      text=f'{action}: {args.name}')
    return run


def down(args):
    # Rerunnable: with the VM already gone it still removes the tailnet device.
    cloud, vm = locate(args)
    lines, removed = [], []
    if vm:
        cloud.delete(vm)
        lines.append(f'Deleted {args.name} and its boot disk')
        print(lines[-1], file=sys.stderr, flush=True)
        for machine in vm['machines'] if (state() / 'known_hosts').exists() else []:
            # A later VM may get the same address with a new host key.
            known = machine['address'] if machine['port'] == 22 else f"[{machine['address']}]:{machine['port']}"
            subprocess.run(['ssh-keygen', '-R', known, '-f', str(state() / 'known_hosts')],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    else:
        lines.append(f'No VM named {args.name}; removing its tailnet device if one is left')
    names = [f'{name}-{args.name}' for name in ([cloud.name] if cloud else [args.provider] if args.provider
                                                 else PROVIDERS)]
    token = tailscale_token()
    for device in tailscale('GET', '/tailnet/-/devices', token).get('devices', []):
        hostname = device.get('hostname', '')
        # Also the --2, --3 ... machines of a split Ornn node.
        if TAG in device.get('tags', []) and any(re.fullmatch(re.escape(n) + r'(--\d+)?', hostname) for n in names):
            tailscale('DELETE', f"/device/{device['id']}", token)
            removed.append(device['name'])
            lines.append(f"Removed tailnet device {device['name']}")
            print(lines[-1], file=sys.stderr, flush=True)
    return Result(data={'name': args.name, 'deleted_vm': bool(vm), 'provider': cloud.name if cloud else None,
                        'removed_tailnet_devices': removed}, text='\n'.join(lines))


def setup(args):
    from . import setup as setup_module
    setup_module.run(args)
    return Result(data={'provider': args.target}, text=f'{args.target} credentials written to gradiated/dev/env')


def positive(value):
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError('must be 1 or more')
    return int(value)


def register(commands, common) -> None:
    sub = group(commands, 'compute', 'Development training GPU VMs from Nebius or Ornn, isolated on the tailnet '
                                     '(see $dev-training)')
    creds = ('aws',)

    def command(name, run, meta, vm=False, many=False, aliases=()):
        parser = leaf(sub, name, lambda ctx: run(ctx.args), meta, common, aliases=list(aliases))
        if many:
            parser.add_argument('--provider', type=provider_list, action='extend',
                                help=f"one or more of {', '.join(sorted(PROVIDERS))}; default: all")
        else:
            parser.add_argument('--provider', choices=sorted(PROVIDERS),
                                required=not vm and name != 'up', help='default: found from NAME or the platform')
        if vm:
            parser.add_argument('name')
        return parser

    parser = command('search', search, Meta('Compute available now across providers, cheapest per GPU-hour first, '
                                            'with the arguments for `up`', requires=creds),
                     many=True, aliases=['prices'])
    parser.add_argument('--term', choices=['spot', 'on-demand'], help='default: both')
    parser.add_argument('--gpu', help='substring of the GPU platform, for example h100 or b300')
    parser.add_argument('--region', help='substring of the region, for example us- or eu-north1')
    parser.add_argument('--min-gpus', type=int, default=1, help='GPUs per VM')
    parser.add_argument('--max-gpus', type=int, help='GPUs per VM')
    parser.add_argument('--max-price', type=float, help='USD per GPU-hour')
    parser.add_argument('--all', action='store_true', help='include offers that are sold out now')
    command('platforms', platforms, Meta('GPU platforms and presets of one provider', requires=creds)) \
        .add_argument('--region')
    parser = command('up', up, Meta('Create a VM, wait for it to run and join it to the tailnet; spends money',
                                    effects='write', requires=creds), vm=True)
    parser.add_argument('--platform', required=True,
                        help='Nebius platform (gpu-h100-sxm) or Ornn GPU slug (nvidia_h100_sxm); see `search`')
    parser.add_argument('--preset', help='Nebius only, for example 1gpu-16vcpu-200gb; Ornn sells whole nodes')
    parser.add_argument('--region', help='Ornn default: the cheapest region')
    parser.add_argument('--term', choices=['spot', 'on-demand'], default='spot')
    parser.add_argument('--max-price', type=float,
                        help='refuse to create the VM above this USD per GPU-hour now; spot prices can move later')
    parser.add_argument('--disk-gib', type=int, help='Nebius boot disk, default 250; Ornn nodes have their own disk')
    parser.add_argument('--image', help='Nebius image family (default Ubuntu 24.04 with CUDA) or Ornn disk ID')
    command('ls', ls, Meta('Every dev-training VM on every provider', requires=creds), many=True)
    parser = leaf(sub, 'ssh', lambda ctx: ssh(ctx.args, ctx.json), Meta(
        'Run a command on a VM over SSH (or open a shell without --json)', effects='write', requires=creds,
        interactive=True), common)
    parser.add_argument('--provider', choices=sorted(PROVIDERS), help='default: found from NAME')
    parser.add_argument('--vm', type=positive, default=1, help='which VM of a node Ornn split into several (1, 2, ...)')
    parser.add_argument('name')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run; put it after --')
    command('s3', s3, Meta('Give the VM the key that can use only the development training bucket',
                           effects='write', requires=creds), vm=True)
    command('start', lifecycle('start'), Meta('Start a stopped (preempted) VM', effects='write', requires=creds),
            vm=True)
    command('stop', lifecycle('stop'), Meta('Stop a VM; its disk is kept and still billed', effects='write',
                                            requires=creds), vm=True)
    command('down', down, Meta('Delete a VM, its disk and its tailnet device; rerunnable', effects='destructive',
                               requires=creds), vm=True)
    parser = leaf(sub, 'setup', lambda ctx: setup(ctx.args), Meta(
        'Admin: write or rotate the provider and Tailscale credentials in gradiated/dev/env', effects='write',
        requires=('aws', 'nebius')), common)
    parser.add_argument('target', nargs='?', choices=['nebius', 'ornn', 'tailscale'], default='nebius',
                        help='ornn reads a new API key on stdin; tailscale copies only the Tailscale clients')
    parser.add_argument('--aws-profile', default='gradiated-admin')
    parser.add_argument('--rotate-ssh-key', action='store_true',
                        help='replace the SSH key; existing VMs keep trusting only the old one')
