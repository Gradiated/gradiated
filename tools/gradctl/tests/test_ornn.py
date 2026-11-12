"""gradctl compute: the Ornn provider against canned API responses."""

import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

import _path  # noqa: F401
from gradctl.compute.ornn import Ornn

RESERVATION = '4b0f7d5e-0a8f-4f5e-9d55-5c1b6a0c2a11'


class FakeOrnn(Ornn):
    def __init__(self, state, responses):
        super().__init__(lambda name: 'key', state)
        self.responses, self.calls = responses, []

    def api(self, method, path, params=None, body=None, headers=None, missing_ok=False):
        self.calls.append((method, path, params, body, headers))
        return self.responses[(method, path)]


class OrnnTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.state = Path(directory.name)

    def test_offers_price_each_ask_level_per_node(self):
        ornn = FakeOrnn(self.state, {
            ('GET', '/v1/markets/books'): {'orderBooks': [
                {'gpuSlug': 'nvidia_b300', 'saleType': 'spot', 'region': 'us-east-10',
                 'bestAskPricePerGpuHourMicroUsd': 7500000},
                {'gpuSlug': 'nvidia_b300', 'saleType': 'spot', 'region': 'any', 'bestAskPricePerGpuHourMicroUsd': None},
                {'gpuSlug': 'nvidia_h100_sxm', 'saleType': 'spot', 'region': 'us-west-3',
                 'bestAskPricePerGpuHourMicroUsd': None}]},
            ('GET', '/v1/markets/books/nvidia_b300'): {'asks': [
                {'pricePerGpuHourMicroUsd': 7500000, 'nodes': 3, 'gpus': 24, 'orders': 1},
                {'pricePerGpuHourMicroUsd': 8000000, 'nodes': 0, 'gpus': 4, 'orders': 1}]},
        })
        [offer] = ornn.offers('spot')
        self.assertEqual((offer['gpus'], offer['gpu_hour'], offer['hour'], offer['available']), (8, 7.5, 60.0, 3))
        self.assertIn('--platform nvidia_b300 --region us-east-10', offer['up'])

    def test_create_pins_the_quoted_line_and_names_the_reservation(self):
        quote = {'listingId': 'l', 'pricePerGpuHourMicroUsd': 1500000, 'gpus': 1, 'gpusPerNode': 1,
                 'region': 'us-west-3', 'interruptsAt': None, 'interruptReason': None}
        ornn = FakeOrnn(self.state, {
            ('GET', '/v1/markets/books/nvidia_rtx_pro_6000/quote'): {'nodes': [quote]},
            ('POST', '/v1/markets/orders'): {'order': {'orderId': 'o', 'status': 'filled', 'fillIds': [RESERVATION]}},
        })
        ornn.create('exp', None, 'nvidia_rtx_pro_6000', None, None, None, None, term='on-demand', max_price=2)
        method, path, _, body, headers = ornn.calls[-1]
        self.assertEqual(body['saleType'], 'on-demand')
        self.assertNotIn('region', body)
        self.assertEqual(body['nodeSelections'], [{'region': 'us-west-3', 'gpusPerNode': 1,
                                                   'pricePerGpuHourMicroUsd': 1500000, 'nodes': 1}])
        self.assertIn('Idempotency-Key', headers)
        self.assertEqual(ornn.names(), {'exp': RESERVATION})

    def test_create_refuses_above_max_price(self):
        ornn = FakeOrnn(self.state, {('GET', '/v1/markets/books/nvidia_b300/quote'): {'nodes': [
            {'pricePerGpuHourMicroUsd': 7500000, 'gpusPerNode': 8, 'region': 'us-east-10', 'interruptsAt': None}]}})
        with self.assertRaises(SystemExit):
            ornn.create('exp', None, 'nvidia_b300', None, None, None, None, max_price=5)
        self.assertEqual([c[0] for c in ornn.calls], ['GET'])

    def test_find_reads_the_running_vm(self):
        (self.state / 'ornn-names.json').write_text(f'{{"exp": "{RESERVATION}"}}')
        ornn = FakeOrnn(self.state, {
            ('GET', f'/commerce/reservations/{RESERVATION}'): {
                'reservationId': RESERVATION, 'status': 'active', 'kind': 'spot', 'facilityId': 'f',
                'gpuSlug': 'nvidia_b300', 'reservedGpuCount': 8, 'pricePerGpuHourMicroUsd': 7500000},
            ('GET', f'/v1/orchestrator/reservations/{RESERVATION}/virtual-machines'): {'virtual_machines': [
                {'status': 'running', 'ip': '203.0.113.7', 'port': 20022, 'tenant_username': 'ubuntu'}]},
        })
        vm = ornn.find('exp')
        self.assertEqual(len(vm['machines']), 1)
        self.assertEqual((vm['state'], vm['address'], vm['port'], vm['user'], vm['term']),
                         ('RUNNING', '203.0.113.7', 20022, 'ubuntu', 'spot'))
        self.assertIsNone(ornn.find('unknown-name'))

    def test_a_split_node_runs_only_when_every_vm_runs(self):
        (self.state / 'ornn-names.json').write_text(f'{{"exp": "{RESERVATION}"}}')
        reservation = {'reservationId': RESERVATION, 'status': 'active', 'kind': 'spot', 'gpuSlug': 'nvidia_h100_sxm',
                       'reservedGpuCount': 6, 'pricePerGpuHourMicroUsd': 2000000}
        vms = [{'status': 'running', 'ip': '203.0.113.7', 'port': 20022, 'gpu_count': 4},
               {'status': 'provisioning', 'ip': '203.0.113.7', 'port': 20023, 'gpu_count': 2}]
        responses = {('GET', f'/commerce/reservations/{RESERVATION}'): reservation,
                     ('GET', f'/v1/orchestrator/reservations/{RESERVATION}/virtual-machines'):
                         {'virtual_machines': vms}}
        self.assertEqual(FakeOrnn(self.state, responses).find('exp')['state'], 'STARTING')
        vms[1]['status'] = 'running'
        vm = FakeOrnn(self.state, responses).find('exp')
        self.assertEqual((vm['state'], [m['port'] for m in vm['machines']]), ('RUNNING', [20022, 20023]))
        self.assertIn('as 2 VMs', vm['shape'])

    def test_network_failures_become_provider_errors(self):
        ornn = Ornn(lambda name: 'key', self.state)
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('no route')), \
                mock.patch('time.sleep'), self.assertRaises(SystemExit):
            ornn.api('GET', '/v1/markets/books')

    def test_names_survive_concurrent_updates(self):
        from concurrent.futures import ThreadPoolExecutor
        ornn = Ornn(lambda name: 'key', self.state)
        ids = [f'00000000-0000-4000-8000-{i:012d}' for i in range(20)]
        with ThreadPoolExecutor(8) as pool:
            list(pool.map(lambda i: ornn.remember(f'vm{i}', ids[i]), range(20)))
        self.assertEqual(len(ornn.names()), 20)


if __name__ == '__main__':
    unittest.main()
