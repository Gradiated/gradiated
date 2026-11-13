"""Ornn hourly VMs (Spot and On-demand) for `gradctl compute`.

Credentials come from ORNN_API_KEY, a read and write key of the Gradiated Ornn
organization, and ORNN_SSH_*_KEY_B64, an SSH key used only for Ornn VMs and
registered as the organization's account key, which Ornn installs on every VM
it starts. `gradctl compute setup ornn` writes them to gradiated/dev/env.

Ornn sells whole machines from an order book: `up` buys one node at the lowest
asking price with a market bid, so its platform is a GPU slug such as
nvidia_h100_sxm and it has no preset. The bid becomes a reservation; ending it
(`down`) stops and deletes its VMs. Ornn cannot stop and restart a VM, and
reservations have no names, so this machine records which reservation each name
bought; a reservation bought elsewhere shows by its ID, which every command
also accepts. Ornn VMs have no cloud-init input: `gradctl compute` joins them to
the tailnet over SSH once they run.
"""

import fcntl
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = 'https://api.ornn.com'
LIVE = ('confirmed', 'active')


class Ornn:
    name = 'ornn'
    ssh_user = 'ubuntu'
    default_region = None
    virtualization = 'vm'
    # Recognizes this provider's --platform names, so `up` can find the provider.
    platform_pattern = '(nvidia|amd)_|cpu$'
    cloud_init = False
    # A stopped Ornn VM never comes back, so its tailnet device should leave by itself.
    ephemeral = True
    can_stop = False

    def __init__(self, secret, state):
        self.secret, self.state = secret, state

    @property
    def names_file(self):
        return self.state / 'ornn-names.json'

    def api(self, method, path, params=None, body=None, headers=None, missing_ok=False):
        url = API + path + ('?' + urllib.parse.urlencode(params, doseq=True) if params else '')
        request = urllib.request.Request(url, method=method,
                                         data=None if body is None else json.dumps(body).encode(),
                                         headers={'Authorization': 'Bearer ' + self.secret('ORNN_API_KEY'),
                                                  'Content-Type': 'application/json',
                                                  'User-Agent': 'gradiated-dev-training',
                                                  **(headers or {})})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    content = response.read()
                return json.loads(content) if content else {}
            except urllib.error.HTTPError as error:
                detail = error.read().decode(errors='replace')
                if error.code == 404 and missing_ok:
                    return None
                if error.code in (429, 502, 503, 504) and attempt < 4 and 'session_contract_unavailable' not in detail:
                    time.sleep(min(int(error.headers.get('Retry-After') or 2 ** attempt), 60))
                    continue
                sys.exit(f'Ornn {method} {path}: HTTP {error.code} {detail[:500]}')
            except (urllib.error.URLError, OSError) as error:
                # DNS, connection and timeout failures: retry, then fail like any provider error.
                if attempt < 4:
                    time.sleep(2 ** attempt)
                    continue
                sys.exit(f'Ornn {method} {path}: {error}')
        raise AssertionError('unreachable')

    def regions(self):
        return sorted({b['region'] for b in self.books() if b['region'] != 'any'})

    def books(self, term=None):
        return self.api('GET', '/v1/markets/books', {'saleType': term} if term else None)['orderBooks']

    def platforms(self, region):
        # Ornn's platforms are GPU slugs; one node is one whole machine.
        found = {}
        for book in self.books():
            if book['bestAskPricePerGpuHourMicroUsd'] and book['region'] != 'any' \
                    and (region is None or book['region'] == region):
                found.setdefault(book['gpuSlug'], set()).add(f"{book['saleType']} {book['region']}")
        for slug, where in sorted(found.items()):
            yield f"{slug}: {', '.join(sorted(where))} (one whole node; see `search`)"

    def offers(self, term):
        """Every book with capacity for sale, one entry per ask price level."""
        offers = []
        for book in self.books(term):
            if book['region'] == 'any' or not book['bestAskPricePerGpuHourMicroUsd'] or book['gpuSlug'] == 'cpu':
                continue
            depth = self.api('GET', f"/v1/markets/books/{book['gpuSlug']}",
                             {'saleType': book['saleType'], 'region': book['region']})
            for ask in depth['asks']:
                if not ask['nodes']:
                    continue
                gpus = ask['gpus'] // ask['nodes']
                price = ask['pricePerGpuHourMicroUsd'] / 1e6
                offers.append({'gpu': book['gpuSlug'], 'region': book['region'], 'term': book['saleType'],
                               'gpus': gpus, 'gpu_hour': price, 'hour': price * gpus, 'available': ask['nodes'],
                               'up': f"--provider ornn --platform {book['gpuSlug']} --region {book['region']}"})
        return offers

    def names(self):
        try:
            return json.loads(self.names_file.read_text())
        except FileNotFoundError:
            return {}

    def remember(self, name, reservation_id):
        # Concurrent `up` and `down` runs on this machine must not lose each other's names.
        with open(self.state / 'ornn-names.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            names = {k: v for k, v in self.names().items() if v != reservation_id}
            if name:
                names[name] = reservation_id
            with tempfile.NamedTemporaryFile('w', dir=self.state, delete=False) as replacement:
                json.dump(names, replacement, indent=1, sort_keys=True)
            os.replace(replacement.name, self.names_file)

    def reservations(self, **params):
        cursor = None
        while True:
            page = self.api('GET', '/commerce/reservations', {**params, **({'cursor': cursor} if cursor else {})})
            yield from page['reservations']
            cursor = page.get('nextCursor')
            if not cursor:
                return

    def vm(self, reservation, name):
        vms = self.api('GET', f"/v1/orchestrator/reservations/{reservation['reservationId']}/virtual-machines",
                       missing_ok=True) or {'virtual_machines': []}
        # A node whose GPUs split only in powers of two runs as several VMs (6 GPUs as 4 and 2);
        # each is a machine of this one reservation, oldest first.
        statuses = [m['status'] for m in vms['virtual_machines']]
        machines = [{'address': m.get('ip'), 'port': m.get('port') or 22, 'gpus': m.get('gpu_count'),
                     'user': m.get('tenant_username') or self.ssh_user}
                    for m in vms['virtual_machines'] if m['status'] == 'running' and m.get('ip')]
        if reservation['status'] not in LIVE:
            state = reservation['status'].upper()
        elif 'failed' in statuses:
            state = 'ERROR'
        elif statuses and len(machines) == len(statuses):
            state = 'RUNNING'
        else:
            state = 'STARTING'
        first = machines[0] if machines else {'address': None, 'port': 22, 'user': self.ssh_user}
        return {'name': name, 'id': reservation['reservationId'], 'region': reservation.get('facilityId') or '-',
                'state': state, 'address': first['address'], 'port': first['port'], 'user': first['user'],
                'machines': machines, 'term': reservation.get('kind') or '-',
                'shape': f"{reservation.get('gpuSlug')}/{reservation.get('reservedGpuCount')}gpu"
                         + (f" as {len(statuses)} VMs" if len(statuses) > 1 else '')
                         + f" ${reservation.get('pricePerGpuHourMicroUsd', 0) / 1e6:.2f}/gpu-hr"}

    def find(self, name):
        reservation_id = self.names().get(name, name)
        try:
            uuid.UUID(reservation_id)
        except ValueError:
            return None
        reservation = self.api('GET', f'/commerce/reservations/{reservation_id}', missing_ok=True)
        if not reservation or reservation['status'] not in LIVE:
            return None
        return self.vm(reservation, name)

    def list(self):
        names = {v: k for k, v in self.names().items()}
        for status in LIVE:
            for reservation in self.reservations(status=status):
                if reservation.get('kind') in ('spot', 'on-demand'):
                    yield self.vm(reservation, names.get(reservation['reservationId'], reservation['reservationId']))

    def create(self, name, region, platform, preset, disk_gib, image, user_data, term='spot', max_price=None):
        if preset or disk_gib:
            print('Ornn sells whole nodes with their own disk; ignoring --preset and --disk-gib')
        params = {'nodes': 1, 'orderType': 'market', 'saleType': term, **({'region': region} if region else {})}
        quote = self.api('GET', f'/v1/markets/books/{platform}/quote', params)['nodes']
        if not quote:
            sys.exit(f'Ornn has no {term} {platform} node for sale{" in " + region if region else ""}; see `search`')
        line = quote[0]
        price = line['pricePerGpuHourMicroUsd'] / 1e6
        print(f"Best offer: 1 {term} {platform} node ({line['gpusPerNode']} GPUs) in {line['region']} at "
              f"${price:.2f}/GPU-hour (${price * line['gpusPerNode']:.2f}/hour, prepaid hourly)"
              + (f"; next scheduled interruption {line['interruptsAt']}" if line.get('interruptsAt') else ''))
        if max_price is not None and price > max_price:
            sys.exit(f'${price:.2f}/GPU-hour is above --max-price ${max_price:.2f}; nothing bought')
        print('Buying it')
        # Pin the bid to the quoted line so a moving book cannot fill at a higher price.
        body = {'gpuSlug': platform, 'saleType': term, 'orderType': 'market', 'nodes': 1,
                'nodeSelections': [{'region': line['region'], 'gpusPerNode': line['gpusPerNode'],
                                    'pricePerGpuHourMicroUsd': line['pricePerGpuHourMicroUsd'], 'nodes': 1}],
                **({'diskId': image} if image else {})}
        order = self.api('POST', '/v1/markets/orders', body=body,
                         headers={'Idempotency-Key': str(uuid.uuid4())})['order']
        if not order.get('fillIds'):
            sys.exit(f"Ornn bid {order['orderId']} bought nothing ({order.get('cancelReason') or order['status']}); "
                     'the node sold first. Try again or pick another offer from `search`')
        self.remember(name, order['fillIds'][0])
        return order['fillIds'][0]

    def start(self, vm):
        sys.exit('Ornn cannot restart a VM; create another with `up` and `down` this one')

    def stop(self, vm):
        sys.exit('Ornn cannot stop a VM without deleting it; use `down`')

    def delete(self, vm):
        self.api('DELETE', f"/commerce/reservations/{vm['id']}")
        self.remember(None, vm['id'])
