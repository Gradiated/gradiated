"""The Gradiated tailnet: the connection every gradctl command requires, and joining it.

gradctl runs only on a machine connected to the Gradiated tailnet. Access is
still enforced by the tailnet policy and AWS IAM; this check makes every caller
work from the same network position, so a command never half-runs on a machine
that cannot reach the fleet, the dev-training VMs or the cluster.

In GitHub Actions, which is not on the tailnet, commands that use no network
(repository checks, config rendering) run without it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .core import CliError, Context, DependencyMissing, Meta, Result, UsageError, group, leaf
from .devenv import secret

TAILNET = 'gradiated.com'
MAGIC_DNS_SUFFIX = 'tail186117.ts.net'
DEV_MACHINE_TAG = 'tag:dev-machine'
MAC_BINARY = '/Applications/Tailscale.app/Contents/MacOS/Tailscale'
JOIN_HINT = ('sign in with the Tailscale app as a person (`tailscale up`), or join a headless machine with '
             '`gradctl tailnet join` (needs TAILSCALE_DEV_MACHINE_AUTH_KEY or AWS access to gradiated/dev/env); '
             'in a container without TUN, start `tailscaled --tun=userspace-networking` first and set '
             'TAILSCALE_SOCKET if it uses a non-default socket')


def binary() -> str | None:
    return shutil.which('tailscale') or (MAC_BINARY if Path(MAC_BINARY).exists() else None)


def command(*args: str) -> list[str]:
    path = binary()
    if not path:
        raise DependencyMissing('tailscale', 'install it from https://tailscale.com/download')
    socket = os.environ.get('TAILSCALE_SOCKET')
    return [path, *(['--socket', socket] if socket else []), *args]


def raw_status() -> dict | None:
    try:
        result = subprocess.run(command('status', '--json', '--peers=false'), capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return None
    if not result.stdout.strip():
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def evaluate(status: dict | None) -> dict:
    """Whether a `tailscale status --json` document shows this machine on the Gradiated tailnet."""
    if status is None:
        return {'connected': False, 'reason': 'tailscaled is not running or did not answer'}
    tailnet = (status.get('CurrentTailnet') or {}).get('Name')
    suffix = status.get('MagicDNSSuffix') or (status.get('CurrentTailnet') or {}).get('MagicDNSSuffix')
    me = status.get('Self') or {}
    summary = {'backend_state': status.get('BackendState'), 'tailnet': tailnet,
               'hostname': me.get('HostName'), 'dns_name': (me.get('DNSName') or '').rstrip('.') or None,
               'tags': me.get('Tags') or [], 'addresses': me.get('TailscaleIPs') or []}
    if status.get('BackendState') != 'Running':
        return {'connected': False, 'reason': f"tailscale is {status.get('BackendState') or 'not running'}",
                **summary}
    if tailnet != TAILNET and suffix != MAGIC_DNS_SUFFIX:
        return {'connected': False, 'reason': f'connected to {tailnet or suffix}, not the {TAILNET} tailnet',
                **summary}
    return {'connected': True, 'reason': None, **summary}


def check() -> dict:
    if not binary():
        return {'connected': False, 'reason': 'tailscale is not installed'}
    return evaluate(raw_status())


def require() -> dict:
    state = check()
    if not state['connected']:
        raise CliError(f"gradctl needs the {TAILNET} tailnet: {state['reason']}", 'tailnet_required',
                       JOIN_HINT, 3, data={'tailnet': state})
    return state


def needed(meta: Meta) -> bool:
    if not meta.tailnet:
        return False
    return not (os.environ.get('GITHUB_ACTIONS') == 'true' and not meta.network)


def status_command(ctx: Context) -> Result:
    state = check()
    text = (f"connected to {TAILNET} as {state.get('dns_name') or state.get('hostname')}"
            if state['connected'] else f"not connected: {state['reason']}\nhint: {JOIN_HINT}")
    # Reporting is not failing: the exit code says whether other commands will run.
    return Result(data=state, text=text, ok=state['connected'], exit_code=0 if state['connected'] else 3,
                  error=state['reason'], error_code='tailnet_required')


def join_command(ctx: Context) -> Result:
    state = check()
    if state['connected']:
        return Result(data={**state, 'joined': False}, text=f'already connected to {TAILNET}')
    if not binary():
        raise DependencyMissing('tailscale', 'install it from https://tailscale.com/download')
    if raw_status() is None:
        raise CliError('tailscaled is not running', 'tailscaled_missing',
                       'start it (`tailscaled --tun=userspace-networking --state=mem: &` in a container), '
                       'then rerun')
    if ctx.args.hostname and not all(c.isalnum() or c == '-' for c in ctx.args.hostname):
        raise UsageError('--hostname takes letters, digits and dashes')
    key = secret('TAILSCALE_DEV_MACHINE_AUTH_KEY')
    with tempfile.TemporaryDirectory() as directory:
        os.chmod(directory, 0o700)
        path = Path(directory) / 'auth-key'
        path.touch(mode=0o600)
        path.write_text(key)
        # The key is read from a file so it never appears in a process listing.
        up = command('up', f'--auth-key=file:{path}', f'--advertise-tags={DEV_MACHINE_TAG}',
                     *([f'--hostname={ctx.args.hostname}'] if ctx.args.hostname else []))
        result = subprocess.run(up, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise CliError(f'tailscale up failed: {result.stderr.strip()[:500]}', 'tailnet_join_failed',
                       'run as root or a Tailscale operator (`tailscale set --operator=$USER`)')
    state = check()
    if not state['connected']:
        raise CliError(f"joined but not connected: {state['reason']}", 'tailnet_join_failed', JOIN_HINT,
                       data=state)
    return Result(data={**state, 'joined': True}, text=f"joined {TAILNET} as {state.get('dns_name')}")


def register(commands, common) -> None:
    sub = group(commands, 'tailnet', 'Check or establish the Gradiated tailnet connection gradctl requires')
    leaf(sub, 'status', status_command, Meta('Report whether this machine is on the Gradiated tailnet; exits 3 '
                                             'when it is not', tailnet=False), common)
    join = leaf(sub, 'join', join_command,
                Meta(f'Join a headless machine to the tailnet as an ephemeral {DEV_MACHINE_TAG} device',
                     effects='write', tailnet=False, requires=('tailscale',)), common)
    join.add_argument('--hostname', help='tailnet machine name; default: the OS hostname')
