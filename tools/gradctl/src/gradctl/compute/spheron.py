"""Spheron GPU VMs (spot or dedicated) for `gradctl compute`.

Credentials come from SPHERON_API_KEY, a GPU VM API key of the Gradiated Spheron
account, and SPHERON_SSH_*_KEY_B64, an SSH key used only for Spheron VMs.
`gradctl compute setup spheron` writes them to gradiated/dev/env.

Spheron resells capacity from several clouds (Spheron AI, ES, MS and AM, Verda,
which the API calls data-crunch, and Massed Compute) behind one API. An offer is
one machine shape from one of them in one region, so `up` takes the GPU type as
its platform (upper case, such as H100_SXM5) and the offer ID as its preset;
`search` prints both. Offers are priced per instance per hour. Every deployment
gets our public key inline, never a key saved on the account, and never the
Agent GPU Sandbox (`agentAccess`), which would let anyone holding the API key
run commands on the VM through Spheron. Spheron passes cloud-init to only some
offers, so `gradctl compute` joins every VM to the tailnet over SSH instead and
the join key never reaches Spheron's API.

Spheron refuses to terminate a deployment that is still deploying or that has
run less than its minimum runtime (20 minutes by default, and charged in full
either way), so `down` waits until it can.
"""

import json
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://app.spheron.ai'
TERMS = {'spot': 'SPOT', 'on-demand': 'DEDICATED'}
STATES = {'deploying': 'STARTING', 'running': 'RUNNING', 'stopped': 'STOPPED'}
GONE = ('terminated', 'terminated-provider', 'failed')


class Spheron:
    name = 'spheron'
    ssh_user = 'root'
    default_region = None
    virtualization = 'vm'
    # Spheron GPU types are upper case (H100_SXM5); Nebius and Ornn platforms are lower case.
    platform_pattern = '[A-Z][A-Z0-9_]*$'
    cloud_init = False
    # Some Spheron VMs stop and start again on the same disk, keeping their tailnet identity.
    ephemeral = False
    can_stop = True

    def __init__(self, secret, state):
        self.secret, self.state = secret, state

    def api(self, method, path, params=None, body=None, missing_ok=False):
        url = API + path + ('?' + urllib.parse.urlencode(params) if params else '')
        request = urllib.request.Request(url, method=method,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={'Authorization': 'Bearer ' + self.secret('SPHERON_API_KEY'),
                                                  'Content-Type': 'application/json',
                                                  'User-Agent': 'gradiated-dev-training'})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    content = response.read()
                return json.loads(content) if content else {}
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors='replace')
                if error.code == 404 and missing_ok:
                    return None
                # A 429 was refused before anything happened, so any call may repeat it. Spheron has no
                # idempotency key, so only reads repeat after a server error: a repeated create could buy twice.
                if attempt < 4 and (error.code == 429 or (method == 'GET' and error.code in (500, 502, 503, 504))):
                    wait = error.headers.get('Retry-After') or error.headers.get('RateLimit-Reset') or 2 ** attempt
                    time.sleep(min(int(float(wait)), 60))
                    continue
                try:
                    found = json.loads(detail)
                    detail = f"{found.get('code')}: {found.get('error')}"
                except (ValueError, AttributeError):
                    detail = detail[:500]
                sys.exit(f'Spheron {method} {path}: HTTP {error.code} {detail}')
            except (urllib.error.URLError, OSError) as error:
                # Connection failures before a response: nothing reached Spheron for a refused connection,
                # but a timeout may have, so only reads repeat.
                if attempt < 4 and method == 'GET':
                    time.sleep(2 ** attempt)
                    continue
                sys.exit(f'Spheron {method} {path}: {error}')
        raise AssertionError('unreachable')

    def catalog(self, term=None):
        """Every GPU VM offer as (GPU type, offer), across every page."""
        page = 1
        while True:
            params = {'computeType': 'gpu', 'limit': 100, 'page': page,
                      **({'instanceType': TERMS[term]} if term else {})}
            found = self.api('GET', '/api/gpu-offers', params)
            for group in found.get('data', []):
                for offer in group.get('offers', []):
                    if (offer.get('instanceType') in TERMS.values() and offer.get('gpuCount', 0) >= 1
                            and group.get('gpuType') != 'CPU' and offer.get('provider') != 'spheron-con'):
                        yield group['gpuType'], offer
            if page >= (found.get('totalPages') or 1):
                return
            page += 1

    @staticmethod
    def price(offer):
        """USD per hour for the whole instance, after our account's discount."""
        return offer['discountedPrice'] if offer.get('hasDiscount') and offer.get('discountedPrice') else offer['price']

    @staticmethod
    def term(instance_type):
        return 'spot' if instance_type == 'SPOT' else 'on-demand'

    def regions(self):
        return sorted({f"{offer['provider']}/{cluster}" for _, offer in self.catalog()
                       for cluster in offer.get('clusters') or []})

    def platforms(self, region):
        found = {}
        for gpu, offer in self.catalog():
            for cluster in offer.get('clusters') or []:
                where = f"{offer['provider']}/{cluster}"
                if region is None or region.lower() in where.lower():
                    found.setdefault(gpu, set()).add(f"{offer['gpuCount']}x {self.term(offer['instanceType'])} {where}")
        for gpu, where in sorted(found.items()):
            yield f"{gpu}: {', '.join(sorted(where))} (see `search` for offer IDs)"

    def offers(self, term):
        offers = []
        for gpu, offer in self.catalog(term):
            gpus, price = offer['gpuCount'], self.price(offer)
            units = ((offer.get('extras') or {}).get('technical') or {}).get('units_available')
            available = 0 if not offer.get('available') or offer.get('maintenance') else units
            deployment = (offer.get('extras') or {}).get('deployment_type') or 'vm'
            for cluster in offer.get('clusters') or []:
                offers.append({
                    'gpu': gpu, 'region': f"{offer['provider']}/{cluster}", 'term': self.term(offer['instanceType']),
                    'gpus': gpus, 'gpu_hour': price / gpus, 'hour': price, 'available': available,
                    'virtualization': 'bare-metal' if 'BAREMETAL' in gpu or 'metal' in deployment else 'vm',
                    'seller': offer['provider'], 'offer_id': offer['offerId'],
                    'up': f"--provider spheron --platform {gpu} --preset {shlex.quote(offer['offerId'])} "
                          f"--region {shlex.quote(cluster)}"})
        return offers

    @staticmethod
    def default_os(options):
        # Prefer Ubuntu with CUDA, 24.04 then 22.04; the first of equals keeps Spheron's order.
        def rank(option):
            text = option.lower()
            return ('ubuntu' in text, 'cuda' in text, '24.04' in text, '22.04' in text, 'kubernetes' not in text)
        return max(options, key=rank) if options else None

    def deployments(self):
        found = self.api('GET', '/api/deployments', {'status': 'active'})
        if isinstance(found, dict):
            found = found.get('deployments') or found.get('data') or []
        return [d for d in found if d.get('status') not in GONE]

    def vm(self, deployment):
        status = deployment.get('status') or 'unknown'
        address = deployment.get('ipAddress') if status == 'running' else None
        command = shlex.split(deployment.get('sshCommand') or '')
        login = next((part.split('@')[0] for part in command if '@' in part), None)
        user = deployment.get('user') or login or self.ssh_user
        port = int(deployment.get('sshPort') or 22)
        gpus, rate = deployment.get('gpuCount'), deployment.get('hourlyRate')
        seller = deployment.get('providerId') or deployment.get('provider') or '-'
        return {'name': deployment.get('name') or deployment['id'], 'id': deployment['id'],
                'region': f"{seller}/{deployment.get('region')}", 'state': STATES.get(status, status.upper()),
                'address': address, 'port': port, 'user': user,
                'machines': [{'address': address, 'port': port, 'user': user, 'gpus': gpus}] if address else [],
                'term': self.term(deployment.get('instanceType')), 'gpu_type': deployment.get('gpuType'),
                'gpus': gpus, 'usd_per_gpu_hour': rate / gpus if rate is not None and gpus else None,
                'created_at': deployment.get('startedAt') or deployment.get('createdAt'),
                'supports_pause': deployment.get('supportsPause'),
                'pause_unsupported_reason': deployment.get('pauseUnsupportedReason'),
                'shape': f"{gpus}x{deployment.get('gpuType')} {seller}"
                         + (f' ${rate:.2f}/hr' if rate is not None else '')}

    def find(self, name):
        matches = [d for d in self.deployments() if name in (d.get('name'), d.get('id'))]
        if len(matches) > 1:
            sys.exit(f"{len(matches)} Spheron deployments are named {name}; pass a deployment ID: "
                     + ', '.join(d['id'] for d in matches))
        return self.vm(matches[0]) if matches else None

    def list(self):
        for deployment in self.deployments():
            yield self.vm(deployment)

    def create(self, name, region, platform, preset, disk_gib, image, user_data, term='spot', max_price=None):
        if disk_gib:
            print('Spheron offers come with a fixed disk; ignoring --disk-gib', file=sys.stderr)
        if region and '/' in region:
            region = region.split('/', 1)[1]  # `ls` and `search` show regions as <seller>/<cluster>
        candidates = []
        for gpu, offer in self.catalog(term):
            if gpu != platform or (preset and offer['offerId'] != preset) or not offer.get('available') \
                    or offer.get('maintenance'):
                continue
            for cluster in offer.get('clusters') or []:
                if not region or region == cluster or (not preset and region.lower() in cluster.lower()):
                    candidates.append((self.price(offer) / offer['gpuCount'], cluster, offer))
        if not candidates:
            sys.exit(f"Spheron has no available {term} {platform} offer"
                     f"{' ' + preset if preset else ''}{' in ' + region if region else ''}; see `search`")
        gpu_hour, cluster, offer = min(candidates, key=lambda c: c[0])
        operating_system = image or self.default_os(offer.get('os_options') or [])
        if image and image not in (offer.get('os_options') or []):
            sys.exit(f"{image} is not an image of offer {offer['offerId']}; choose from "
                     + ', '.join(offer.get('os_options') or []))
        print(f"Best offer: {offer['offerId']} from {offer['provider']} in {cluster}: {offer['gpuCount']}x {platform} "
              f"at ${gpu_hour:.2f}/GPU-hour (${self.price(offer):.2f}/hour), {operating_system}; at least "
              f"{offer.get('minimumRuntimeMinutes') or 20} minutes are billed", file=sys.stderr)
        if max_price is not None and gpu_hour > max_price:
            sys.exit(f'${gpu_hour:.2f}/GPU-hour is above --max-price ${max_price:.2f}; nothing bought')
        public_key = self.secret('SPHERON_SSH_PUBLIC_KEY_B64').strip()
        body = {'provider': offer['provider'], 'offerId': offer['offerId'], 'gpuType': platform,
                'gpuCount': offer['gpuCount'], 'region': cluster, 'operatingSystem': operating_system,
                'instanceType': offer['instanceType'], 'name': name, 'ssh_public_key': public_key,
                # Never the Agent GPU Sandbox: it runs commands on the VM for anyone holding the API key.
                'agentAccess': False}
        deployment = self.api('POST', '/api/deployments', body=body)
        return deployment['id']

    def start(self, vm):
        self.api('POST', f"/api/deployments/{vm['id']}/resume")

    def stop(self, vm):
        if vm.get('supports_pause') is False:
            sys.exit(f"Spheron cannot stop {vm['name']}: {vm.get('pause_unsupported_reason') or 'not supported'}; "
                     'use `down`')
        self.api('POST', f"/api/deployments/{vm['id']}/pause")

    def delete(self, vm, wait_minutes=45):
        path = f"/api/deployments/{vm['id']}"
        deadline = time.time() + wait_minutes * 60
        while True:
            deployment = self.api('GET', path, missing_ok=True)
            if deployment is None or deployment.get('status') in GONE:
                return
            check = self.api('GET', f'{path}/can-terminate')
            if check.get('canTerminate'):
                break
            if time.time() > deadline:
                sys.exit(f"Spheron will not terminate {vm['name']} yet ({check.get('reason')}); run `down` again")
            remaining = check.get('timeRemaining')
            print(f"Spheron cannot terminate {vm['name']} yet ({check.get('reason') or 'minimum runtime'}"
                  + (f', {remaining} minutes left of its {check.get("minimumRuntime")}-minute minimum'
                     if remaining else '') + '); waiting', file=sys.stderr, flush=True)
            time.sleep(min(max(float(remaining or 0) * 60, 15), 120))
        self.api('DELETE', path)
