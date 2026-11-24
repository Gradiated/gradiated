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
  gradctl compute s3 NAME --path P [--read P] [--hours H]
                                                         give the VM expiring credentials for those
                                                         bucket paths only
  gradctl compute start NAME | stop NAME                 preemption stops a VM, it is not deleted
  gradctl compute down NAME                              delete the VM, its disk and its tailnet device
  gradctl compute meter [--provider P[,P]]               send each VM's cost since it was last metered to PostHog
  gradctl compute record-usage --provider P --gpu-type G --gpu-count N --usd-per-gpu-hour X --hours H ...
                                                         send GPU time this command does not manage (our fleet)

Cost events: `up` takes --customer, --stage, --run-id and --workstream and records
them locally; `meter` (run it every 15 to 60 minutes while VMs are up) and `down`
send `compute_usage` events with those tags, the GPU type and count, and the
price, to the FDE PostHog project (see gradctl/usage.py for the schema). A VM
created on another machine is metered from its creation time as unattributed.

Providers: nebius, ornn and spheron, all virtual machines (some Spheron offers are
bare metal). --provider picks one or more
(repeat it or separate with commas); without it, search and ls cover every
provider, commands that take NAME find the VM on whichever provider has it, and
up takes the provider from the platform's name. `search` lists what each sells
with what is available now and the arguments for `up`. Spot VMs can be taken back at any time;
on-demand VMs cost more and run until stopped (Ornn's also end when the seller's
listing ends). Spheron resells several clouds; `search` shows the seller in REGION,
and bills at least 20 minutes of each VM.

A VM joins the tailnet as <provider>-<NAME> with tag:dev-training and
tag:dev-training-<provider>. It can reach other VMs from the same provider, for
multi-node training, and nothing else on the tailnet: not production, EKS, people's
devices, or another provider's VMs. tag:dev-machine devices and administrators can reach it, including
with `tailscale ssh root@<provider>-<NAME>`. A machine that is not on the tailnet
joins as tag:dev-machine with
`gradctl tailnet join` (ephemeral; userspace networking works).

Credentials come from gradiated/dev/env: from the environment (an ignored .env
loaded as AGENTS.md describes) or, if unset, read with the AWS profile in
AWS_PROFILE (default gradiated-readonly). VMs start with no credentials. `s3`
installs temporary credentials, minted from the bucket user's key, that reach
only the paths it is given in the development training bucket
(DEV_TRAINING_S3_BUCKET) and expire after --hours (default 24), so jobs on the
VM can save checkpoints themselves. The bucket user's own key never leaves the
machine that runs gradctl.
These are spot VMs: save results to S3 regularly. A stopped VM still pays for
its disk.
"""

import argparse
import json
import math
import os
import re
import shlex
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from ..core import Meta, Result, UsageError, group, leaf
from .. import usage
from ..devenv import secret
from .nebius import Nebius
from .ornn import Ornn
from .spheron import Spheron
from .sfcompute import SFCompute

PROVIDERS = {'nebius': Nebius, 'ornn': Ornn, 'spheron': Spheron, 'sfcompute': SFCompute}
# Temporarily omit Ornn from aggregate results; retain explicit access for existing VMs.
DISABLED_PROVIDERS = {'ornn'}
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
    """Run for chosen providers or enabled defaults, skipping failures only for defaults."""
    for name in sorted(set(only)) if only else sorted(PROVIDERS.keys() - DISABLED_PROVIDERS):
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
    public_key = secret(f"{getattr(cloud, 'secret_prefix', cloud.name.upper())}_SSH_PUBLIC_KEY_B64").strip()
    return '\n'.join([
        '#cloud-config',
        # SF Compute public images use root SSH; cloud-init otherwise disables it.
        *(['disable_root: false'] if cloud.ssh_user == 'root' else []),
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
        # An offer may name its own virtualization, such as a Spheron bare-metal server.
        rows.extend({'virtualization': cloud.virtualization, **offer, 'provider': name}
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


def hourly_price(cloud, vm, cache):
    """USD per hour for the whole VM, and where the price came from."""
    if vm.get('usd_per_gpu_hour') is not None and vm.get('gpus'):
        return vm['usd_per_gpu_hour'] * vm['gpus'], f'{cloud.name}_reservation'
    if hasattr(cloud, 'hourly_price') and vm.get('preset'):
        key = (vm['region'], vm['gpu_type'], vm['preset'], vm['term'])
        if key not in cache:
            try:
                cache[key] = cloud.hourly_price(*key)
            except (SystemExit, Exception) as error:
                print(f"no price for {vm['name']}: {error}", file=sys.stderr)
                cache[key] = None
        return cache[key], f'{cloud.name}_current_price'
    return None, 'unknown'


def ledger_key(cloud, vm, book):
    """The VM's ledger key, by its stable resource ID; an entry `up` recorded under the name moves to the ID."""
    key = f"{cloud.name}:{vm.get('id') or vm['name']}"
    named = f"{cloud.name}:{vm['name']}"
    if key not in book and named in book and named != key:
        book[key] = book.pop(named)
    return key


def meter_vms(cloud, vms, end, source):
    """Send one compute_usage event per VM for the time since it was last metered; returns the events sent.

    Each event is built once and kept in the ledger as pending until PostHog accepts it, so a retry resends the
    identical event (same uuid and timestamp) and PostHog drops the duplicate. An interval is billed by the state
    the VM was last seen in, since the time of a change between meters is not known. A billed interval without a
    price is not sent: it stays open until a price is available.
    """
    pending, cache = {}, {}
    with usage.ledger(state()) as book:
        for vm in vms:
            key = ledger_key(cloud, vm, book)
            tags = book.setdefault(key, {})
            tags.setdefault('resource_name', vm['name'])
            if tags.get('pending'):
                pending[key] = tags['pending']
                continue
            start = (usage.parse_time(tags.get('metered_until')) or usage.parse_time(tags.get('started_at'))
                     or usage.parse_time(vm.get('created_at')) or end)
            # A provider that bills only from a point after creation (Spheron's startedAt) sets
            # billing_started_at; the time before it cost nothing and is not sent.
            billed_from = usage.parse_time(vm.get('billing_started_at'))
            began_billing = bool(billed_from and start < billed_from <= end)
            if began_billing:
                start = billed_from
            billed_until = usage.parse_time(vm.get('billing_ended_at'))
            interval_end = min(end, billed_until) if billed_until else end
            if (interval_end - start).total_seconds() < 1:
                continue
            # From the billing start on, the VM is no longer in the unbilled state an earlier meter saw.
            interval_state = vm.get('state') if began_billing else tags.get('last_state') or vm.get('state')
            if billed_until:
                # A known terminal boundary establishes that the preceding interval was billed,
                # including the first observation of an already-expired SF allocation.
                interval_state = 'RUNNING'
            if hasattr(cloud, 'usage_price'):
                price, price_source = cloud.usage_price(vm, start, interval_end), f'{cloud.name}_fills'
            else:
                price, price_source = hourly_price(cloud, vm, cache)
            if price is None and interval_state in usage.BILLED_STATES:
                print(f"no price for {vm['name']}; its time since {start.isoformat()} is kept for the next meter",
                      file=sys.stderr)
                continue
            event = usage.event(
                customer=tags.get('customer'), stage=tags.get('stage'), run_id=tags.get('run_id'),
                workstream=tags.get('workstream'), provider=cloud.name, resource_name=vm['name'],
                resource_id=vm.get('id'), region=vm.get('region'), term=vm.get('term'), gpu_type=vm.get('gpu_type'),
                gpu_count=vm.get('gpus'), usd_per_hour=price, price_source=price_source, start=start, end=interval_end,
                vm_state=interval_state, source=source)
            tags['pending'] = event
            tags['next_state'] = vm.get('state')
            pending[key] = event
    if not pending:
        return []
    usage.send(list(pending.values()))
    settle(pending)
    return list(pending.values())


def settle(sent):
    """Advance the ledger past events PostHog accepted, and drop entries of deleted VMs with nothing left to send."""
    with usage.ledger(state()) as book:
        for key, event in sent.items():
            tags = book.get(key)
            if not tags or tags.get('pending', {}).get('uuid') != event['uuid']:
                continue
            tags['metered_until'] = event['properties']['interval_end']
            tags['last_state'] = tags.pop('next_state', None) or tags.get('last_state')
            tags.pop('pending')
            if tags.get('deleted'):
                book.pop(key)


def close_ended(cloud, seen, end, source, only=None):
    """Send the final interval of VMs this machine tracked that the provider has since ended, then forget them.

    A provider such as Spheron drops a reclaimed spot VM from its live list, so neither `meter` nor `down`
    would see it again. `seen` holds the ledger keys of VMs still listed; `only` limits this to one VM name.
    """
    if not hasattr(cloud, 'ended'):
        return []
    prefix = f'{cloud.name}:'
    with usage.ledger(state()) as book:
        tracked = [(key[len(prefix):], tags.get('started_at')) for key, tags in book.items()
                   if key.startswith(prefix) and key not in seen and not tags.get('pending')
                   and (only is None or only in (key[len(prefix):], tags.get('resource_name')))]
    sent = []
    for key, vm in cloud.ended(tracked) if tracked else []:
        with usage.ledger(state()) as book:
            if prefix + key in book:
                book[prefix + key]['deleted'] = True  # dropped once its final interval is accepted
        # It ran until it ended: bill its last interval as running unless an earlier meter saw it otherwise.
        final = {**vm, 'state': 'RUNNING'} if vm.get('billing_started_at') else vm
        sent.extend(meter_vms(cloud, [final], min(end, usage.parse_time(vm.get('ended_at')) or end), source))
        with usage.ledger(state()) as book:
            for gone in (prefix + key, prefix + str(vm.get('id'))):
                if gone in book and not book[gone].get('pending'):
                    book.pop(gone)
    return sent


def flush_pending(skip=()):
    """Send pending events of VMs no longer listed, such as one whose final send failed during `down`."""
    with usage.ledger(state()) as book:
        pending = {k: t['pending'] for k, t in book.items() if t.get('pending') and k not in skip}
    if pending:
        usage.send(list(pending.values()))
        settle(pending)
    return list(pending.values())


def meter(args):
    end, found = usage.now(), []

    def collect(name, cloud):
        found.append((cloud, list(cloud.list())))
    # A provider that cannot be reached is skipped; a failure to deliver events fails the command.
    each_provider(args.provider, collect)
    sent, keys = [], set()
    for cloud, vms in found:
        sent.extend(meter_vms(cloud, vms, end, 'gradctl compute meter'))
        listed = {f"{cloud.name}:{vm.get('id') or vm['name']}" for vm in vms}
        keys |= listed
        try:
            sent.extend(close_ended(cloud, listed, end, 'gradctl compute meter'))
        except (SystemExit, Exception) as error:  # noqa: BLE001 - the next meter retries it
            print(f'could not close ended {cloud.name} VMs: {error}', file=sys.stderr)
    sent.extend(flush_pending(skip=keys))
    cost = sum(e['properties']['cost_usd'] for e in sent)
    rows = [{k: e['properties'][k] for k in ('provider', 'resource_name', 'customer', 'stage', 'gpu_type',
                                              'gpu_count', 'duration_seconds', 'cost_usd')} for e in sent]
    text = '\n'.join(f"{r['resource_name']:24} {r['provider']:8} {r['customer']:14} {r['stage'] or '-':10} "
                     f"{r['gpu_count'] or '-'}x{r['gpu_type']} {r['duration_seconds'] / 3600:6.2f}h "
                     f"${r['cost_usd']:.2f}" for r in rows)
    return Result(data={'events': len(sent), 'cost_usd': round(cost, 4), 'vms': rows},
                  text=(text + '\n' if text else '') + f'Sent {len(sent)} compute_usage events, ${cost:.2f}')


def record_usage(args):
    end = usage.parse_time(args.end) if args.end else usage.now()
    if args.start:
        start = usage.parse_time(args.start)
    elif args.hours is not None:
        start = datetime.fromtimestamp(end.timestamp() - args.hours * 3600, timezone.utc)
    else:
        raise UsageError('pass --hours or --start')
    if not start or not end or end <= start:
        raise UsageError('the interval must end after it starts')
    sent = usage.event(customer=args.customer, stage=args.stage, run_id=args.run_id, workstream=args.workstream,
                       provider=args.provider, resource_name=args.resource, resource_id=args.resource,
                       region=args.region, term=args.term, gpu_type=args.gpu_type, gpu_count=args.gpu_count,
                       usd_per_hour=args.usd_per_gpu_hour * args.gpu_count, price_source='recorded', start=start,
                       end=end, vm_state='RUNNING', source='gradctl compute record-usage')
    usage.send([sent])
    return Result(data=sent['properties'], text=f"Sent {sent['properties']['gpu_hours']:.2f} GPU-hours, "
                                                f"${sent['properties']['cost_usd']:.2f}, for {args.customer}")


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
    if args.duration_hours is not None:
        if cloud.name != 'sfcompute':
            raise UsageError('--duration-hours is supported only by SF Compute')
        cloud.duration_hours = args.duration_hours
    pricing = {}
    if args.spot_price_multiple is not None:
        if cloud.name != 'nebius' or args.term != 'spot':
            raise UsageError('--spot-price-multiple requires Nebius spot')
        if not math.isfinite(args.spot_price_multiple) or args.spot_price_multiple <= 0:
            raise UsageError('--spot-price-multiple must be finite and positive')
        pricing['spot_price_multiple'] = args.spot_price_multiple
    cloud.create(args.name, region, args.platform, args.preset, args.disk_gib, args.image,
                 lambda: cloud_init(cloud, host), term=args.term, max_price=args.max_price, **pricing)
    with usage.ledger(state()) as book:
        book[f'{cloud.name}:{args.name}'] = {'customer': args.customer, 'stage': args.stage, 'run_id': args.run_id,
                                             'workstream': args.workstream, 'started_at': usage.now().isoformat()}
    print(f"Creating {args.term} {args.name} in {cloud.name} {region or ''}; waiting for it to run", file=sys.stderr)
    started = time.time()
    while time.time() < started + 1800:
        vm = cloud.find(args.name)
        if not vm and time.time() > started + 120:
            # Ornn ends a reservation whose VMs cannot start; Spheron fails a deployment that cannot.
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


def extend(args):
    if not math.isfinite(args.hours) or args.hours <= 0:
        raise UsageError('--hours must be finite and positive')
    if not math.isfinite(args.max_price) or args.max_price <= 0:
        raise UsageError('--max-price must be finite and positive (USD per GPU-hour)')
    cloud, vm = locate(args)
    if not vm:
        raise UsageError(f'No VM named {args.name}')
    if not hasattr(cloud, 'extend'):
        raise UsageError(f"{cloud.name}: {cloud.extension_note}")
    data = cloud.extend(vm, args.hours, args.max_price)
    return Result(data={'name': vm['name'], 'provider': cloud.name, **data},
                  text=f"Extended {vm['name']} by {data['hours']:g} hours through "
                       f"{datetime.fromtimestamp(data['end_at'], timezone.utc).isoformat()} "
                       f"(order {data['order_id']})")


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
    content = secret(f"{getattr(cloud, 'secret_prefix', cloud.name.upper())}_SSH_PRIVATE_KEY_B64").strip() + '\n'
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


BUCKET_PATH = re.compile(r'[A-Za-z0-9][A-Za-z0-9._=-]*(/[A-Za-z0-9][A-Za-z0-9._=-]*)*')
WRITE_ACTIONS = ['s3:PutObject', 's3:DeleteObject', 's3:AbortMultipartUpload', 's3:ListMultipartUploadParts']


# The VM reads its token through credential_process, which AWS SDKs call again as the token nears its
# Expiration, so a running job picks up a renewed token without restarting. A static ~/.aws/credentials
# file, which SDKs load once and which outranks credential_process, is removed. The file is replaced
# atomically so a refresh never reads half of it.
VM_CREDENTIALS = ' && '.join([
    'umask 077', 'mkdir -p ~/.aws', 'cat > ~/.aws/dev-training-token.json.new',
    'mv ~/.aws/dev-training-token.json.new ~/.aws/dev-training-token.json', 'rm -f ~/.aws/credentials',
    'printf "[default]\\nregion = us-east-1\\ncredential_process = cat %s/.aws/dev-training-token.json\\n" '
    '"$HOME" > ~/.aws/config',
])


def bucket_path(value):
    """A key prefix in the development bucket, such as bildy/run-7: no wildcards, '..' or leading '/'."""
    path = value.strip().rstrip('/')
    if not BUCKET_PATH.fullmatch(path) or any(part in ('.', '..') for part in path.split('/')):
        raise argparse.ArgumentTypeError('a path such as <project>/<run>: letters, digits, . _ = - and /, '
                                         'with no wildcards, .. or leading /')
    return path


def bucket_policy(bucket, writes, reads):
    """A session policy that allows only these paths: list and read every path, write only `writes`.

    Listing is limited to `<path>/` and below, not the bare prefix, which would also list `<path>-other/`.
    """
    arn = f'arn:aws:s3:::{bucket}'
    every = sorted(set(writes) | set(reads))
    statements = [
        {'Sid': 'Locate', 'Effect': 'Allow', 'Action': 's3:GetBucketLocation', 'Resource': arn},
        {'Sid': 'List', 'Effect': 'Allow', 'Action': ['s3:ListBucket', 's3:ListBucketVersions'], 'Resource': arn,
         'Condition': {'StringLike': {'s3:prefix': [f'{p}/{suffix}' for p in every for suffix in ('', '*')]}}},
        {'Sid': 'Read', 'Effect': 'Allow', 'Action': ['s3:GetObject', 's3:GetObjectVersion'],
         'Resource': [f'{arn}/{p}/*' for p in every]},
    ]
    if writes:
        statements.append({'Sid': 'Write', 'Effect': 'Allow', 'Action': WRITE_ACTIONS,
                           'Resource': [f'{arn}/{p}/*' for p in sorted(set(writes))]})
    return {'Version': '2012-10-17', 'Statement': statements}


def bucket_credentials(name, bucket, writes, reads, hours):
    """Temporary credentials, from the bucket user's key, that expire after `hours` and reach only these paths.

    GetFederationToken grants the overlap of the bucket user's own policy and the session policy, so the
    result can never exceed the bucket, and a federated user cannot mint further credentials.
    """
    policy = json.dumps(bucket_policy(bucket, writes, reads), separators=(',', ':'))
    if len(policy) > 2048:
        sys.exit(f'{len(writes) + len(reads)} paths make a policy over the 2048 characters AWS allows; '
                 'name fewer, or a common parent path')
    environment = {k: v for k, v in os.environ.items()
                   if not k.startswith('AWS_') or k in ('AWS_CA_BUNDLE',)}
    environment.update({'AWS_ACCESS_KEY_ID': secret('DEV_TRAINING_AWS_ACCESS_KEY_ID'),
                        'AWS_SECRET_ACCESS_KEY': secret('DEV_TRAINING_AWS_SECRET_ACCESS_KEY'),
                        'AWS_DEFAULT_REGION': 'us-east-1'})
    # Federated user names are at most 32 characters; the bucket user may mint only dt-* names.
    result = subprocess.run(['aws', 'sts', 'get-federation-token', '--name', f'dt-{name}'[:32],
                             '--duration-seconds', str(int(hours * 3600)),
                             '--policy', policy,
                             '--output', 'json'],
                            env=environment, text=True, capture_output=True, timeout=60)
    if result.returncode:
        sys.exit(f'Could not mint bucket credentials: {result.stderr.strip()[:500]}')
    return json.loads(result.stdout)['Credentials']


def s3(args):
    """Install credentials that reach only the chosen paths and expire, as the VM user's default AWS profile."""
    if not args.path and not args.read:
        raise UsageError('name the bucket paths the VM may use with --path (read and write) or --read',
                         hint='gradctl compute s3 NAME --path <project>/<run>; pick a new path for a new run')
    writes, reads = sorted(set(args.path or [])), sorted(set(args.read or []))
    for read in reads:
        # A writable parent would make a read-only path writable after all.
        parent = next((w for w in writes if read == w or read.startswith(w + '/')), None)
        if parent:
            raise UsageError(f'--read {read} is inside the writable --path {parent}, so it would not be read-only',
                             hint='make the writable path a sibling, such as <project>/<new-run>')
    if not 0.25 <= args.hours <= 36:
        raise UsageError('--hours must be from 0.25 to 36, the range AWS allows for these credentials')
    cloud = located(args)
    vm = find(cloud, args.name)
    if vm['state'] != 'RUNNING':
        # A split Ornn node lists only its running VMs; configure them all at once.
        sys.exit(f"{args.name} is {vm['state']}; run `gradctl compute s3` once every VM runs")
    bucket = secret('DEV_TRAINING_S3_BUCKET')
    issued = bucket_credentials(args.name, bucket, writes, reads, args.hours)
    credentials = json.dumps({'Version': 1, 'AccessKeyId': issued['AccessKeyId'],
                              'SecretAccessKey': issued['SecretAccessKey'], 'SessionToken': issued['SessionToken'],
                              'Expiration': issued['Expiration']})
    for index in range(len(vm['machines'])):
        subprocess.run([*ssh_command(cloud, args.name, index), VM_CREDENTIALS], input=credentials, text=True,
                       check=True, timeout=120, stdout=sys.stderr)
    expires = issued['Expiration']
    lines = [f'{args.name} can use these paths of s3://{bucket} until {expires}:']
    lines += [f'  read and write  s3://{bucket}/{p}/' for p in writes]
    lines += [f'  read only       s3://{bucket}/{p}/' for p in reads]
    lines.append('Run `gradctl compute s3` again before then to renew them; running jobs pick up the renewal.')
    return Result(data={'name': args.name, 'bucket': bucket, 'machines': len(vm['machines']), 'write_paths': writes,
                        'read_paths': reads, 'expires_at': expires}, text='\n'.join(lines))


def lifecycle(action):
    def run(args):
        cloud = located(args)
        vm = find(cloud, args.name)
        try:
            # Close the interval at the state change, so the time before it is billed by the state it had.
            meter_vms(cloud, [vm], usage.now(), f'gradctl compute {action}')
        except Exception as error:  # noqa: BLE001 - cost reporting must never block starting or stopping a VM
            print(f'could not send the cost event for {args.name}: {error}', file=sys.stderr)
        getattr(cloud, action)(vm)
        return Result(data={'action': action, 'name': args.name, 'provider': cloud.name},
                      text=f'{action}: {args.name}')
    return run


def down(args):
    # Rerunnable: with the VM already gone it still removes the tailnet device.
    cloud, vm = locate(args)
    lines, removed, keep_ledger = [], [], False
    if vm:
        if hasattr(cloud, 'wait_until_deletable'):
            # Spheron bills a minimum runtime and refuses to delete before it; wait first, so the final
            # meter below counts that time, with the VM as it is after the wait (it may have started running).
            fresh = cloud.wait_until_deletable(vm)
        else:
            fresh = vm
        try:
            if fresh:
                meter_vms(cloud, [fresh], usage.now(), 'gradctl compute down')
            else:
                # The provider ended it during the wait, such as a spot reclaim: close it by its end time.
                close_ended(cloud, set(), usage.now(), 'gradctl compute down', only=args.name)
        except (SystemExit, Exception) as error:  # noqa: BLE001 - cost reporting must never block deleting a VM
            print(f'could not send the final cost event for {args.name}: {error}', file=sys.stderr)
            # An ended VM that could not be closed keeps its ledger entry, so the next `meter` closes it.
            keep_ledger = not fresh
        vm = fresh or vm
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
        # A VM the provider ended itself, such as a reclaimed Spheron spot VM, still owes its final interval.
        for name in [cloud.name] if cloud else [args.provider] if args.provider else sorted(PROVIDERS):
            try:
                close_ended(provider(name), set(), usage.now(), 'gradctl compute down', only=args.name)
            except (SystemExit, Exception) as error:  # noqa: BLE001 - cost reporting must never block down
                print(f'could not send the final cost event for {args.name} on {name}: {error}', file=sys.stderr)
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
    if cloud and vm and not keep_ledger:
        with usage.ledger(state()) as book:
            key = ledger_key(cloud, vm, book)
            if book.get(key, {}).get('pending'):
                book[key]['deleted'] = True  # the next `meter` sends the final interval, then drops the entry
            else:
                book.pop(key, None)
    return Result(data={'name': args.name, 'deleted_vm': bool(vm), 'provider': cloud.name if cloud else None,
                        'removed_tailnet_devices': removed}, text='\n'.join(lines))


def setup(args):
    from . import setup as setup_module
    setup_module.run(args)
    return Result(data={'provider': args.target}, text=f'{args.target} credentials written to gradiated/dev/env')


def attribution(parser):
    parser.add_argument('--customer', default='gradiated',
                        help='who the work is for, as in OpenRouter `user` (bild-ai); default gradiated (internal)')
    parser.add_argument('--stage', default='dev',
                        help='cleaning, env-build, training, rollout, eval, serving or dev (default)')
    parser.add_argument('--run-id', help='the run or experiment this time belongs to')
    parser.add_argument('--workstream', help='for example bildy')


def positive(value):
    if not value.isdigit() or int(value) < 1:
        raise argparse.ArgumentTypeError('must be 1 or more')
    return int(value)


def register(commands, common) -> None:
    sub = group(commands, 'compute', 'Development training GPU VMs from Nebius, Ornn, Spheron or SF Compute, isolated on '
                                     'the tailnet (see $dev-training)')
    creds = ('aws',)

    def command(name, run, meta, vm=False, many=False, aliases=()):
        parser = leaf(sub, name, lambda ctx: run(ctx.args), meta, common, aliases=list(aliases))
        if many:
            parser.add_argument('--provider', type=provider_list, action='extend',
                                help=f"one or more of {', '.join(sorted(PROVIDERS))}; "
                                     f"default: {', '.join(sorted(PROVIDERS.keys() - DISABLED_PROVIDERS))}")
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
                        help='Nebius platform (gpu-h100-sxm), Ornn GPU slug (nvidia_h100_sxm) or Spheron GPU '
                             'type (H100_SXM5), or SF Compute SKU (sku_...); see `search`')
    parser.add_argument('--preset', help='Nebius preset (1gpu-16vcpu-200gb) or Spheron offer ID; Ornn sells whole '
                                         'nodes')
    parser.add_argument('--region', help='Ornn and Spheron default: the cheapest region')
    parser.add_argument('--term', choices=['spot', 'on-demand'], default='spot')
    parser.add_argument('--max-price', type=float,
                        help='refuse to create the VM above this USD per GPU-hour now; spot prices can move later')
    parser.add_argument('--spot-price-multiple', type=float,
                        help='Nebius spot: attach a provider-enforced ceiling at this multiple of the live GPU price')
    parser.add_argument('--disk-gib', type=int, help='Nebius boot disk, default 250; Ornn nodes have their own disk')
    parser.add_argument('--image', help='Nebius image family (default Ubuntu 24.04 with CUDA), Ornn disk ID or '
                                        "one of the Spheron offer's os_options (default Ubuntu with CUDA)")
    parser.add_argument('--duration-hours', type=float,
                        help='SF Compute: prepaid window upper bound (default 1 hour), ends on the last '
                             'provider schedule boundary within this duration; down does not refund unused time')
    attribution(parser)
    parser = command('extend', extend, Meta(
        'Extend a running reservation without replacing its VM; spends money where supported',
        effects='write', requires=creds), vm=True)
    parser.add_argument('--hours', '--duration-hours', dest='hours', required=True, type=float,
                        help='additional prepaid hours, ending on a provider schedule boundary within this duration')
    parser.add_argument('--max-price', type=float, required=True, help='maximum USD per GPU-hour for the extension')
    command('ls', ls, Meta('Every dev-training VM on every provider', requires=creds), many=True)
    command('meter', meter, Meta("Send each VM's GPU cost since it was last metered to PostHog as compute_usage "
                                 'events', effects='write', requires=creds), many=True)
    parser = leaf(sub, 'record-usage', lambda ctx: record_usage(ctx.args), Meta(
        'Send a compute_usage event for GPU time gradctl does not manage, such as our own serving fleet',
        effects='write'), common)
    parser.add_argument('--provider', required=True, help='for example fleet, runpod or nebius')
    parser.add_argument('--resource', required=True, help='host, node or pool name')
    parser.add_argument('--gpu-type', required=True, help='for example nvidia_b300')
    parser.add_argument('--gpu-count', type=positive, required=True)
    parser.add_argument('--usd-per-gpu-hour', type=float, required=True)
    parser.add_argument('--hours', type=float, help='length of the interval ending now (or at --end)')
    parser.add_argument('--start', help='ISO 8601 start, instead of --hours')
    parser.add_argument('--end', help='ISO 8601 end, default now')
    parser.add_argument('--region')
    parser.add_argument('--term', choices=['spot', 'on-demand', 'reserved'], default='reserved')
    attribution(parser)
    parser = leaf(sub, 'ssh', lambda ctx: ssh(ctx.args, ctx.json), Meta(
        'Run a command on a VM over SSH (or open a shell without --json)', effects='write', requires=creds,
        interactive=True), common)
    parser.add_argument('--provider', choices=sorted(PROVIDERS), help='default: found from NAME')
    parser.add_argument('--vm', type=positive, default=1, help='which VM of a node Ornn split into several (1, 2, ...)')
    parser.add_argument('name')
    parser.add_argument('command', nargs=argparse.REMAINDER, help='command to run; put it after --')
    parser = command('s3', s3, Meta('Give the VM expiring credentials for chosen paths of the development '
                                    'training bucket', effects='write', requires=creds), vm=True)
    parser.add_argument('--path', type=bucket_path, action='append',
                        help='bucket path the VM may read and write, such as <project>/<run>; repeat for more. '
                             'Choose a new path for a new run')
    parser.add_argument('--read', type=bucket_path, action='append',
                        help='bucket path the VM may only read, such as an earlier run to resume from; repeatable')
    parser.add_argument('--hours', type=float, default=24,
                        help='how long the credentials last, from 0.25 to 36 hours (default 24)')
    command('start', lifecycle('start'), Meta('Start a stopped (preempted) VM', effects='write', requires=creds),
            vm=True)
    command('stop', lifecycle('stop'), Meta('Stop a VM; its disk is kept and still billed', effects='write',
                                            requires=creds), vm=True)
    command('down', down, Meta('Delete a VM, its disk and its tailnet device; rerunnable', effects='destructive',
                               requires=creds), vm=True)
    parser = leaf(sub, 'setup', lambda ctx: setup(ctx.args), Meta(
        'Admin: write or rotate the provider and Tailscale credentials in gradiated/dev/env', effects='write',
        requires=('aws', 'nebius')), common)
    parser.add_argument('target', nargs='?', choices=['nebius', 'ornn', 'spheron', 'sfcompute', 'tailscale'], default='nebius',
                        help='ornn and spheron read a new API key on stdin; tailscale copies only the Tailscale '
                             'clients')
    parser.add_argument('--aws-profile', default='gradiated-admin')
    parser.add_argument('--rotate-ssh-key', action='store_true',
                        help='replace the SSH key; existing VMs keep trusting only the old one')
