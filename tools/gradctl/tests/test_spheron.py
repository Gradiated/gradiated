"""gradctl compute: the Spheron provider against canned API responses."""

import unittest
import urllib.error
from unittest import mock

import _path  # noqa: F401
from gradctl.compute.spheron import Spheron

B300 = {'provider': 'spheron-es', 'offerId': 'UK South 1::gpu-b300-sxm::8gpu', 'gpuCount': 8, 'price': 40.0,
        'available': True, 'maintenance': False, 'clusters': ['UK South 1'], 'instanceType': 'SPOT',
        'os_options': ['Ubuntu 22.04', 'Ubuntu 24.04 (CUDA 13)', 'Ubuntu 24.04'],
        'extras': {'deployment_type': 'vm', 'technical': {'units_available': 2}}, 'minimumRuntimeMinutes': 20}
H100 = {'provider': 'data-crunch', 'offerId': '1H100.80S.30V_FIN-01_200_spot', 'gpuCount': 1, 'price': 3.41,
        'hasDiscount': True, 'discountedPrice': 3.0, 'available': True, 'clusters': ['Finland 1'],
        'instanceType': 'SPOT', 'os_options': ['Ubuntu 24.04', 'Ubuntu 24.04 + CUDA 13.0 Open'], 'extras': {}}
CATALOG = {'data': [{'gpuType': 'B300_SXM6', 'offers': [B300]},
                    {'gpuType': 'H100_SXM5', 'offers': [H100, {**H100, 'offerId': 'sold', 'available': False}]},
                    {'gpuType': 'CPU', 'offers': [{**H100, 'gpuCount': 0}]},
                    {'gpuType': 'H100_SXM5_CONTAINER', 'offers': [{**H100, 'provider': 'spheron-con'}]}],
           'totalPages': 1}
RUNNING = {'id': 'd-1', 'name': 'exp', 'providerId': 'spheron-es', 'region': 'UK South 1', 'status': 'running',
           'ipAddress': '203.0.113.7', 'user': 'ubuntu', 'sshPort': 22, 'instanceType': 'SPOT',
           'gpuType': 'B300_SXM6', 'gpuCount': 8, 'hourlyRate': 40.0, 'startedAt': '2026-11-17T10:00:00Z',
           'sshCommand': 'ssh ubuntu@203.0.113.7', 'supportsPause': False,
           'pauseUnsupportedReason': 'Spheron MS does not support stopping an instance.'}


class Answers(list):
    """Successive answers to one call, in order."""


class FakeSpheron(Spheron):
    def __init__(self, responses):
        # secret() decodes _B64 values itself.
        super().__init__(lambda name: 'ssh-ed25519 AAAA test' if name.endswith('_B64') else 'key', None)
        self.responses, self.calls = responses, []

    def api(self, method, path, params=None, body=None, missing_ok=False):
        self.calls.append((method, path, params, body))
        response = self.responses[(method, path)]
        return response.pop(0) if isinstance(response, Answers) else response


class SpheronTests(unittest.TestCase):
    def test_offers_are_gpu_vms_priced_per_gpu_with_the_seller(self):
        offers = FakeSpheron({('GET', '/api/gpu-offers'): CATALOG}).offers('spot')
        self.assertEqual([(o['gpu'], o['gpus'], o['gpu_hour'], o['available']) for o in offers],
                         [('B300_SXM6', 8, 5.0, 2), ('H100_SXM5', 1, 3.0, None), ('H100_SXM5', 1, 3.0, 0)])
        self.assertEqual(offers[0]['region'], 'spheron-es/UK South 1')
        self.assertEqual(offers[0]['up'], "--provider spheron --platform B300_SXM6 "
                                          "--preset 'UK South 1::gpu-b300-sxm::8gpu' --region 'UK South 1'")

    def test_create_deploys_the_offer_with_our_key_and_no_sandbox(self):
        spheron = FakeSpheron({('GET', '/api/gpu-offers'): CATALOG, ('POST', '/api/deployments'): {'id': 'd-1'}})
        with mock.patch('sys.stderr'):
            self.assertEqual(spheron.create('exp', 'spheron-es/UK South 1', 'B300_SXM6', B300['offerId'], None,
                                            None, None, term='spot', max_price=6), 'd-1')
        body = spheron.calls[-1][3]
        self.assertEqual({k: body[k] for k in ('provider', 'offerId', 'gpuType', 'gpuCount', 'region',
                                               'operatingSystem', 'instanceType', 'name', 'agentAccess')},
                         {'provider': 'spheron-es', 'offerId': B300['offerId'], 'gpuType': 'B300_SXM6',
                          'gpuCount': 8, 'region': 'UK South 1', 'operatingSystem': 'Ubuntu 24.04 (CUDA 13)',
                          'instanceType': 'SPOT', 'name': 'exp', 'agentAccess': False})
        self.assertEqual(body['ssh_public_key'], 'ssh-ed25519 AAAA test')
        self.assertNotIn('sshKeyId', body)
        self.assertNotIn('cloudInit', body)

    def test_create_without_a_preset_takes_the_cheapest_available_offer(self):
        spheron = FakeSpheron({('GET', '/api/gpu-offers'): CATALOG, ('POST', '/api/deployments'): {'id': 'd-2'}})
        with mock.patch('sys.stderr'):
            spheron.create('exp', None, 'H100_SXM5', None, None, None, None, term='spot')
        self.assertEqual(spheron.calls[-1][3]['offerId'], H100['offerId'])

    def test_create_refuses_above_max_price(self):
        spheron = FakeSpheron({('GET', '/api/gpu-offers'): CATALOG})
        with mock.patch('sys.stderr'), self.assertRaises(SystemExit):
            spheron.create('exp', None, 'B300_SXM6', None, None, None, None, max_price=4)
        self.assertEqual([c[0] for c in spheron.calls], ['GET'])

    def test_find_reads_the_running_vm(self):
        spheron = FakeSpheron({('GET', '/api/deployments'): [RUNNING, {**RUNNING, 'id': 'd-0', 'status': 'failed'}]})
        vm = spheron.find('exp')
        self.assertEqual((vm['id'], vm['state'], vm['address'], vm['user'], vm['term'], vm['usd_per_gpu_hour']),
                         ('d-1', 'RUNNING', '203.0.113.7', 'ubuntu', 'spot', 5.0))
        self.assertEqual(len(vm['machines']), 1)
        self.assertEqual(spheron.find('d-1')['name'], 'exp')
        self.assertIsNone(spheron.find('other'))

    def test_a_deploying_vm_has_no_machine_yet(self):
        deploying = {**RUNNING, 'status': 'deploying', 'ipAddress': None, 'user': None, 'sshCommand': None}
        vm = FakeSpheron({('GET', '/api/deployments'): [deploying]}).find('exp')
        self.assertEqual((vm['state'], vm['machines'], vm['user']), ('STARTING', [], 'root'))

    def test_stop_relays_why_a_vm_cannot_stop(self):
        spheron = FakeSpheron({})
        with self.assertRaises(SystemExit) as stopped:
            spheron.stop(spheron.vm(RUNNING))
        self.assertIn('Spheron MS does not support', str(stopped.exception))

    def test_delete_waits_for_the_minimum_runtime(self):
        spheron = FakeSpheron({
            ('GET', '/api/deployments/d-1'): RUNNING,
            ('GET', '/api/deployments/d-1/can-terminate'): Answers([
                {'canTerminate': False, 'timeRemaining': 3, 'minimumRuntime': 20, 'reason': 'Minimum runtime not met'},
                {'canTerminate': True}]),
            ('DELETE', '/api/deployments/d-1'): {'message': 'Instance destruction initiated'},
        })
        with mock.patch('time.sleep') as sleep, mock.patch('sys.stderr'):
            spheron.delete(spheron.vm(RUNNING))
        sleep.assert_called_once_with(120)
        self.assertEqual(spheron.calls[-1][:2], ('DELETE', '/api/deployments/d-1'))

    def test_delete_of_a_gone_deployment_does_nothing(self):
        spheron = FakeSpheron({('GET', '/api/deployments/d-1'): {**RUNNING, 'status': 'terminated-provider'}})
        spheron.delete(spheron.vm(RUNNING))
        self.assertNotIn('DELETE', [c[0] for c in spheron.calls])

    def test_a_failed_create_is_not_repeated(self):
        spheron = Spheron(lambda name: 'key', None)
        error = urllib.error.HTTPError('https://app.spheron.ai/api/deployments', 502, 'Bad Gateway', {}, None)
        error.read = lambda: b'{"code": "internal_error", "error": "upstream"}'
        with mock.patch('urllib.request.urlopen', side_effect=error) as urlopen, mock.patch('time.sleep'), \
                self.assertRaises(SystemExit) as failed:
            spheron.api('POST', '/api/deployments', body={})
        self.assertEqual(urlopen.call_count, 1)
        self.assertIn('internal_error', str(failed.exception))

    def test_reads_retry_network_failures_then_fail(self):
        spheron = Spheron(lambda name: 'key', None)
        with mock.patch('urllib.request.urlopen', side_effect=urllib.error.URLError('no route')) as urlopen, \
                mock.patch('time.sleep'), self.assertRaises(SystemExit):
            spheron.api('GET', '/api/deployments')
        self.assertEqual(urlopen.call_count, 5)


if __name__ == '__main__':
    unittest.main()
