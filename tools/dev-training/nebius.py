"""Nebius spot VMs for dev_training.py.

Credentials come from NEBIUS_SERVICE_ACCOUNT_CREDENTIALS_B64 (the dev-training
service account, editor on the regional projects in nebius-projects.json).
setup.py creates the account and writes its keys to gradiated/dev/env.
"""

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

CONFIG = json.loads((Path(__file__).resolve().parent / 'nebius-projects.json').read_text())
PROJECTS, TENANT = CONFIG['projects'], CONFIG['tenant_id']


class Nebius:
    name = 'nebius'
    ssh_user = 'ubuntu'
    default_region = 'eu-north1'

    def __init__(self, secret, state):
        self.secret, self.state = secret, state

    def cli(self, *args, missing_ok=False):
        binary = shutil.which('nebius') or str(Path.home() / '.nebius/bin/nebius')
        if not Path(binary).exists():
            sys.exit('Install the nebius CLI: curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash')
        config = self.state / 'nebius.yaml'
        credentials = self.state / 'nebius-service-account.json'
        current = self.secret('NEBIUS_SERVICE_ACCOUNT_CREDENTIALS_B64')
        # Rebuild the profile after setup.py rotates the key; the old one is revoked.
        if not config.exists() or not credentials.exists() or credentials.read_text() != current:
            config.unlink(missing_ok=True)
            credentials.touch(mode=0o600)
            credentials.write_text(current)
            subprocess.run([binary, '-c', str(config), 'profile', 'create', 'dev-training', '--endpoint',
                            'api.nebius.cloud', '--service-account-file', str(credentials),
                            '--parent-id', PROJECTS[self.default_region]],
                           check=True, stdout=subprocess.DEVNULL, timeout=60)
        result = subprocess.run([binary, '-c', str(config), *args, '--format', 'json'], text=True,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        if result.returncode:
            # Only a NotFound answer means absent; any other failure must stop the caller.
            if missing_ok and 'code = NotFound' in result.stderr:
                return None
            sys.exit(result.stderr.strip())
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def regions(self):
        return sorted(PROJECTS)

    def project(self, region):
        if region not in PROJECTS:
            sys.exit(f'Unknown Nebius region {region}; choose from {", ".join(self.regions())}')
        return PROJECTS[region]

    def platforms(self, region):
        for platform in self.items('compute', 'platform', 'list', '--parent-id', self.project(region)):
            if platform['metadata']['name'].startswith('gpu'):
                yield f"{platform['metadata']['name']}: {', '.join(p['name'] for p in platform['spec'].get('presets', []))}"

    def capacity(self, platform):
        """Live availability per region and preset, from Nebius resource advice."""
        level = lambda status: (status or {}).get('availability_level', '-').replace('AVAILABILITY_LEVEL_', '')
        count = lambda status: f"{(status or {}).get('available', 0)}/{(status or {}).get('limit', '-')}"
        for advice in self.items('capacity', 'resource-advice', 'list', '--parent-id', TENANT):
            instance = advice['spec'].get('compute_instance')
            if not instance or (platform and platform not in instance['platform']):
                continue
            status = advice.get('status', {})
            yield (f"{instance['platform']:16} {instance['preset']['name']:22} {advice['spec']['region'] + '/' + advice['spec'].get('fabric', '-'):24} "
                   f"spot {level(status.get('preemptible')):13} {count(status.get('preemptible')):6} "
                   f"on-demand {level(status.get('on_demand')):13} {count(status.get('on_demand'))}")

    @staticmethod
    def vm(region, instance):
        address = next((i['public_ip_address']['address'].split('/')[0]
                        for i in instance.get('status', {}).get('network_interfaces', [])
                        if i.get('public_ip_address', {}).get('address')), None)
        resources = instance['spec']['resources']
        return {'name': instance['metadata']['name'], 'id': instance['metadata']['id'], 'region': region,
                'state': instance.get('status', {}).get('state', ''), 'address': address,
                'shape': f"{resources['platform']}/{resources['preset']}"}

    def find(self, name):
        for region, parent in PROJECTS.items():
            instance = self.cli('compute', 'instance', 'get-by-name', '--parent-id', parent, '--name', name,
                                missing_ok=True)
            if instance:
                return self.vm(region, instance)
        return None

    def items(self, *args):
        # List calls return ten entries a page by default; follow every page.
        token = None
        while True:
            page = self.cli(*args, *(['--page-token', token] if token else []))
            yield from page.get('items', [])
            token = page.get('next_page_token')
            if not token:
                return

    def list(self):
        for region, parent in sorted(PROJECTS.items()):
            for instance in self.items('compute', 'instance', 'list', '--parent-id', parent):
                yield self.vm(region, instance)

    def create(self, name, region, platform, preset, disk_gib, image, user_data):
        parent = self.project(region)
        subnets = list(self.items('vpc', 'subnet', 'list', '--parent-id', parent))
        if not subnets:
            sys.exit(f'No subnet in {region}')
        spec = {
            'metadata': {'parent_id': parent, 'name': name, 'labels': {'purpose': 'dev-training'}},
            'spec': {
                'resources': {'platform': platform, 'preset': preset},
                'network_interfaces': [{'name': 'eth0', 'subnet_id': subnets[0]['metadata']['id'],
                                        'ip_address': {}, 'public_ip_address': {}}],
                'boot_disk': {'attach_mode': 'READ_WRITE', 'managed_disk': {
                    'name': name + '-boot', 'spec': {
                        'size_bytes': str(disk_gib * 1024 ** 3), 'type': 'NETWORK_SSD',
                        'source_image_family': {'image_family': image or 'ubuntu24.04-cuda13.0'}}}},
                # Preemption stops the VM; pricing defaults to on-demand, so ask for spot.
                'preemptible': {'on_preemption': 'STOP'},
                # Nebius accepts only FAIL for preemptible VMs.
                'recovery_policy': 'FAIL',
                'follows_spot_price': {},
                'cloud_init_user_data': user_data,
            },
        }
        # One request file per launch, so concurrent launches cannot read each other's.
        with tempfile.NamedTemporaryFile('w', dir=self.state, suffix='.json') as request:
            json.dump(spec, request)
            request.flush()
            self.cli('compute', 'instance', 'create', '--file', request.name)

    def start(self, vm):
        self.cli('compute', 'instance', 'start', '--id', vm['id'])

    def stop(self, vm):
        self.cli('compute', 'instance', 'stop', '--id', vm['id'])

    def delete(self, vm):
        self.cli('compute', 'instance', 'delete', '--id', vm['id'])
