"""Tailscale SSH transport for enrolled GPU hosts.

GPU hosts run no public SSH. Administrators reach them with Tailscale SSH, which
the tailnet policy limits to tailnet admins in check mode (Google sign-in with
MFA, renewed every 12 hours).
"""

import ipaddress
import json
import os
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[2]
HOSTS = ROOT / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/hosts.json'
TAILNET = ipaddress.ip_network('100.64.0.0/10')


def tailnet_address(value):
    address = ipaddress.ip_address(value)
    if address.version != 4 or address not in TAILNET:
        raise ValueError('Expected a Tailscale IPv4 address')
    return str(address)


def resolve(instance_id, hosts=HOSTS):
    """Return the committed Tailscale address of an enrolled host."""
    instance = str(uuid.UUID(instance_id))
    matches = [host for host in json.loads(Path(hosts).read_text()) if host['instance_id'] == instance]
    if len(matches) != 1:
        raise ValueError(f'{instance} is not exactly once in hosts.json')
    return instance, tailnet_address(matches[0]['tailscale_ip'])


def command(address, remote, tailscale=None):
    """Run one remote shell command as root over Tailscale SSH."""
    binary = tailscale or os.environ.get('TAILSCALE', 'tailscale')
    return [binary, 'ssh', 'root@' + tailnet_address(address), remote]
