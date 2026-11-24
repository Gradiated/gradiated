"""SF Compute: bounded orders into a dedicated pool, then cloud-init VMs.

API contract: https://docs.sfcompute.com/api-reference/instances/create-instance
Deleting a VM does not refund the pool's purchased time. Never retry mutations:
an ambiguous response must be reconciled in the provider console before buying again.
"""

import base64
from contextlib import nullcontext
import fcntl
import hashlib
import json
import math
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from decimal import Decimal, ROUND_DOWN
from datetime import datetime, timezone


class SFCompute:
    name = 'sfcompute'
    secret_prefix = 'SF_COMPUTE'
    ssh_user = 'root'
    default_region = None
    virtualization = 'vm'
    platform_pattern = 'sku_'
    cloud_init = True
    ephemeral = True
    can_stop = False
    # SF Compute rejects callable orders above 1.2, and bases it on the buy limit, not the fill.
    preemption_multiple = '1.2'

    def __init__(self, secret, state):
        self.secret, self.state = secret, state
        self.duration_hours = 1.0

    def api(self, method, path, params=None, body=None, missing_ok=False, headers=None):
        url = 'https://api.sfcompute.com' + path
        if params:
            url += '?' + urllib.parse.urlencode(params, doseq=True)
        request = urllib.request.Request(url, method=method,
                                        data=None if body is None else json.dumps(body).encode(),
                                        headers={'Authorization': 'Bearer ' + self.secret('SF_COMPUTE_API_TOKEN'),
                                                 'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                data = response.read()
            return json.loads(data) if data else {}
        except urllib.error.HTTPError as error:
            if error.code == 404 and missing_ok:
                return None
            # Do not echo arbitrary provider bodies, which can include cloud-init secrets.
            sys.exit(f'SF Compute {method} {path}: HTTP {error.code}; inspect the provider console before retrying')
        except (urllib.error.URLError, OSError, ValueError) as error:
            sys.exit(f'SF Compute {method} {path}: {type(error).__name__}; response unconfirmed, '
                     'inspect the provider console before retrying')

    def pages(self, path, **params):
        while True:
            page = self.api('GET', path, params)
            yield from page['data']
            if not page['has_more']:
                return
            if not page.get('cursor') or page['cursor'] == params.get('starting_after'):
                sys.exit('SF Compute pagination did not advance')
            params['starting_after'] = page['cursor']

    def skus(self):
        return list(self.pages('/v2/skus'))

    @staticmethod
    def value(sku, field, default=None):
        return (sku.get(field) or {}).get('value', default)

    def regions(self):
        return sorted({self.value(s, 'region', '-') for s in self.skus()})

    def platforms(self, region):
        for s in self.skus():
            if region is None or self.value(s, 'region') == region:
                yield f"{s['id']}: {s['alias']} {self.value(s, 'accelerator')} {self.value(s, 'num_accelerators')} GPUs"

    def window(self, start=None, hours=None):
        hours = self.duration_hours if hours is None else hours
        if not math.isfinite(hours) or hours <= 0:
            sys.exit('SF Compute --duration-hours must be finite and positive')
        start = int(time.time()) // 60 * 60 if start is None else start
        grid = self.api('GET', '/preview/v2/platform_constants')['allocation_schedule_grid']['time_grid']
        ends = [t for t in grid if start < t <= start + hours * 3600]
        if not ends:
            sys.exit('No SF Compute schedule boundary within --duration-hours; choose a longer duration')
        return start, max(ends)

    def quote(self, sku, start, end):
        result = self.api('GET', '/preview/v2/orderbook/quote',
                          {'requirements': 'instance_sku:' + sku, 'start_at': start, 'end_at': end})
        ask = result.get('best_ask')
        if ask and ask['instance_sku'] != sku:
            sys.exit('SF Compute quote returned a different SKU')
        return ask

    def offers(self, term):
        start, end = self.window()
        offers = []
        for s in self.skus():
            gpus = self.value(s, 'num_accelerators', 0)
            if s.get('deleted_at') or not gpus:
                continue
            ask = self.quote(s['id'], start, end)
            if not ask:
                continue
            price = float(ask['dollars_per_node_hour'])
            # Top of book is a quote, not proof a whole node is available for this entire window.
            for kind in [term] if term else ['spot', 'on-demand']:
                offers.append({'gpu': self.value(s, 'accelerator') + '/' + s['id'],
                               'region': self.value(s, 'region', '-'), 'term': kind, 'gpus': gpus,
                               'gpu_hour': price / gpus, 'hour': price, 'available': None,
                               'up': f"--provider sfcompute --platform {shlex.quote(s['id'])}"})
        return offers

    def raw_instances(self):
        return self.pages('/v2/instances', workspace=self.secret('SF_COMPUTE_WORKSPACE'))

    def vm(self, instance):
        sku = next((s for s in self.skus() if s['id'] == instance['sku']['id']), {})
        ssh = (self.api('GET', f"/v2/instances/{instance['id']}/ssh", missing_ok=True)
               if instance['state'] == 'running' else None)
        tags = instance.get('tags') or {}
        rate = None
        price_schedule = None
        if tags.get('gradctl-order'):
            orders = self.pages('/v2/orders', pool=instance['pool']['id'], side='buy')
            weighted, seconds = Decimal(0), 0
            price_schedule = []
            fills = [fill for order in orders if order['sku']['id'] == instance['sku']['id']
                     for fill in order.get('fills') or []]
            for fill in fills:
                for span in fill['allocation_schedule_delta']:
                    if span.get('end_at') is not None and span['node_count'] > 0:
                        length = (span['end_at'] - span['start_at']) * span['node_count']
                        price_schedule.append({**span, 'node_hour': fill['price_dollars_per_node_hour']})
                        weighted += Decimal(fill['price_dollars_per_node_hour']) * length
                        seconds += length
            gpus = self.value(sku, 'num_accelerators', 0)
            if seconds and gpus:
                rate = float(weighted / seconds / gpus)
        ended = None
        if instance['state'] in ('terminated', 'failed'):
            # Expiry is bounded by purchased allocation. An earlier termination/fault is observed
            # at the provider's update timestamp; later edits cannot move it beyond allocation end.
            bounds = [span['end_at'] for span in price_schedule or []]
            if bounds:
                ended = max(bounds)
                if instance.get('_preview_updated_at'):
                    ended = min(ended, instance['_preview_updated_at'])
        address, port = (ssh['hostname'], ssh['port']) if ssh else (None, 22)
        return {'id': instance['id'], 'name': instance['name'], 'region': self.value(sku, 'region', '-'),
                'state': {'running': 'RUNNING', 'failed': 'ERROR', 'terminated': 'COMPLETED'}.get(
                    instance['state'], 'STARTING'), 'address': address, 'port': port, 'user': self.ssh_user,
                'machines': [{'address': address, 'port': port, 'user': self.ssh_user}] if address else [],
                'term': tags.get('gradctl-term', 'reserved'), 'gpu_type': self.value(sku, 'accelerator'),
                'gpus': self.value(sku, 'num_accelerators'),
                'billing_ended_at': ended,
                'price_schedule': price_schedule,
                'usd_per_gpu_hour': rate,  # Actual fills, never the order's limit price.
                'created_at': datetime.fromtimestamp(instance['created_at'], timezone.utc).isoformat(),
                'shape': instance['sku'].get('alias', instance['sku']['id']),
                'pool': (instance.get('pool') or {}).get('id')}

    def usage_price(self, vm, start, end):
        """Actual node-hour rate weighted only over the metered interval, across purchase/extension fills."""
        if not vm.get('price_schedule'):
            return None
        seconds = Decimal(str((end - start).total_seconds()))
        if seconds <= 0:
            return None
        cost_seconds = Decimal(0)
        for span in vm['price_schedule']:
            overlap = max(0, min(end.timestamp(), span['end_at']) - max(start.timestamp(), span['start_at']))
            cost_seconds += Decimal(span['node_hour']) * span['node_count'] * Decimal(str(overlap))
        return float(cost_seconds / seconds)

    def find(self, name):
        found = [i for i in self.raw_instances() if name in (i['name'], i['id'])]
        if len(found) > 1:
            sys.exit(f'Multiple SF Compute instances named {name}; use the instance ID')
        return self.vm(found[0]) if found else None

    def list(self):
        for i in self.raw_instances():
            yield self.vm(i)

    def create(self, name, region, platform, preset, disk_gib, image, user_data, term='spot', max_price=None):
        if preset or disk_gib:
            sys.exit('SF Compute SKUs fix the disk and shape; omit --preset and --disk-gib')
        sku = next((s for s in self.skus() if s['id'] == platform and not s.get('deleted_at')), None)
        if not sku or (region and region != self.value(sku, 'region')):
            sys.exit('SF Compute SKU not found in the requested region; see `compute platforms --provider sfcompute`')
        gpus = self.value(sku, 'num_accelerators', 0)
        start, end = self.window()
        ask = self.quote(platform, start, end)
        if not ask:
            sys.exit('No SF Compute ask for the requested window; nothing purchased')
        ask_price = Decimal(ask['dollars_per_node_hour'])
        if term == 'spot' and max_price is None:
            max_price = 2 * ask_price / gpus
        cap = self.price_cap(max_price, gpus)
        if ask_price > cap:
            sys.exit('No SF Compute ask at or below --max-price; nothing purchased')
        workspace = self.secret('SF_COMPUTE_WORKSPACE')
        image = image or 'sfc:image:sfcompute:public:ubuntu-24.04-cuda-13.2'
        self.api('GET', '/v2/images/' + urllib.parse.quote(image, safe=''))
        self.secret('SF_COMPUTE_SSH_PRIVATE_KEY_B64')
        # Validate bootstrap credentials before purchasing capacity.
        data = base64.b64encode(user_data().encode()).decode()
        pool_name = 'gradctl-' + name
        pools = [p for p in self.pages('/v2/pools', workspace=workspace) if p['name'] == pool_name]
        if pools:
            sys.exit(f'SF Compute pool {pool_name} already exists; inspect orders and capacity in the console '
                     'before retrying (prevents duplicate purchases)')
        pool = self.api('POST', '/v2/pools', body={'name': pool_name, 'workspace': workspace})
        print(f"SF Compute pool {pool['id']}: buying one node until {end}; prepaid time is not refunded by down",
              file=sys.stderr)
        order = self.buy(pool['id'], platform, start, end, cap, term)
        instance = self.api('POST', '/v2/instances', body={
            'name': name, 'pool': pool['id'], 'sku': platform,
            'image': image,
            'cloud_init_user_data': data, 'tags': {'gradctl-term': term, 'gradctl-order': order['id']}})
        return instance['id']

    def price_cap(self, max_price, gpus):
        if max_price is None or not math.isfinite(max_price) or max_price <= 0:
            sys.exit('SF Compute requires a finite positive --max-price (USD per GPU-hour)')
        cap = (Decimal(str(max_price)) * gpus / Decimal('0.000060')).to_integral_value(
            rounding=ROUND_DOWN) * Decimal('0.000060')
        if not 0 < cap <= 500:
            sys.exit('SF Compute node-hour price must be greater than zero and at most $500')
        return cap

    def buy(self, pool, sku, start, end, cap, term):
        body = {'pool': pool, 'side': 'buy', 'allow_standing': False, 'allow_partial': False,
                'sku': sku, 'allocation_schedule_delta': [{'start_at': start, 'end_at': end, 'node_count': 1}],
                'limit_price_dollars_per_node_hour': format(cap, '.6f')}
        if term == 'spot':
            body['_preview_preemption_limit_price_multiple'] = self.preemption_multiple
        # The same purchase window/body has one key even across callers and ambiguous responses.
        key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        order = self.api('POST', '/v2/orders', body=body, headers={'Idempotency-Key': key})
        for _ in range(30):
            if order['state'] in ('filled', 'cancelled', 'rejected'):
                break
            time.sleep(2)
            order = self.api('GET', f"/v2/orders/{order['id']}")
        if order['state'] != 'filled':
            sys.exit(f"SF Compute order {order['id']} is {order['state']}; inspect pool {pool} before retrying")
        return order

    def extend(self, vm, hours, max_price):
        # Serialize local callers through read/quote/purchase. Provider idempotency also covers identical
        # purchases from other machines; never retry a mutation automatically.
        with (open(self.state / 'sfcompute-extend.lock', 'a') if self.state else nullcontext()) as lock:
            if lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
            return self.extend_locked(vm, hours, max_price)

    def extend_locked(self, vm, hours, max_price):
        cap = self.price_cap(max_price, vm.get('gpus') or 0)
        instance = self.api('GET', f"/v2/instances/{vm['id']}")
        if instance['state'] not in ('running', 'awaiting_allocation'):
            sys.exit('SF Compute cannot extend a terminated or failed instance')
        pool_id = (instance.get('pool') or {}).get('id')
        if not pool_id:
            sys.exit('SF Compute instance has no pool')
        pool = self.api('GET', f'/v2/pools/{pool_id}')
        if pool['name'] != 'gradctl-' + instance['name']:
            sys.exit('Only dedicated gradctl SF Compute pools can be extended')
        active = [i for i in self.pages('/v2/instances', pool=pool_id)
                  if i['state'] not in ('terminated', 'failed')]
        if len(active) != 1 or active[0]['id'] != instance['id']:
            sys.exit("SF Compute pool is shared; refusing to extend another instance's capacity")
        sku = instance['sku']['id']
        allocation = pool['allocation_schedule']['by_sku']
        if any(k != sku and any(x['node_count'] for x in spans) for k, spans in allocation.items()):
            sys.exit('SF Compute pool contains other SKUs; reconcile its allocation before extending')
        schedule = allocation.get(sku, [])
        spans = []
        for index, span in enumerate(schedule):
            end = span.get('end_at')
            if end is None and index + 1 < len(schedule):
                end = schedule[index + 1]['start_at']
            if span['node_count']:
                if span['node_count'] != 1 or end is None:
                    sys.exit('SF Compute extension requires a bounded one-node allocation')
                spans.append((span['start_at'], end))
        now = time.time()
        if not spans or not spans[0][0] <= now < spans[0][1] or any(
                left[1] != right[0] for left, right in zip(spans, spans[1:])):
            sys.exit('SF Compute allocation has expired or has gaps; cannot extend without interruption')
        start = spans[-1][1]
        start, end = self.window(start=start, hours=hours)
        # A pending order may have been accepted by a previous caller with an unconfirmed response.
        orders = list(self.pages('/v2/orders', pool=pool_id, side='buy'))
        if any(o['state'] in ('pending', 'standing', 'partially_filled') for o in orders):
            sys.exit('SF Compute pool has an outstanding buy order; reconcile it before extending again')
        ask = self.quote(sku, start, end)
        if not ask or Decimal(ask['dollars_per_node_hour']) > cap:
            sys.exit('No SF Compute extension ask at or below --max-price; nothing purchased')
        term = (instance.get('tags') or {}).get('gradctl-term')
        if term not in ('spot', 'on-demand'):
            sys.exit('SF Compute instance has no gradctl reservation term')
        # Quotes can take time; do not buy an extension after this VM's allocation has ended.
        if time.time() >= start:
            sys.exit('SF Compute allocation expired during extension checks; nothing purchased')
        fresh = self.api('GET', f"/v2/instances/{vm['id']}")
        if fresh['state'] not in ('running', 'awaiting_allocation') or fresh.get('pool') != instance.get('pool'):
            sys.exit('SF Compute instance changed during extension checks; nothing purchased')
        order = self.buy(pool_id, sku, start, end, cap, term)
        fresh = self.api('GET', f"/v2/instances/{vm['id']}")
        if fresh['state'] not in ('running', 'awaiting_allocation'):
            sys.exit(f"Extension order {order['id']} filled, but the SF Compute instance has terminated; "
                     f"inspect prepaid capacity in pool {pool_id}; it has not been replaced")
        return {'order_id': order['id'], 'pool': pool_id, 'start_at': start, 'end_at': end,
                'hours': (end - start) / 3600, 'term': term}

    def start(self, vm):
        sys.exit('SF Compute instances cannot restart; create a new instance')

    def stop(self, vm):
        sys.exit('SF Compute instances cannot stop and resume; use down when finished')

    def delete(self, vm):
        if vm['state'] != 'COMPLETED':
            self.api('POST', f"/v2/instances/{vm['id']}/terminate")
            for _ in range(30):
                fresh = self.api('GET', f"/v2/instances/{vm['id']}", missing_ok=True)
                if not fresh:
                    return
                if fresh['state'] == 'terminated':
                    break
                time.sleep(2)
            else:
                sys.exit('SF Compute instance is still terminating; retry down after checking the console')
        self.api('DELETE', f"/v2/instances/{vm['id']}", missing_ok=True)
        print(f"SF Compute prepaid capacity in pool {vm.get('pool')} remains until expiry; "
              'sell unused time in the SF Compute console. No refund is implied by down.', file=sys.stderr)
