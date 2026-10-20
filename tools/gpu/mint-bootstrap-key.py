#!/usr/bin/env python3
"""Mint the single-use Tailscale key a new or re-imaged GPU pod uses on first start.

The key is pre-authorized, single-use, short-lived and tagged tag:gpu-bootstrap,
which has no network grants: only tailnet admins and ops-mcp can reach the pod,
and only with Tailscale SSH. Paste it into the RunPod secret
gradiated_tailscale_bootstrap immediately before creating or re-imaging one pod.
"""

import argparse
import json
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request

API = 'https://api.tailscale.com/api/v2'
SECRET = 'gradiated/prod/platform/tailscale-gpu-bootstrap'
MAX_HOURS = 24


def token(profile, check_output=subprocess.check_output, urlopen=urllib.request.urlopen):
    secret = json.loads(check_output(
        ['aws', 'secretsmanager', 'get-secret-value', '--profile', profile, '--region', 'us-east-1',
         '--secret-id', SECRET, '--query', 'SecretString', '--output', 'text'], text=True, timeout=30))
    data = urllib.parse.urlencode({'client_id': secret['client_id'], 'client_secret': secret['client_secret'],
                                   'grant_type': 'client_credentials'}).encode()
    with urlopen(urllib.request.Request(API + '/oauth/token', data=data), timeout=30) as response:
        return json.load(response)['access_token']


def key_request(pod, hours):
    if not re.fullmatch('[a-z0-9]{1,40}', pod):
        raise ValueError('Expected a RunPod pod ID')
    if not 1 <= hours <= MAX_HOURS:
        raise ValueError(f'Bootstrap keys last 1 to {MAX_HOURS} hours')
    return {
        'capabilities': {'devices': {'create': {
            'reusable': False, 'ephemeral': False, 'preauthorized': True, 'tags': ['tag:gpu-bootstrap']}}},
        'expirySeconds': hours * 3600,
        'description': f'GPU bootstrap {pod}',
    }


def mint(pod, hours, bearer, urlopen=urllib.request.urlopen):
    request = urllib.request.Request(API + '/tailnet/-/keys', data=json.dumps(key_request(pod, hours)).encode(),
                                     headers={'Authorization': 'Bearer ' + bearer, 'Content-Type': 'application/json'})
    with urlopen(request, timeout=30) as response:
        created = json.load(response)
    if not created['key'].startswith('tskey-auth-'):
        raise ValueError('Tailscale returned an unexpected key type')
    return created


def revoke(key_id, bearer, urlopen=urllib.request.urlopen):
    if not re.fullmatch('[A-Za-z0-9]+', key_id):
        raise ValueError('Expected a Tailscale key ID')
    request = urllib.request.Request(f'{API}/tailnet/-/keys/{key_id}', method='DELETE',
                                     headers={'Authorization': 'Bearer ' + bearer})
    with urlopen(request, timeout=30) as response:
        response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--pod', help='RunPod pod ID that will consume the key')
    parser.add_argument('--hours', type=int, default=6)
    parser.add_argument('--profile', default='gradiated-admin')
    parser.add_argument('--print', action='store_true', help='write the key to stdout instead of the clipboard')
    parser.add_argument('--revoke', metavar='KEY_ID', help='revoke an unused bootstrap key')
    args = parser.parse_args()
    bearer = token(args.profile)
    if args.revoke:
        revoke(args.revoke, bearer)
        print(f'Revoked {args.revoke}', file=sys.stderr)
        return
    if not args.pod:
        parser.error('--pod is required')
    created = mint(args.pod, args.hours, bearer)
    if args.print:
        print(created['key'])
    elif shutil.which('pbcopy'):
        subprocess.run(['pbcopy'], input=created['key'], text=True, check=True)
    else:
        parser.error('No clipboard available; rerun with --print')
    print(f"Bootstrap key {created['id']} for pod {args.pod} expires {created.get('expires', 'in ' + str(args.hours) + 'h')}. "
          'Set it as the RunPod secret gradiated_tailscale_bootstrap now.', file=sys.stderr)


if __name__ == '__main__':
    main()
