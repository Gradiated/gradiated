#!/usr/bin/env python3
import ipaddress
import os
import sys
TAILNET = ipaddress.ip_network("100.64.0.0/10")


def forward(address, port):
    if ipaddress.ip_address(address) not in TAILNET or port != 3004:
        raise ValueError('Invalid private control destination')
    os.execv('/opt/gradiated/tailscale/tailscale', [
        'tailscale', '--socket=/var/lib/gradiated-tailscale/socket', 'nc', address, str(port),
    ])


if __name__ == '__main__':
    forward(sys.argv[1], int(sys.argv[2]))
