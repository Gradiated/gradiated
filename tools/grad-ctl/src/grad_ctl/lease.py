"""`grad-ctl gpu lease`: lease a whole GPU host out of the serving pool, and hand it back.

The gpu-fleet operator does the work: on acquire it moves the host's model
replicas elsewhere, drains and cordons it; on release or expiry it re-images the
pod, wiping its disk, re-enrolls it and returns it to the pool. A lease that
cannot start fails at once and is not retried. A lease is preemptible unless
acquired with --no-preempt: the operator takes the host back when a model
replica has nowhere else to run. This tool only writes the request (the
fleet.gradiated.com/lease annotation) and reports state.

  grad-ctl gpu lease acquire 01a0f19d --hours 6 --purpose "SFT sweep" [--holder me] [--no-preempt]
  grad-ctl gpu lease wait 01a0f19d
  grad-ctl gpu lease extend 01a0f19d --hours 2
  grad-ctl gpu lease release 01a0f19d
  grad-ctl gpu lease status [01a0f19d]
"""
from datetime import datetime, timedelta, timezone
import getpass
import json
import shutil
import subprocess
import time

from .core import Context, DependencyMissing, Meta, Result, group, leaf

ANNOTATION = 'fleet.gradiated.com/lease'
RESERVED = 'gradiated.com/reserved'
MAX_HOURS = 7 * 24


def timestamp(value):
    """An RFC 3339 time; Python before 3.11 does not read a trailing Z."""
    return datetime.fromisoformat(value[:-1] + '+00:00' if value.endswith('Z') else value)


class Conflict(Exception):
    """The GpuHost changed since it was read."""


def kubectl(*args, capture=True):
    if not shutil.which('kubectl'):
        raise DependencyMissing('kubectl', 'install it with `mise install` and configure the EKS context')
    result = subprocess.run(['kubectl', '--request-timeout=20s', *args], capture_output=capture, text=True, timeout=60)
    if result.returncode:
        if 'the object has been modified' in (result.stderr or ''):
            raise Conflict()
        raise SystemExit(f'kubectl {" ".join(args[:3])} failed: {(result.stderr or "").strip()}')
    return result.stdout


def hosts():
    return json.loads(kubectl('get', 'gpuhosts', '-o', 'json'))['items']


def find(hosts, name):
    wanted = name.removeprefix('gpu-')
    matches = [host for host in hosts if host['spec']['instanceId'].startswith(wanted)]
    if len(matches) != 1:
        raise SystemExit(f'{name!r} matches {len(matches)} hosts; give more of the instance ID')
    return matches[0]


def request_of(host):
    value = host['metadata'].get('annotations', {}).get(ANNOTATION)
    return json.loads(value) if value else None


def build_request(holder, purpose, hours, now, preemptible=True):
    if not 0 < hours <= MAX_HOURS:
        raise SystemExit(f'A lease lasts more than 0 and at most {MAX_HOURS} hours')
    if not 0 < len(holder) <= 100 or not 0 < len(purpose) <= 500:
        raise SystemExit('holder must be 1-100 characters and purpose 1-500')
    until = (now + timedelta(hours=hours)).replace(microsecond=0)
    return {'holder': holder, 'purpose': purpose, 'until': until.isoformat().replace('+00:00', 'Z'),
            'preemptible': preemptible}


def normal(request):
    """A request as the operator records it, with preemptible filled in."""
    return {**request, 'preemptible': request.get('preemptible', True)} if request else None


def outcome(rollout):
    """How the lease request the rollout records ended, or None."""
    if not rollout.get('lease'):
        return None
    if rollout.get('kind') == 'lease' and rollout.get('result') == 'Failed':
        return f'failed: {rollout.get("lastError")}'
    if rollout.get('kind') == 'return' and rollout.get('result') == 'Succeeded':
        started = rollout.get('startedAt')
        expired = started and timestamp(rollout['lease']['until']) <= timestamp(started)
        return 'expired' if expired else 'preempted'
    return None


def ended(host):
    """Whether the host's request already had its outcome; the operator
    removes such a request on its next pass."""
    status = host.get('status', {})
    rollout = status.get('rollout') or {}
    request = request_of(host)
    return bool(request) and not status.get('lease') and outcome(rollout) is not None and \
        rollout['lease'] == normal(request)


def state(host, now=None):
    status = host.get('status', {})
    rollout = status.get('rollout') or {}
    request = request_of(host)
    lease = status.get('lease')
    if lease:
        if rollout.get('kind') == 'return' and rollout.get('result') == 'Running':
            return f'returning ({rollout.get("step")})'
        if rollout.get('kind') == 'return' and rollout.get('result') == 'Failed':
            return f'return failed: {rollout.get("lastError")}'
        if not request:
            return 'handed back, waiting for its return'
        if request.get('holder') != lease['holder']:
            return f'given to {request.get("holder")}, waiting for its return'
        if timestamp(request['until']) <= (now or datetime.now(timezone.utc)):
            return 'expired, waiting for its return'
        return 'leased'
    if request:
        if ended(host):
            return f'lease {outcome(rollout)}'
        if rollout.get('kind') == 'lease' and rollout.get('result') == 'Running':
            return f'leasing ({rollout.get("step")})'
        return 'requested'
    return 'in pool'


def annotate(host, request):
    """Writes the request only if the host is as it was read, so two holders
    acquiring at once cannot both believe they won."""
    name = host['metadata']['name']
    version = f'--resource-version={host["metadata"]["resourceVersion"]}'
    if request is None:
        kubectl('annotate', 'gpuhost', name, version, f'{ANNOTATION}-')
    else:
        kubectl('annotate', 'gpuhost', name, version, '--overwrite',
                f'{ANNOTATION}={json.dumps(request, separators=(",", ":"))}')


def change(name, update):
    """Applies update to a freshly read host, again if the operator wrote its
    status in between; update re-checks the host each time."""
    for _ in range(5):
        host = find(hosts(), name)
        try:
            return update(host)
        except Conflict:
            time.sleep(1)
    raise SystemExit('The host kept changing; try again')


def own(host, holder, force):
    request = request_of(host)
    if request and request['holder'] != holder and not force:
        raise SystemExit(f'The host is leased to {request["holder"]}; pass --force to override')
    return request


def summary(host):
    """The host and its lease as the operator records them."""
    request = request_of(host) or {}
    lease = host.get('status', {}).get('lease') or {}
    inventory = host['spec']['inventory']
    reserved = [taint['value'] for taint in host['spec'].get('extraTaints', []) if taint.get('key') == RESERVED]
    current = state(host)
    if current == 'in pool' and reserved:
        current = f'reserved for {reserved[0]}'
    elif current == 'in pool' and outcome(host.get('status', {}).get('rollout') or {}):
        current = f'in pool (last lease {outcome(host["status"]["rollout"])})'
    held = bool(request or lease)
    return {
        'instance_id': host['spec']['instanceId'],
        'gpus': inventory['gpuCount'],
        'gpu': inventory['gpuProduct'],
        'state': current,
        'reserved_for': reserved[0] if reserved else None,
        'lease': {'holder': request.get('holder') or lease.get('holder'), 'until': request.get('until'),
                  'since': lease.get('since'), 'preemptible': request.get('preemptible', True),
                  'purpose': request.get('purpose') or lease.get('purpose')} if held else None,
        'operator_plan': host.get('status', {}).get('plan'),
    }


def format_summary(item):
    lines = [f"{item['instance_id']}  {item['gpus']}x{item['gpu']}  {item['state']}"]
    if item['lease']:
        lease = item['lease']
        lines.append(f"  holder={lease['holder']}  until={lease['until'] or '-'}  since={lease['since'] or '-'}  "
                     f"preemptible={str(lease['preemptible']).lower()}  purpose={lease['purpose']}")
    if item['operator_plan']:
        lines.append(f"  operator: {item['operator_plan']}")
    return '\n'.join(lines)


def shown(host, message=None, ok=True, error=None):
    item = summary(host)
    text = format_summary(item) + (f'\n{message}' if message else '')
    return Result(data={'host': item, 'message': message}, text=text, ok=ok, exit_code=0 if ok else 1, error=error,
                  error_code='lease_failed')


def resolve_holder(args):
    """The OS user when --holder is not given, looked up only when a command needs it."""
    if args.holder is None:
        try:
            args.holder = getpass.getuser()
        except (KeyError, OSError):
            raise SystemExit('Cannot tell who you are; pass --holder') from None
    return args.holder


def status_command(ctx: Context) -> Result:
    wanted = (ctx.args.host or '').removeprefix('gpu-')
    items = [summary(host) for host in sorted(hosts(), key=lambda item: item['spec']['instanceId'])
             if host['spec']['instanceId'].startswith(wanted)]
    return Result(data=items, text='\n'.join(format_summary(item) for item in items) or 'no matching hosts')


def acquire_command(ctx: Context) -> Result:
    resolve_holder(ctx.args)
    args, now = ctx.args, datetime.now(timezone.utc)

    def acquire_host(host):
        if any(taint.get('key') == RESERVED for taint in host['spec'].get('extraTaints', [])):
            raise SystemExit('Reserved hosts cannot be leased')
        if not (state(host) == 'in pool' or ended(host)):
            raise SystemExit(f'The host is already {state(host)}; use extend or release')
        annotate(host, build_request(args.holder, args.purpose, args.hours, now, not args.no_preempt))
    change(args.host, acquire_host)
    return shown(find(hosts(), args.host),
                 'Requested. The operator drains the host first; run `grad-ctl gpu lease wait` until it is leased.')


def extend_command(ctx: Context) -> Result:
    resolve_holder(ctx.args)
    args, now = ctx.args, datetime.now(timezone.utc)

    def extend_host(host):
        request = own(host, args.holder, False)
        if state(host) != 'leased':
            raise SystemExit(f'Only a leased host can be extended; it is {state(host)}')
        annotate(host, build_request(request['holder'], request['purpose'], args.hours, now,
                                     request.get('preemptible', True)))
    change(args.host, extend_host)
    return shown(find(hosts(), args.host))


def release_command(ctx: Context) -> Result:
    resolve_holder(ctx.args)
    args = ctx.args

    def release_host(host):
        if not own(host, args.holder, args.force):
            raise SystemExit('The host has no lease to release')
        annotate(host, None)
    change(args.host, release_host)
    return shown(find(hosts(), args.host),
                 'Handed back. The operator re-images the host, wiping its disk, then returns it to the pool.')


def wait_command(ctx: Context) -> Result:
    resolve_holder(ctx.args)
    args = ctx.args
    # Waits on the request as first read, so an old outcome or someone
    # else's request is never mistaken for this one's.
    host = find(hosts(), args.host)
    mine = normal(request_of(host))
    if not mine or mine['holder'] != args.holder:
        return shown(host, ok=False, error=f'The host has no lease request from {args.holder}')
    deadline = time.monotonic() + args.timeout_minutes * 60
    while True:
        status = host.get('status', {})
        rollout = status.get('rollout') or {}
        if state(host) == 'leased' and normal(request_of(host)) == mine:
            return shown(host)
        if rollout.get('lease') == mine and outcome(rollout):
            return shown(host, ok=False, error=f'Lease {outcome(rollout)}')
        if normal(request_of(host)) != mine:
            return shown(host, ok=False, error='The lease request was removed or replaced')
        if time.monotonic() > deadline:
            return shown(host, ok=False, error='Timed out waiting for the lease')
        time.sleep(30)
        host = find(hosts(), args.host)


def register(gpu, common) -> None:
    sub = group(gpu, 'lease', 'Lease a whole GPU host out of the serving pool, and hand it back (see $gpu-host-lease)')
    needs = ('kubectl',)
    holder = dict(default=None, help='who holds the lease; default: the OS user')
    parser = leaf(sub, 'acquire', acquire_command, Meta(
        'Request a lease; the operator drains the host, then `wait` reports it leased', effects='write',
        requires=needs), common)
    parser.add_argument('host', help='instance ID or a unique prefix of it')
    parser.add_argument('--hours', type=float, required=True)
    parser.add_argument('--purpose', required=True)
    parser.add_argument('--holder', **holder)
    parser.add_argument('--no-preempt', action='store_true',
                        help='keep the host even when a model has nowhere else to run')
    parser = leaf(sub, 'extend', extend_command, Meta('Set a leased host\'s remaining time from now',
                                                      effects='write', requires=needs), common)
    parser.add_argument('host')
    parser.add_argument('--hours', type=float, required=True, help='new remaining duration from now')
    parser.add_argument('--holder', **holder)
    parser = leaf(sub, 'release', release_command, Meta(
        'Hand the host back; the operator re-images it, wiping its disk', effects='destructive', requires=needs),
        common)
    parser.add_argument('host')
    parser.add_argument('--holder', **holder)
    parser.add_argument('--force', action='store_true', help="hand back another holder's lease")
    parser = leaf(sub, 'wait', wait_command, Meta('Wait until the host is leased or the lease fails',
                                                  requires=needs), common)
    parser.add_argument('host')
    parser.add_argument('--holder', **holder)
    parser.add_argument('--timeout-minutes', type=float, default=150)
    parser = leaf(sub, 'status', status_command, Meta('Show every host, or one, with its lease state',
                                                      requires=needs), common)
    parser.add_argument('host', nargs='?')
