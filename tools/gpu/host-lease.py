#!/usr/bin/env python3
"""Lease a whole GPU host out of the serving pool, and hand it back.

The gpu-fleet operator does the work: on acquire it moves the host's model
replicas elsewhere, drains and cordons it; on release or expiry it re-images the
pod, wiping its disk, re-enrolls it and returns it to the pool. A lease that
cannot start fails at once and is not retried. A lease is preemptible unless
acquired with --no-preempt: the operator takes the host back when a model
replica has nowhere else to run. This tool only writes the request (the
fleet.gradiated.com/lease annotation) and reports state.

  host-lease.py acquire 01a0f19d --hours 6 --purpose "SFT sweep" [--holder me] [--no-preempt]
  host-lease.py wait 01a0f19d
  host-lease.py extend 01a0f19d --hours 2
  host-lease.py release 01a0f19d
  host-lease.py status [01a0f19d]
"""
import argparse
from datetime import datetime, timedelta, timezone
import getpass
import json
import subprocess
import sys
import time

ANNOTATION = 'fleet.gradiated.com/lease'
RESERVED = 'gradiated.com/reserved'
MAX_HOURS = 7 * 24


class Conflict(Exception):
    """The GpuHost changed since it was read."""


def kubectl(*args, capture=True):
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
        expired = started and datetime.fromisoformat(rollout['lease']['until']) <= datetime.fromisoformat(started)
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
        if datetime.fromisoformat(request['until']) <= (now or datetime.now(timezone.utc)):
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


def show(host):
    request = request_of(host) or {}
    lease = host.get('status', {}).get('lease') or {}
    inventory = host['spec']['inventory']
    reserved = [taint['value'] for taint in host['spec'].get('extraTaints', []) if taint.get('key') == RESERVED]
    current = state(host)
    if current == 'in pool' and reserved:
        current = f'reserved for {reserved[0]}'
    elif current == 'in pool' and outcome(host.get('status', {}).get('rollout') or {}):
        current = f'in pool (last lease {outcome(host["status"]["rollout"])})'
    print(f'{host["spec"]["instanceId"]}  {inventory["gpuCount"]}x{inventory["gpuProduct"]}  {current}')
    if request or lease:
        print(f'  holder={request.get("holder") or lease.get("holder")}  until={request.get("until", "-")}  '
              f'since={lease.get("since", "-")}  preemptible={str(request.get("preemptible", True)).lower()}  '
              f'purpose={request.get("purpose") or lease.get("purpose")}')
    plan = host.get('status', {}).get('plan')
    if plan:
        print(f'  operator: {plan}')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest='command', required=True)
    acquire = commands.add_parser('acquire')
    acquire.add_argument('host')
    acquire.add_argument('--hours', type=float, required=True)
    acquire.add_argument('--purpose', required=True)
    acquire.add_argument('--holder', default=getpass.getuser())
    acquire.add_argument('--no-preempt', action='store_true',
                         help='keep the host even when a model has nowhere else to run')
    extend = commands.add_parser('extend')
    extend.add_argument('host')
    extend.add_argument('--hours', type=float, required=True, help='new remaining duration from now')
    extend.add_argument('--holder', default=getpass.getuser())
    release = commands.add_parser('release')
    release.add_argument('host')
    release.add_argument('--holder', default=getpass.getuser())
    release.add_argument('--force', action='store_true', help='hand back another holder\'s lease')
    wait = commands.add_parser('wait')
    wait.add_argument('host')
    wait.add_argument('--holder', default=getpass.getuser())
    wait.add_argument('--timeout-minutes', type=float, default=150)
    status = commands.add_parser('status')
    status.add_argument('host', nargs='?')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)

    if args.command == 'status':
        for host in sorted(hosts(), key=lambda item: item['spec']['instanceId']):
            if not args.host or host['spec']['instanceId'].startswith(args.host.removeprefix('gpu-')):
                show(host)
        return

    if args.command == 'acquire':
        def acquire_host(host):
            if any(taint.get('key') == RESERVED for taint in host['spec'].get('extraTaints', [])):
                raise SystemExit('Reserved hosts cannot be leased')
            if not (state(host) == 'in pool' or ended(host)):
                raise SystemExit(f'The host is already {state(host)}; use extend or release')
            annotate(host, build_request(args.holder, args.purpose, args.hours, now, not args.no_preempt))
        change(args.host, acquire_host)
        print('Requested. The operator drains the host first; run `host-lease.py wait` until it is leased.')
    elif args.command == 'extend':
        def extend_host(host):
            request = own(host, args.holder, False)
            if state(host) != 'leased':
                raise SystemExit(f'Only a leased host can be extended; it is {state(host)}')
            annotate(host, build_request(request['holder'], request['purpose'], args.hours, now,
                                         request.get('preemptible', True)))
        change(args.host, extend_host)
    elif args.command == 'release':
        def release_host(host):
            if not own(host, args.holder, args.force):
                raise SystemExit('The host has no lease to release')
            annotate(host, None)
        change(args.host, release_host)
        print('Handed back. The operator re-images the host, wiping its disk, then returns it to the pool.')
    elif args.command == 'wait':
        # Waits on the request as first read, so an old outcome or someone
        # else's request is never mistaken for this one's.
        host = find(hosts(), args.host)
        mine = normal(request_of(host))
        if not mine or mine['holder'] != args.holder:
            show(host)
            raise SystemExit(f'The host has no lease request from {args.holder}')
        deadline = time.monotonic() + args.timeout_minutes * 60
        while True:
            status = host.get('status', {})
            rollout = status.get('rollout') or {}
            if state(host) == 'leased' and normal(request_of(host)) == mine:
                show(host)
                return
            if rollout.get('lease') == mine and outcome(rollout):
                show(host)
                raise SystemExit(f'Lease {outcome(rollout)}')
            if normal(request_of(host)) != mine:
                show(host)
                raise SystemExit('The lease request was removed or replaced')
            if time.monotonic() > deadline:
                show(host)
                raise SystemExit('Timed out waiting for the lease')
            time.sleep(30)
            host = find(hosts(), args.host)
    show(find(hosts(), args.host))


if __name__ == '__main__':
    main()
