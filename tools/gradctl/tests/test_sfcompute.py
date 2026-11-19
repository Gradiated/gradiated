"""SF Compute behavior with synthetic API fixtures; never purchases compute."""

import base64
from datetime import datetime, timezone
import unittest
import urllib.error
from unittest import mock

import _path  # noqa: F401
from gradctl.compute.sfcompute import SFCompute
from gradctl.compute import commands
from gradctl.compute.nebius import Nebius

SKU = {'id': 'sku_test', 'alias': 'test', 'accelerator': {'value': 'h100'},
       'num_accelerators': {'value': 8}, 'region': {'value': 'us-west1'}}
ASK = {'instance_sku': 'sku_test', 'dollars_per_node_hour': '16.000000'}
INSTANCE = {'id': 'inst_test', 'name': 'exp', 'state': 'running', 'sku': {'id': 'sku_test', 'alias': 'test'},
            'created_at': 1700000000, 'pool': {'id': 'pool_test'}, 'tags': {'gradctl-term': 'spot'}}


class Fake(SFCompute):
    def __init__(self):
        super().__init__(lambda name: 'test-workspace', None)
        self.calls = []
        self.responses = {('GET', '/v2/skus'): {'data': [SKU], 'has_more': False},
                          ('GET', '/v2/pools'): {'data': [], 'has_more': False},
                          ('GET', '/preview/v2/platform_constants'): {
                              'allocation_schedule_grid': {'time_grid': [3600, 7200, 10800]}},
                          ('GET', '/preview/v2/orderbook/quote'): {'best_ask': ASK},
                          ('POST', '/v2/pools'): {'id': 'pool_test'},
                          ('POST', '/v2/orders'): {'id': 'ordr_test', 'state': 'filled'},
                          ('POST', '/v2/instances'): INSTANCE,
                          ('GET', '/v2/instances'): {'data': [INSTANCE], 'has_more': False},
                          ('GET', '/v2/instances/inst_test/ssh'): {'hostname': '203.0.113.1', 'port': 2222},
                          ('GET', '/v2/images/sfc%3Aimage%3Asfcompute%3Apublic%3Aubuntu-24.04-cuda-13.2'): {},
                          ('POST', '/v2/instances/inst_test/terminate'): {},
                          ('GET', '/v2/instances/inst_test'): {**INSTANCE, 'state': 'terminated'},
                          ('DELETE', '/v2/instances/inst_test'): {}}

    def api(self, method, path, params=None, body=None, missing_ok=False, headers=None):
        self.calls.append((method, path, params, body))
        if headers:
            self.last_headers = headers
        return self.responses[method, path]

    def create_test(self, **kwargs):
        with mock.patch('time.time', return_value=3660):
            return self.create('exp', None, 'sku_test', None, None, None, lambda: '#cloud-config',
                               max_price=2.0, **kwargs)


class SFComputeTests(unittest.TestCase):
    def test_root_cloud_init_enables_key_login_and_uses_sf_credentials(self):
        with mock.patch.object(commands, 'secret', return_value='ssh-ed25519 AAAA synthetic') as secret, \
                mock.patch.object(commands, 'join_key', return_value='synthetic-join-key'):
            config = commands.cloud_init(Fake(), 'sfcompute-exp')
        self.assertIn('disable_root: false', config.splitlines())
        self.assertIn('  - name: root', config.splitlines())
        self.assertIn('      - ssh-ed25519 AAAA synthetic', config.splitlines())
        secret.assert_called_once_with('SF_COMPUTE_SSH_PUBLIC_KEY_B64')
        with mock.patch.object(commands, 'secret', return_value='ssh-ed25519 AAAA synthetic'), \
                mock.patch.object(commands, 'join_key', return_value='synthetic-join-key'):
            config = commands.cloud_init(Nebius(lambda name: '', None), 'nebius-exp')
        self.assertNotIn('disable_root: false', config.splitlines())

    def test_search_converts_node_prices_without_claiming_capacity(self):
        cloud = Fake()
        with mock.patch('time.time', return_value=3660):
            offers = cloud.offers(None)
        self.assertEqual([o['term'] for o in offers], ['spot', 'on-demand'])
        self.assertEqual(offers[0]['gpu_hour'], 2)
        self.assertEqual(offers[0]['hour'], 16)
        self.assertIsNone(offers[0]['available'])
        self.assertEqual(cloud.calls[-1][2]['requirements'], 'instance_sku:sku_test')

    def test_market_tick_rounding_cannot_exceed_the_price_cap(self):
        cloud = Fake()
        with self.assertRaisesRegex(SystemExit, 'No SF Compute ask'):
            cloud.create_test()
        self.assertFalse(any(c[0] == 'POST' for c in cloud.calls))
        # 16 is not a market tick: a 2.00 cap rounds down and must reject the 16 ask.

    def test_higher_cap_buys_and_spot_can_be_preempted(self):
        cloud = Fake()
        cloud.responses['GET', '/preview/v2/orderbook/quote'] = {'best_ask': {**ASK, 'dollars_per_node_hour': '15.0'}}
        cloud.create_test()
        order = next(c[3] for c in cloud.calls if c[:2] == ('POST', '/v2/orders'))
        self.assertFalse(order['allow_standing'])
        self.assertFalse(order['allow_partial'])
        self.assertEqual(order['_preview_preemption_limit_price_multiple'], '1.2')
        self.assertEqual(order['allocation_schedule_delta'], [{'start_at': 3660, 'end_at': 7200, 'node_count': 1}])
        instance = cloud.calls[-1][3]
        self.assertEqual(base64.b64decode(instance['cloud_init_user_data']), b'#cloud-config')

    def test_on_demand_omits_preemption(self):
        cloud = Fake()
        cloud.responses['GET', '/preview/v2/orderbook/quote'] = {'best_ask': {**ASK, 'dollars_per_node_hour': '15.0'}}
        cloud.create_test(term='on-demand')
        order = next(c[3] for c in cloud.calls if c[:2] == ('POST', '/v2/orders'))
        self.assertNotIn('_preview_preemption_limit_price_multiple', order)

    def test_window_never_exceeds_duration_budget(self):
        cloud = Fake()
        with mock.patch('time.time', return_value=3660):
            self.assertEqual(cloud.window(), (3660, 7200))
            cloud.duration_hours = 0.1
            with self.assertRaisesRegex(SystemExit, 'schedule boundary'):
                cloud.window()
            cloud.duration_hours = float('inf')
            with self.assertRaises(SystemExit):
                cloud.window()

    def test_all_pages_are_read(self):
        cloud = Fake()
        cloud.api = mock.Mock(side_effect=[{'data': [SKU], 'has_more': True, 'cursor': 'next'},
                                           {'data': [], 'has_more': False}])
        self.assertEqual(cloud.skus(), [SKU])
        self.assertEqual(cloud.api.call_args.args[2], {'starting_after': 'next'})

    def test_bad_price_or_region_never_mutates(self):
        for price in (None, 0, -1, float('nan'), float('inf'), 1):
            cloud = Fake()
            with self.assertRaises(SystemExit):
                cloud.create('exp', None, 'sku_test', None, None, None, lambda: '', max_price=price)
            self.assertFalse(any(c[0] == 'POST' for c in cloud.calls))
        cloud = Fake()
        with self.assertRaises(SystemExit):
            cloud.create('exp', 'wrong-region', 'sku_test', None, None, None, lambda: '', max_price=3)
        self.assertFalse(any(c[0] == 'POST' for c in cloud.calls))

    def test_existing_pool_prevents_second_purchase_even_without_instance(self):
        cloud = Fake()
        cloud.responses['GET', '/preview/v2/orderbook/quote'] = {'best_ask': {**ASK, 'dollars_per_node_hour': '15.0'}}
        cloud.responses['GET', '/v2/pools'] = {'data': [{'name': 'gradctl-exp'}], 'has_more': False}
        with self.assertRaisesRegex(SystemExit, 'duplicate purchases'):
            cloud.create_test()
        self.assertFalse(any(c[0] == 'POST' for c in cloud.calls))

    def test_rejected_order_does_not_create_vm(self):
        cloud = Fake()
        cloud.responses['GET', '/preview/v2/orderbook/quote'] = {'best_ask': {**ASK, 'dollars_per_node_hour': '15.0'}}
        cloud.responses['POST', '/v2/orders'] = {'id': 'ordr_test', 'state': 'cancelled'}
        with self.assertRaisesRegex(SystemExit, 'cancelled'):
            cloud.create_test()
        self.assertNotIn(('POST', '/v2/instances'), [c[:2] for c in cloud.calls])

    def test_vm_ssh_terminated_state_and_cleanup_preserve_prepaid_pool(self):
        cloud = Fake()
        vm = cloud.find('exp')
        self.assertEqual((vm['address'], vm['port'], vm['user']), ('203.0.113.1', 2222, 'root'))
        self.assertEqual(cloud.vm({**INSTANCE, 'state': 'terminated'})['state'], 'COMPLETED')
        cloud.delete(vm)
        self.assertEqual(cloud.calls[-1][:2], ('DELETE', '/v2/instances/inst_test'))
        self.assertNotIn(('DELETE', '/v2/pools/pool_test'), [c[:2] for c in cloud.calls])

    def test_meter_price_comes_from_actual_fills_not_limit(self):
        cloud = Fake()
        cloud.responses['GET', '/v2/orders'] = {'has_more': False, 'data': [{'sku': {'id': 'sku_test'},
            'limit_price_dollars_per_node_hour': '99.0',
            'fills': [{'price_dollars_per_node_hour': '16.0', 'allocation_schedule_delta': [
                {'start_at': 0, 'end_at': 3600, 'node_count': 1}]},
                      {'price_dollars_per_node_hour': '8.0', 'allocation_schedule_delta': [
                {'start_at': 3600, 'end_at': 7200, 'node_count': 1}]}]},
                {'sku': {'id': 'sku_test'}, 'fills': [{'price_dollars_per_node_hour': '24.0',
                    'allocation_schedule_delta': [{'start_at': 7200, 'end_at': 10800, 'node_count': 1}]}]}]}
        vm = cloud.vm({**INSTANCE, 'tags': {'gradctl-order': 'ordr_test'}})
        self.assertEqual(vm['usd_per_gpu_hour'], 2.0)

    def test_instance_listing_is_scoped_to_selected_workspace(self):
        cloud = Fake()
        cloud.find('exp')
        request = next(c for c in cloud.calls if c[:2] == ('GET', '/v2/instances'))
        self.assertEqual(request[2], {'workspace': 'test-workspace'})

    def test_terminal_billing_boundary_is_capped_by_allocation_expiry(self):
        cloud = Fake()
        cloud.responses['GET', '/v2/orders'] = {'has_more': False, 'data': [
            {'sku': {'id': 'sku_test'}, 'fills': [{'price_dollars_per_node_hour': '16.0',
                'allocation_schedule_delta': [{'start_at': 100, 'end_at': 200, 'node_count': 1}]}]}]}
        for updated, expected in ((190, 190), (250, 200)):
            vm = cloud.vm({**INSTANCE, 'state': 'terminated', '_preview_updated_at': updated,
                           'tags': {'gradctl-order': 'ordr_test'}})
            self.assertEqual(vm['billing_ended_at'], expected)

    def test_usage_price_crosses_extension_boundary_without_repricing_earlier_time(self):
        cloud = Fake()
        vm = {'price_schedule': [{'start_at': 0, 'end_at': 3600, 'node_count': 1, 'node_hour': '16.0'},
                                 {'start_at': 3600, 'end_at': 7200, 'node_count': 1, 'node_hour': '24.0'}]}
        def at(seconds):
            return datetime.fromtimestamp(seconds, timezone.utc)
        self.assertEqual(cloud.usage_price(vm, at(0), at(1800)), 16)
        self.assertEqual(cloud.usage_price(vm, at(1800), at(5400)), 20)
        self.assertEqual(cloud.usage_price(vm, at(3600), at(7200)), 24)
        self.assertIsNone(cloud.usage_price({}, at(0), at(3600)))

    def test_ambiguous_mutations_are_not_retried_or_echoed(self):
        cloud = SFCompute(lambda name: 'private-token', None)
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('private-token')) as call:
            with self.assertRaises(SystemExit) as error:
                cloud.api('POST', '/v2/orders', body={})
        self.assertEqual(call.call_count, 1)
        self.assertNotIn('private-token', str(error.exception))


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.cloud = Fake()
        self.vm = {'id': INSTANCE['id'], 'gpus': 8}
        self.cloud.responses['GET', '/v2/instances/inst_test'] = INSTANCE
        self.cloud.responses['GET', '/v2/pools/pool_test'] = {
            'name': 'gradctl-exp', 'allocation_schedule': {'by_sku': {'sku_test': [
                {'start_at': 3600, 'end_at': 7200, 'node_count': 1},
                {'start_at': 7200, 'end_at': None, 'node_count': 0}]}}}
        self.cloud.responses['GET', '/v2/orders'] = {'data': [], 'has_more': False}
        self.cloud.responses['GET', '/preview/v2/orderbook/quote'] = {
            'best_ask': {**ASK, 'dollars_per_node_hour': '15.0'}}

    def run_extend(self, hours=1, max_price=2):
        with mock.patch('time.time', return_value=3660):
            return self.cloud.extend(self.vm, hours, max_price)

    def test_extends_same_pool_and_sku_from_existing_expiry_without_touching_vm(self):
        result = self.run_extend()
        self.assertEqual((result['start_at'], result['end_at'], result['hours']), (7200, 10800, 1))
        posts = [c for c in self.cloud.calls if c[0] != 'GET']
        self.assertEqual([c[1] for c in posts], ['/v2/orders'])
        body = posts[0][3]
        self.assertEqual((body['pool'], body['sku']), ('pool_test', 'sku_test'))
        self.assertEqual(body['allocation_schedule_delta'], [{'start_at': 7200, 'end_at': 10800, 'node_count': 1}])
        self.assertEqual(body['limit_price_dollars_per_node_hour'], '15.999960')
        self.assertEqual(body['_preview_preemption_limit_price_multiple'], '1.2')
        self.assertIn('Idempotency-Key', self.cloud.last_headers)

    def test_on_demand_extension_has_no_callable_preemption(self):
        self.cloud.responses['GET', '/v2/instances/inst_test'] = {
            **INSTANCE, 'tags': {'gradctl-term': 'on-demand'}}
        self.run_extend()
        order = next(c[3] for c in self.cloud.calls if c[:2] == ('POST', '/v2/orders'))
        self.assertNotIn('_preview_preemption_limit_price_multiple', order)

    def test_rejects_unsafe_or_expired_allocation_without_spending(self):
        scenarios = [
            ('expired', [{'start_at': 0, 'end_at': 3600, 'node_count': 1}]),
            ('gap', [{'start_at': 3600, 'end_at': 7200, 'node_count': 1},
                     {'start_at': 10800, 'end_at': 14400, 'node_count': 1}]),
            ('multi-node', [{'start_at': 3600, 'end_at': 7200, 'node_count': 2}]),
            ('unbounded', [{'start_at': 3600, 'end_at': None, 'node_count': 1}])]
        for label, schedule in scenarios:
            with self.subTest(label=label):
                self.setUp()
                self.cloud.responses['GET', '/v2/pools/pool_test']['allocation_schedule']['by_sku']['sku_test'] = schedule
                with self.assertRaises(SystemExit):
                    self.run_extend()
                self.assertFalse(any(c[0] != 'GET' for c in self.cloud.calls))

    def test_refuses_pending_orders_and_shared_pools(self):
        for state in ('pending', 'standing', 'partially_filled'):
            self.setUp()
            self.cloud.responses['GET', '/v2/orders']['data'] = [{'state': state}]
            with self.assertRaisesRegex(SystemExit, 'outstanding buy order'):
                self.run_extend()
            self.assertFalse(any(c[0] != 'GET' for c in self.cloud.calls))
        self.setUp()
        self.cloud.responses['GET', '/v2/instances']['data'] = [INSTANCE, {**INSTANCE, 'id': 'inst_other'}]
        with self.assertRaisesRegex(SystemExit, 'shared'):
            self.run_extend()
        self.assertFalse(any(c[0] != 'GET' for c in self.cloud.calls))

    def test_bad_inputs_and_high_quote_cannot_purchase(self):
        for hours, cap in ((0, 2), (float('nan'), 2), (1, -1), (1, float('inf')), (1, 1), (0.2, 2)):
            self.setUp()
            with self.assertRaises(SystemExit):
                self.run_extend(hours, cap)
            self.assertFalse(any(c[0] != 'GET' for c in self.cloud.calls))

    def test_failed_order_never_replaces_the_instance(self):
        self.cloud.responses['POST', '/v2/orders'] = {'id': 'ordr_test', 'state': 'cancelled'}
        with self.assertRaisesRegex(SystemExit, 'cancelled'):
            self.run_extend()
        self.assertEqual([c[1] for c in self.cloud.calls if c[0] != 'GET'], ['/v2/orders'])

    def test_identical_purchases_have_identical_idempotency_keys(self):
        self.run_extend()
        key = self.cloud.last_headers['Idempotency-Key']
        self.run_extend()
        self.assertEqual(self.cloud.last_headers['Idempotency-Key'], key)



if __name__ == '__main__':
    unittest.main()
