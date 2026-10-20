#!/usr/bin/env python3
"""Check the tailnet policy with Tailscale's validate endpoint before it is applied.

Tailscale parses the policy and runs its `tests` and `sshTests` blocks against
the live tailnet without changing anything. Credentials come from
TAILSCALE_OAUTH_CLIENT_ID and TAILSCALE_OAUTH_CLIENT_SECRET (the read-only plan
client is sufficient) and are never printed.
"""

import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

API = 'https://api.tailscale.com/api/v2'
POLICY = Path(__file__).resolve().parents[2] / 'infra/environments/prod/us-east-1/terraform/tailscale/policy.hujson'


def failures(response):
    """Return readable failures from a validate response; an empty object means success."""
    if not response:
        return []
    found = [response.get('message', 'Policy rejected')]
    for item in response.get('data') or []:
        found.extend(f"{item.get('user', '?')}: {error}" for error in item.get('errors') or [])
    return found


def validate(policy, client_id, client_secret, urlopen=urllib.request.urlopen):
    data = urllib.parse.urlencode({'client_id': client_id, 'client_secret': client_secret,
                                   'grant_type': 'client_credentials'}).encode()
    with urlopen(urllib.request.Request(API + '/oauth/token', data=data), timeout=30) as response:
        token = json.load(response)['access_token']
    request = urllib.request.Request(API + '/tailnet/-/acl/validate', data=policy, method='POST',
                                     headers={'Authorization': 'Bearer ' + token,
                                              'Content-Type': 'application/hujson'})
    try:
        with urlopen(request, timeout=30) as response:
            return failures(json.load(response))
    except urllib.error.HTTPError as error:
        return failures(json.loads(error.read() or b'{}')) or [f'Tailscale returned HTTP {error.code}']


def main():
    problems = validate(POLICY.read_bytes(), os.environ['TAILSCALE_OAUTH_CLIENT_ID'],
                        os.environ['TAILSCALE_OAUTH_CLIENT_SECRET'])
    for problem in problems:
        print(problem, file=sys.stderr)
    if problems:
        sys.exit(1)
    print(f'{POLICY.name}: valid; all tests and sshTests pass')


if __name__ == '__main__':
    main()
