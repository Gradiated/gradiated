"""Nebius VMs (spot or on-demand) for `grad-ctl compute`.

Credentials come from NEBIUS_SERVICE_ACCOUNT_CREDENTIALS_B64 (the dev-training
service account, editor on the regional projects in nebius-projects.json).
`grad-ctl compute setup` creates the account and writes its keys to gradiated/dev/env.
"""

from concurrent.futures import ThreadPoolExecutor
from importlib import resources
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

# Read as package data so the single-file grad-ctl build carries it.
CONFIG = json.loads(resources.files(__package__).joinpath('nebius-projects.json').read_text())
PROJECTS = CONFIG['projects']


class Nebius:
    name = 'nebius'
    ssh_user = 'ubuntu'
    default_region = 'eu-north1'
    virtualization = 'vm'
    # Recognizes this provider's --platform names, so `up` can find the provider.
    platform_pattern = '(gpu|cpu)-'
    cloud_init = True
    # A preempted VM stops and can start again with the same tailnet identity.
    ephemeral = False
    can_stop = True

    def __init__(self, secret, state):
        self.secret, self.state = secret, state

    def cli(self, *args, missing_ok=False, unpriced_ok=False):
        binary = shutil.which('nebius') or str(Path.home() / '.nebius/bin/nebius')
        if not Path(binary).exists():
            sys.exit('Install the nebius CLI: curl -sSL https://storage.eu-north1.nebius.cloud/cli/install.sh | bash')
        config = self.state / 'nebius.yaml'
        credentials = self.state / 'nebius-service-account.json'
        current = self.secret('NEBIUS_SERVICE_ACCOUNT_CREDENTIALS_B64')
        # Rebuild the profile after `grad-ctl compute setup` rotates the key; the old one is revoked.
        if not config.exists() or not credentials.exists() or credentials.read_text() != current:
            config.unlink(missing_ok=True)
            credentials.touch(mode=0o600)
            credentials.write_text(current)
            subprocess.run([binary, '-c', str(config), 'profile', 'create', 'dev-training', '--endpoint',
                            'api.nebius.cloud', '--service-account-file', str(credentials),
                            '--parent-id', PROJECTS[self.default_region]],
                           check=True, stdout=subprocess.DEVNULL, timeout=60)
        try:
            result = subprocess.run([binary, '-c', str(config), *args, '--format', 'json'], text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=600)
        except subprocess.TimeoutExpired:
            sys.exit(f"nebius {' '.join(args[:3])} did not answer within 10 minutes")
        if result.returncode:
            # Only a NotFound answer means absent; any other failure must stop the caller.
            if missing_ok and 'code = NotFound' in result.stderr:
                return None
            # The calculator has no SKU for shapes Nebius does not sell on that term.
            if unpriced_ok and 'unresolved sku' in result.stderr:
                return None
            sys.exit(result.stderr.strip())
        return json.loads(result.stdout) if result.stdout.strip() else {}

    def regions(self):
        return sorted(PROJECTS)

    def project(self, region):
        if region not in PROJECTS:
            sys.exit(f'Unknown Nebius region {region}; choose from {", ".join(self.regions())}')
        return PROJECTS[region]

    def gpu_platforms(self, region):
        return [p for p in self.items('compute', 'platform', 'list', '--parent-id', self.project(region))
                if p['metadata']['name'].startswith('gpu')]

    def platforms(self, region):
        for platform in self.gpu_platforms(region):
            yield f"{platform['metadata']['name']}: {', '.join(p['name'] for p in platform['spec'].get('presets', []))}"

    def estimate(self, region, platform, preset, term):
        """Hourly price of one VM from the Nebius calculator, in USD, or None if it is not sold."""
        result = self.cli('billing', 'v1alpha1', 'calculator', 'estimate',
                          '--resource-spec-compute-instance-spec-parent-id', self.project(region),
                          '--resource-spec-compute-instance-spec-resources-platform', platform,
                          '--resource-spec-compute-instance-spec-resources-preset', preset,
                          *(['--resource-spec-compute-instance-spec-preemptible-on-preemption=stop']
                            if term == 'spot' else []), unpriced_ok=True)
        return float(result['hourly_cost']['general']['total']['cost']) if result else None

    def spot_prices(self):
        """The live market spot price per GPU-hour by region and platform; it includes the preset's CPU and memory."""
        return {(i['region'], i['compute_instance']['platform']): float(i['price']['value'])
                for i in self.cli('billing', 'v1alpha1', 'spot-price', 'list').get('items', [])}

    def hourly_price(self, region, platform, preset, term):
        """What a VM costs per hour now: the market spot price where one exists, else the calculator."""
        gpus = int(preset.split('gpu')[0])
        market = self.spot_prices().get((region, platform)) if term == 'spot' else None
        return market * gpus if market is not None else self.estimate(region, platform, preset, term)

    def capacity(self):
        """VMs of each region, platform and preset the tenant can launch now, by term, within its quotas.

        Nebius reports this per fabric and leaves out the count when it is zero.
        A shape it does not report is unknown (None).
        """
        found = {}
        for item in self.items('capacity', 'resource-advice', 'list', '--parent-id', CONFIG['tenant_id']):
            instance = item['spec'].get('compute_instance')
            if not instance:
                continue
            key = (item['spec']['region'], instance['platform'], instance['preset']['name'])
            for term, field in (('spot', 'preemptible'), ('on-demand', 'on_demand')):
                status = item.get('status', {}).get(field, {})
                if status.get('data_state', 'DATA_STATE_FRESH') == 'DATA_STATE_FRESH':
                    found[key + (term,)] = found.get(key + (term,), 0) + int(status.get('available', 0))
        return found

    def offers(self, term):
        """One offer per region, GPU platform and GPU count, using the smallest preset for that count.

        Spot prices follow the market per region (the published spot price per
        GPU-hour, which includes the preset's CPU and memory); on-demand prices
        and the spot prices of platforms without a market price are the same in
        every region, so the calculator prices each preset once.
        """
        self.cli('iam', 'whoami')  # Build the profile once before the parallel calls.
        with ThreadPoolExecutor(8) as pool:
            catalog = dict(zip(PROJECTS, pool.map(self.gpu_platforms, PROJECTS)))
        available = self.capacity()
        spot = self.spot_prices()
        shapes = {}
        for region, platforms in catalog.items():
            for platform in platforms:
                smallest = {}
                for preset in platform['spec'].get('presets', []):
                    gpus = preset['resources'].get('gpu_count', 0)
                    if gpus and gpus not in smallest:
                        smallest[gpus] = preset['name']
                for gpus, preset in smallest.items():
                    shapes[(region, platform['metadata']['name'], preset)] = gpus
        terms = ['spot', 'on-demand'] if term is None else [term]
        fixed = sorted({(platform, preset, t) for (region, platform, preset) in shapes for t in terms
                        if t == 'on-demand' or (region, platform) not in spot})
        anywhere = {(platform, preset): region for (region, platform, preset) in shapes}
        with ThreadPoolExecutor(8) as pool:
            prices = dict(zip(fixed, pool.map(lambda k: self.estimate(anywhere[k[:2]], *k), fixed)))
        offers = []
        for (region, platform, preset), gpus in sorted(shapes.items()):
            for t in terms:
                hour = spot[(region, platform)] * gpus if t == 'spot' and (region, platform) in spot \
                    else prices[(platform, preset, t)]
                # No SKU, or a zero price for shapes sold only by contract.
                if not hour:
                    continue
                offers.append({'gpu': platform, 'region': region, 'term': t, 'gpus': gpus, 'gpu_hour': hour / gpus,
                               'hour': hour, 'available': available.get((region, platform, preset, t)),
                               'up': f'--provider nebius --platform {platform} --preset {preset} --region {region}'})
        return offers

    @staticmethod
    def vm(region, instance):
        address = next((i['public_ip_address']['address'].split('/')[0]
                        for i in instance.get('status', {}).get('network_interfaces', [])
                        if i.get('public_ip_address', {}).get('address')), None)
        resources = instance['spec']['resources']
        return {'name': instance['metadata']['name'], 'id': instance['metadata']['id'], 'region': region,
                'state': instance.get('status', {}).get('state', ''), 'address': address, 'port': 22,
                'user': Nebius.ssh_user,
                'machines': [{'address': address, 'port': 22, 'user': Nebius.ssh_user}] if address else [],
                'term': 'spot' if instance['spec'].get('preemptible') else 'on-demand',
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

    def create(self, name, region, platform, preset, disk_gib, image, user_data, term='spot', max_price=None):
        if not preset:
            sys.exit('Nebius needs --preset; see `platforms`')
        parent = self.project(region)
        if max_price is not None:
            # The same price `search` shows. A spot VM follows the market afterwards.
            price = self.hourly_price(region, platform, preset, term)
            if price is None:
                sys.exit(f'Nebius does not sell {platform} {preset} as {term}')
            gpus = int(preset.split('gpu')[0])
            if price / gpus > max_price:
                sys.exit(f'${price / gpus:.2f}/GPU-hour is above --max-price ${max_price:.2f}; nothing created')
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
                        'size_bytes': str((disk_gib or 250) * 1024 ** 3), 'type': 'NETWORK_SSD',
                        'source_image_family': {'image_family': image or 'ubuntu24.04-cuda13.0'}}}},
                # Built only now, after the price check, because it mints a tailnet key.
                'cloud_init_user_data': user_data(),
            },
        }
        if term == 'spot':
            spec['spec'].update({
                # Preemption stops the VM; pricing defaults to on-demand, so ask for spot.
                'preemptible': {'on_preemption': 'STOP'},
                # Nebius accepts only FAIL for preemptible VMs.
                'recovery_policy': 'FAIL',
                'follows_spot_price': {},
            })
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
