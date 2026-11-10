#!/usr/bin/env python3
"""Write the credentials dev_training.py needs to gradiated/dev/env.

Run as a Nebius tenant admin (a federated `nebius` profile) with the
gradiated-admin AWS profile, after the tailscale and dev-storage Terraform units
have applied. It is idempotent and doubles as rotation:

Shared by every provider:
- copies the development Tailscale credentials from
  gradiated/prod/platform/tailscale-dev-training;
- issues a new access key for the gradiated-dev-training IAM user, whose only
  permissions are on the development training bucket. The previous key stays
  valid, so running jobs keep uploading, until the next rotation removes it.

Nebius:
- ensures the dev-training service account, a dev-training tenant group holding
  it, and an editor access permit for that group on every project in
  nebius-projects.json, plus tenant viewer for capacity advice (no tenant-level
  write role, so it cannot change IAM);
- issues a new service account key and removes the older ones;
- generates an ed25519 SSH key used only for Nebius dev nodes, once: existing
  VMs only trust the key they were created with, so it is replaced only with
  --rotate-ssh-key;

It merges everything into gradiated/dev/env.

It prints key names and resource IDs, never secret values.
"""

import argparse
import base64
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
CONFIG = json.loads((HERE / 'nebius-projects.json').read_text())
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
    # Tenant viewer is the narrowest role that reads capacity advice
    # (`dev_training.py capacity`); it grants no changes.
    if (tenant, 'viewer') not in permitted:
        nebius('iam', 'access-permit', 'create', '--parent-id', group_id, '--resource-id', tenant, '--role', 'viewer')
        print(f'granted viewer on {tenant}')
    for region, project in sorted(projects.items()):
        if (project, 'editor') not in permitted:
            nebius('iam', 'access-permit', 'create', '--parent-id', group_id, '--resource-id', project,
                   '--role', 'editor')
            print(f'granted editor on {region} ({project})')
    print(f'service account {account_id} in group {group_id}')
    return account_id


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--aws-profile', default='gradiated-admin')
    parser.add_argument('--rotate-ssh-key', action='store_true',
                        help='replace the SSH key; existing VMs keep trusting only the old one')
    args = parser.parse_args()
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
            ssh_key = Path(directory) / 'nebius-dev'
            subprocess.run(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-C', 'gradiated-nebius-dev',
                            '-f', str(ssh_key)], check=True, timeout=30)
            ssh = {'NEBIUS_SSH_PRIVATE_KEY_B64': encode(ssh_key.read_text()),
                   'NEBIUS_SSH_PUBLIC_KEY_B64': encode(Path(f'{ssh_key}.pub').read_text().strip())}
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
            'TAILSCALE_DEV_TRAINING_CLIENT_ID': tailscale['client_id'],
            'TAILSCALE_DEV_TRAINING_CLIENT_SECRET': tailscale['client_secret'],
            'TAILSCALE_DEV_MACHINE_AUTH_KEY': tailscale['machine_auth_key'],
        }
        value = Path(directory) / 'env.json'
        value.write_text(json.dumps({**environment, **added}))
        aws(args.aws_profile, 'secretsmanager', 'put-secret-value', '--secret-id', DEV_SECRET,
            '--secret-string', f'file://{value}')
    print(f'wrote {", ".join(sorted(added))} to {DEV_SECRET}')
    for key_id in old_keys:
        nebius('iam', 'auth-public-key', 'delete', '--id', key_id)
        print(f'removed old service account key {key_id}')


if __name__ == '__main__':
    main()
