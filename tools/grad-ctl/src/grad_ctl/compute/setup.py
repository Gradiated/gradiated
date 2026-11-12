"""`grad-ctl compute setup`: write the credentials `grad-ctl compute` needs to gradiated/dev/env.

Run as a Nebius tenant admin (a federated `nebius` profile) with the
gradiated-admin AWS profile, after the tailscale and dev-storage Terraform units
have applied. It is idempotent and doubles as rotation:

Shared by every provider:
- copies the development Tailscale credentials from
  gradiated/prod/platform/tailscale-dev-training, including each provider's
  key-issuing client (`grad-ctl compute setup tailscale` copies only these, after the
  tailscale Terraform unit replaces a client);
- issues a new access key for the gradiated-dev-training IAM user, whose only
  permissions are on the development training bucket. The previous key stays
  valid, so running jobs keep uploading, until the next rotation removes it.

Nebius:
- ensures the dev-training service account, a dev-training tenant group holding
  it, and an editor access permit for that group on every project in
  nebius-projects.json (no tenant-level role, so it cannot change IAM);
- issues a new service account key and removes the older ones;
- generates an ed25519 SSH key used only for Nebius dev nodes, once: existing
  VMs only trust the key they were created with, so it is replaced only with
  --rotate-ssh-key;

It merges everything into gradiated/dev/env.

`grad-ctl compute setup ornn` sets up Ornn alone and changes nothing else. Ornn API keys can
only be created in its console (Account Settings > Developer > Create key, read
and write), so pass a new key on stdin, for example `pbpaste | grad-ctl compute setup ornn`. It
checks the key, generates an ed25519 SSH key used only for Ornn VMs (once, as
for Nebius), registers it as an Ornn account key, which Ornn installs on every
VM it starts, and writes ORNN_API_KEY, ORNN_ORGANIZATION_ID and ORNN_SSH_* to
gradiated/dev/env. Without a key on stdin it reuses the stored one, so it can
rotate just the SSH key.

It prints key names and resource IDs, never secret values.
"""

import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .nebius import CONFIG
from .ornn import Ornn
NAME = 'dev-training'
HOME_REGION = 'eu-north1'
DEV_SECRET = 'gradiated/dev/env'
TAILSCALE_SECRET = 'gradiated/prod/platform/tailscale-dev-training'
BUCKET_USER = 'gradiated-dev-training'
BUCKET = 'gradiated-dev-training-873716897517'


def nebius(*args):
    binary = shutil.which('nebius') or str(Path.home() / '.nebius/bin/nebius')
    output = subprocess.run([binary, *args, '--format', 'json'], check=True, text=True,
                            stdout=subprocess.PIPE, timeout=120).stdout
    return json.loads(output) if output.strip() else {}


def items(*args, key='items'):
    # List calls return ten entries a page by default; follow every page.
    found, token = [], None
    while True:
        page = nebius(*args, *(['--page-token', token] if token else []))
        found += page.get(key, [])
        token = page.get('next_page_token')
        if not token:
            return found


def aws(profile, *args):
    return subprocess.run(['aws', '--profile', profile, '--region', 'us-east-1', *args], check=True,
                          text=True, stdout=subprocess.PIPE, timeout=60).stdout


def encode(text):
    return base64.b64encode(text.encode()).decode()


def ensure_access():
    tenant, projects = CONFIG['tenant_id'], CONFIG['projects']
    home = projects[HOME_REGION]
    account = next((a for a in items('iam', 'service-account', 'list', '--parent-id', home)
                    if a['metadata']['name'] == NAME), None)
    if account is None:
        account = nebius('iam', 'service-account', 'create', '--parent-id', home, '--name', NAME,
                         '--description', 'Agents: development training VMs (gradiated/dev/env)')
    account_id = account['metadata']['id']
    group = next((g for g in items('iam', 'group', 'list', '--parent-id', tenant)
                  if g['metadata']['name'] == NAME), None)
    if group is None:
        group = nebius('iam', 'group', 'create', '--parent-id', tenant, '--name', NAME)
    group_id = group['metadata']['id']
    members = {m['spec']['member_id'] for m in items('iam', 'group-membership', 'list-members',
                                                      '--parent-id', group_id, key='memberships')}
    if account_id not in members:
        nebius('iam', 'group-membership', 'create', '--parent-id', group_id, '--member-id', account_id)
    permitted = {(p['spec']['resource_id'], p['spec']['role'])
                 for p in items('iam', 'access-permit', 'list', '--parent-id', group_id)}
    for region, project in sorted(projects.items()):
        if (project, 'editor') not in permitted:
            nebius('iam', 'access-permit', 'create', '--parent-id', group_id, '--resource-id', project,
                   '--role', 'editor')
            print(f'granted editor on {region} ({project})')
    print(f'service account {account_id} in group {group_id}')
    return account_id


def ssh_key(directory, comment):
    path = Path(directory) / comment
    subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', comment, '-f', str(path)],
                   check=True, timeout=30)
    return encode(path.read_text()), encode(Path(f'{path}.pub').read_text().strip())


def put_environment(profile, environment, added):
    with tempfile.TemporaryDirectory() as directory:
        os.chmod(directory, 0o700)
        value = Path(directory) / 'env.json'
        value.write_text(json.dumps({**environment, **added}))
        aws(profile, 'secretsmanager', 'put-secret-value', '--secret-id', DEV_SECRET,
            '--secret-string', f'file://{value}')
    print(f'wrote {", ".join(sorted(added))} to {DEV_SECRET}')


def tailscale_environment(profile, tailscale=None):
    tailscale = tailscale or json.loads(aws(profile, 'secretsmanager', 'get-secret-value', '--secret-id',
                                            TAILSCALE_SECRET, '--query', 'SecretString', '--output', 'text'))
    found = {
        'TAILSCALE_DEV_TRAINING_CLIENT_ID': tailscale['client_id'],
        'TAILSCALE_DEV_TRAINING_CLIENT_SECRET': tailscale['client_secret'],
        'TAILSCALE_DEV_MACHINE_AUTH_KEY': tailscale['machine_auth_key'],
    }
    for name, client in tailscale.get('provider_clients', {}).items():
        found[f'TAILSCALE_DEV_TRAINING_{name.upper()}_CLIENT_ID'] = client['client_id']
        found[f'TAILSCALE_DEV_TRAINING_{name.upper()}_CLIENT_SECRET'] = client['client_secret']
    return found


def setup_ornn(args):
    environment = json.loads(aws(args.aws_profile, 'secretsmanager', 'get-secret-value', '--secret-id',
                                 DEV_SECRET, '--query', 'SecretString', '--output', 'text'))
    key = '' if sys.stdin.isatty() else sys.stdin.read().strip()
    key = key or environment.get('ORNN_API_KEY')
    if not key:
        sys.exit('Pass a read and write Ornn API key on stdin, for example `pbpaste | grad-ctl compute setup ornn`')
    ornn = Ornn(lambda name: key, None)
    session = ornn.api('GET', '/v1/auth/session')
    if (session.get('api_key') or {}).get('access') != 'read_write':
        sys.exit('The Ornn key must be an API key with read and write access')
    organization = session['organizations'][0]
    print(f"Ornn API key {session['api_key']['id']} for organization {organization['name']} ({organization['id']})")
    added = {'ORNN_API_KEY': key, 'ORNN_ORGANIZATION_ID': organization['id']}
    ssh = {name: environment[name] for name in ('ORNN_SSH_PRIVATE_KEY_B64', 'ORNN_SSH_PUBLIC_KEY_B64')
           if name in environment}
    if args.rotate_ssh_key or len(ssh) != 2:
        with tempfile.TemporaryDirectory() as directory:
            os.chmod(directory, 0o700)
            private, public = ssh_key(directory, 'gradiated-ornn-dev')
        ssh = {'ORNN_SSH_PRIVATE_KEY_B64': private, 'ORNN_SSH_PUBLIC_KEY_B64': public}
    added.update(ssh)
    public_key = base64.b64decode(ssh['ORNN_SSH_PUBLIC_KEY_B64']).decode().strip()
    keys_path = f"/v1/organizations/{organization['id']}/ssh-keys"
    registered = ornn.api('POST', keys_path, body={'public_key': public_key, 'label': 'gradiated-dev-training'})
    print(f"SSH key {registered['id']} {registered['fingerprint']}: {registered['outcome']}")
    old_keys = [k for k in ornn.api('GET', keys_path, {'status': 'active'})['ssh_keys']
                if k.get('label') == 'gradiated-dev-training' and k['id'] != registered['id']]
    if old_keys:
        # A new organization key reaches only future VMs. Add it to running ones before
        # publishing it, so a failure here leaves gradiated/dev/env on the old key, which
        # every VM still accepts; rerunning reuses the stored new key only once published.
        for status in ('confirmed', 'active'):
            for reservation in ornn.reservations(status=status):
                if reservation.get('kind') in ('spot', 'on-demand'):
                    ornn.api('POST', f"/v1/orchestrator/nodes/reservations/{reservation['reservationId']}/ssh-keys",
                             body={'ssh_key_id': registered['id']})
                    print(f"assigned the new SSH key to reservation {reservation['reservationId']}")
    # Publish before revoking the previous key, so a failure cannot leave none usable.
    put_environment(args.aws_profile, environment, added)
    for old in old_keys:
        ornn.api('DELETE', f"{keys_path}/{old['id']}")
        print(f"revoked previous SSH key {old['id']}")


def run(args):
    """Set up args.target: nebius (default, with the shared keys), ornn or tailscale."""
    if args.target == 'ornn':
        return setup_ornn(args)
    if args.target == 'tailscale':
        environment = json.loads(aws(args.aws_profile, 'secretsmanager', 'get-secret-value', '--secret-id',
                                     DEV_SECRET, '--query', 'SecretString', '--output', 'text'))
        return put_environment(args.aws_profile, environment, tailscale_environment(args.aws_profile))
    # Read both secrets first so a missing one fails before any key is issued.
    tailscale = json.loads(aws(args.aws_profile, 'secretsmanager', 'get-secret-value', '--secret-id',
                               TAILSCALE_SECRET, '--query', 'SecretString', '--output', 'text'))
    environment = json.loads(aws(args.aws_profile, 'secretsmanager', 'get-secret-value', '--secret-id',
                                 DEV_SECRET, '--query', 'SecretString', '--output', 'text'))
    listed = subprocess.run(['aws', '--profile', args.aws_profile, '--region', 'us-east-1', 'iam',
                             'list-access-keys', '--user-name', BUCKET_USER],
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60)
    # The bucket user comes from the dev-storage Terraform unit; until it exists,
    # set up everything else and add the bucket key on a later run.
    bucket_user = listed.returncode == 0
    if not bucket_user and 'NoSuchEntity' not in listed.stderr:
        raise SystemExit(listed.stderr.strip())
    if not bucket_user:
        print(f'{BUCKET_USER} does not exist yet; skipping the bucket key. Run this again once it does.')
    aws_keys = [k['AccessKeyId'] for k in json.loads(listed.stdout)['AccessKeyMetadata']] if bucket_user else []
    unused = [k for k in aws_keys if k != environment.get('DEV_TRAINING_AWS_ACCESS_KEY_ID')]
    if len(aws_keys) >= 2 and unused:
        # IAM allows two keys a user. The one in gradiated/dev/env becomes the
        # previous key and stays valid; the older one is retired.
        aws(args.aws_profile, 'iam', 'delete-access-key', '--user-name', BUCKET_USER, '--access-key-id', unused[0])
        print(f'removed older bucket access key {unused[0]}')
    account_id = ensure_access()
    old_keys = [k['metadata']['id'] for k in items('iam', 'auth-public-key', 'list-by-account',
                                                   '--account-service-account-id', account_id)]
    with tempfile.TemporaryDirectory() as directory:
        os.chmod(directory, 0o700)
        credentials = Path(directory) / 'service-account.json'
        nebius('iam', 'auth-public-key', 'generate', '--service-account-id', account_id,
               '--output', str(credentials), '--output-format', 'service-account-json')
        ssh = {name: environment[name] for name in ('NEBIUS_SSH_PRIVATE_KEY_B64', 'NEBIUS_SSH_PUBLIC_KEY_B64')
               if name in environment}
        if args.rotate_ssh_key or len(ssh) != 2:
            private, public = ssh_key(directory, 'gradiated-nebius-dev')
            ssh = {'NEBIUS_SSH_PRIVATE_KEY_B64': private, 'NEBIUS_SSH_PUBLIC_KEY_B64': public}
        bucket = {'DEV_TRAINING_S3_BUCKET': BUCKET}
        if bucket_user:
            key = json.loads(aws(args.aws_profile, 'iam', 'create-access-key', '--user-name', BUCKET_USER))['AccessKey']
            bucket.update({'DEV_TRAINING_AWS_ACCESS_KEY_ID': key['AccessKeyId'],
                           'DEV_TRAINING_AWS_SECRET_ACCESS_KEY': key['SecretAccessKey']})
        # Base64 keeps multi-line and quoted values safe in a sourced .env file.
        added = {
            **bucket,
            'NEBIUS_TENANT_ID': CONFIG['tenant_id'],
            'NEBIUS_SERVICE_ACCOUNT_CREDENTIALS_B64': encode(credentials.read_text()),
            **ssh,
            **tailscale_environment(args.aws_profile, tailscale),
        }
    put_environment(args.aws_profile, environment, added)
    for key_id in old_keys:
        nebius('iam', 'auth-public-key', 'delete', '--id', key_id)
        print(f'removed old service account key {key_id}')
