"""gradctl compute: search filters and provider choice."""

import argparse
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

import _path  # noqa: F401
from gradctl.compute import commands as dev_training


def search_args(**overrides):
    return argparse.Namespace(**{'gpu': None, 'region': None, 'min_gpus': 1, 'max_gpus': None, 'max_price': None,
                                 'all': False, **overrides})


OFFER = {'gpu': 'gpu-h100-sxm', 'region': 'eu-north1', 'gpus': 8, 'gpu_hour': 2.37, 'available': 2}


class SearchTests(unittest.TestCase):
    def test_filters_combine(self):
        self.assertTrue(dev_training.matches(search_args(gpu='H100', region='eu-', max_gpus=8, max_price=2.5), OFFER))
        self.assertFalse(dev_training.matches(search_args(region='us-'), OFFER))
        self.assertFalse(dev_training.matches(search_args(max_gpus=4), OFFER))
        self.assertFalse(dev_training.matches(search_args(max_price=2), OFFER))

    def test_hides_sold_out_offers_but_keeps_unknown_capacity(self):
        self.assertFalse(dev_training.matches(search_args(), {**OFFER, 'available': 0}))
        self.assertTrue(dev_training.matches(search_args(all=True), {**OFFER, 'available': 0}))
        self.assertTrue(dev_training.matches(search_args(), {**OFFER, 'available': None}))

    def test_provider_lists(self):
        self.assertEqual(dev_training.provider_list('ornn, nebius'), ['ornn', 'nebius'])
        with self.assertRaises(argparse.ArgumentTypeError):
            dev_training.provider_list('aws')

    def test_default_results_skip_ornn_but_explicit_selection_still_works(self):
        with mock.patch.object(dev_training, 'provider') as provider:
            visited = []
            dev_training.each_provider(None, lambda name, cloud: visited.append(name))
            self.assertEqual(visited, ['nebius', 'sfcompute', 'spheron'])
            self.assertNotIn(mock.call('ornn'), provider.call_args_list)
            dev_training.each_provider(['ornn'], lambda name, cloud: visited.append(name))
            self.assertEqual(visited[-1], 'ornn')
            provider.assert_called_with('ornn')

    def test_each_platform_name_has_one_provider(self):
        for platform, expected in (('gpu-h100-sxm', 'nebius'), ('nvidia_b300', 'ornn'), ('cpu', 'ornn'),
                                    ('H100_SXM5', 'spheron'), ('B300_SXM6', 'spheron'), ('sku_abc', 'sfcompute')):
            owners = [name for name, cls in dev_training.PROVIDERS.items()
                      if re.match(cls.platform_pattern, platform)]
            self.assertEqual(owners, [expected])

    def test_split_machines_get_names_no_vm_can_take(self):
        vm = {'machines': [{}, {}, {}]}
        self.assertEqual(dev_training.hosts('ornn-exp', vm), ['ornn-exp', 'ornn-exp--2', 'ornn-exp--3'])
        self.assertEqual(dev_training.hosts('nebius-exp', {'machines': []}), ['nebius-exp'])

    def test_lookup_stops_when_a_provider_cannot_be_checked(self):
        class Down:
            name = 'nebius'

            def __init__(self, secret, state):
                pass

            def find(self, name):
                raise SystemExit('nebius CLI missing')

        class Empty(Down):
            name = 'ornn'

            def find(self, name):
                return None

        providers, dev_training.PROVIDERS = dev_training.PROVIDERS, {'nebius': Down, 'ornn': Empty}
        try:
            with self.assertRaises(SystemExit):
                dev_training.locate(argparse.Namespace(name='exp', provider=None))
            self.assertEqual(dev_training.locate(argparse.Namespace(name='exp', provider=None), strict=False),
                             (None, None))
        finally:
            dev_training.PROVIDERS = providers

    def test_split_vm_selector_is_positive(self):
        self.assertEqual(dev_training.positive('2'), 2)
        for value in ('0', '-1', 'x'):
            with self.assertRaises(argparse.ArgumentTypeError):
                dev_training.positive(value)

    def test_search_skips_a_provider_that_fails_in_any_way(self):
        class Hung:
            virtualization = 'vm'

            def __init__(self, secret, state):
                pass

            def offers(self, term):
                raise TimeoutError('nebius CLI hung')

        class Healthy(Hung):
            def offers(self, term):
                return [OFFER]

        providers, dev_training.PROVIDERS = dev_training.PROVIDERS, {'nebius': Hung, 'spheron': Healthy}
        rows = []
        try:
            dev_training.each_provider(None, lambda name, cloud: rows.extend(cloud.offers(None)))
        finally:
            dev_training.PROVIDERS = providers
        self.assertEqual(rows, [OFFER])

    def test_nebius_max_price_uses_the_live_spot_price(self):
        from gradctl.compute.nebius import Nebius
        nebius = Nebius(lambda name: '', None)
        nebius.spot_prices = lambda: {('eu-north1', 'gpu-h100-sxm'): 2.37}
        nebius.estimate = lambda region, platform, preset, term: 99.0
        self.assertAlmostEqual(nebius.hourly_price('eu-north1', 'gpu-h100-sxm', '8gpu-128vcpu-1600gb', 'spot'), 18.96)
        self.assertEqual(nebius.hourly_price('eu-north1', 'gpu-h100-sxm', '1gpu-16vcpu-200gb', 'on-demand'), 99.0)
        self.assertEqual(nebius.hourly_price('eu-north1', 'gpu-l40s-a', '1gpu-8vcpu-32gb', 'spot'), 99.0)


    def test_nebius_default_spot_policy_uses_exact_region_and_enforces_double_quote(self):
        from gradctl.compute.nebius import Nebius

        with tempfile.TemporaryDirectory() as directory:
            cloud = Nebius(lambda name: '', Path(directory))
            cloud.spot_prices = lambda: {
                ('eu-north1', 'gpu-h200-sxm'): 2.18,
                ('eu-west1', 'gpu-h200-sxm'): 2.00,
            }
            cloud.items = lambda *args: [{'metadata': {'id': 'subnet-test'}}]
            cloud.estimate = mock.Mock(return_value=43.2)
            requests = []
            expected_policy_price = '4.360'


            def cli(*args, **kwargs):
                if args[:3] == ('billing', 'pricing-policy', 'get-by-name'):
                    return None
                if args[:3] == ('billing', 'pricing-policy', 'create'):
                    self.assertEqual(args[-2:], ('--pricing-max-price-v1-max-price', expected_policy_price))
                    return {
                        'metadata': {'id': 'pricingpolicy-test', 'labels': {'gradctl-vm': 'test-name'}},
                        'spec': {
                            'compute_instance_spec': {'v1': {'platform': 'gpu-h200-sxm'}},
                            'pricing': {'max_price_v1': {'max_price': expected_policy_price}},
                        },
                    }
                self.assertEqual(args[:3], ('compute', 'instance', 'create'))
                requests.append(json.loads(Path(args[-1]).read_text())['spec'])

            cloud.cli = cli
            create_args = ('test-name', 'eu-north1', 'gpu-h200-sxm', '8gpu-128vcpu-1600gb',
                           None, None, lambda: '#cloud-config')
            cloud.create(*create_args)
            cloud.create(*create_args, term='on-demand')
            cloud.create(*create_args, max_price=3)
            self.assertEqual(requests[0]['spot_pricing_policy'], {'id': 'pricingpolicy-test'})
            self.assertNotIn('follows_spot_price', requests[0])
            self.assertNotIn('preemptible', requests[1])
            self.assertIn('follows_spot_price', requests[2])
            self.assertNotIn('spot_pricing_policy', requests[2])

            cloud.estimate.return_value = 32
            expected_policy_price = '3.990'
            cloud.create(*create_args)
            self.assertEqual(requests[3]['spot_pricing_policy'], {'id': 'pricingpolicy-test'})

    def test_nebius_failed_create_checks_for_policy_rollback(self):
        from gradctl.compute.nebius import Nebius

        with tempfile.TemporaryDirectory() as directory:
            cloud = Nebius(lambda name: '', Path(directory))
            cloud.items = mock.Mock(return_value=[{'metadata': {'id': 'subnet-test'}}])
            cloud.capped_spot_policy = mock.Mock(return_value='policy-id')
            cloud.remove_unused_policy = mock.Mock()
            cloud.cli = mock.Mock(side_effect=SystemExit('create failed'))
            with self.assertRaisesRegex(SystemExit, 'create failed'):
                cloud.create('test-name', 'eu-north1', 'gpu-h200-sxm', '8gpu-128vcpu-1600gb',
                             None, None, lambda: '#cloud-config')
            cloud.remove_unused_policy.assert_called_once_with('eu-north1', 'test-name', 'policy-id')

    def test_nebius_delete_cleans_only_its_own_orphaned_policy(self):
        from gradctl.compute.nebius import Nebius

        cloud = Nebius(lambda name: '', None)
        vm = {'id': 'vm-id', 'name': 'test-name', 'region': 'eu-north1', 'spot_pricing_policy_id': 'policy-id'}
        cloud.cli = mock.Mock(return_value={'metadata': {'labels': {'gradctl-vm': 'test-name'}}})
        cloud.items = mock.Mock(return_value=[{'spec': {'spot_pricing_policy': {'id': 'policy-id'}}}])
        cloud.delete(vm)
        self.assertEqual(cloud.cli.call_args.args[:3], ('billing', 'pricing-policy', 'get'))
        cloud.items.return_value = []
        cloud.delete(vm)
        cloud.cli.assert_called_with('billing', 'pricing-policy', 'delete', '--id', 'policy-id', missing_ok=True)
        cloud.cli.return_value = {'metadata': {}}
        cloud.delete(vm)
        self.assertEqual(cloud.cli.call_args.args[:3], ('billing', 'pricing-policy', 'get'))

    def test_nebius_default_requires_a_live_quote_before_creating_resources(self):
        from gradctl.compute.nebius import Nebius

        cloud = Nebius(lambda name: '', None)
        cloud.spot_prices = lambda: {}
        cloud.items = lambda *args: [{'metadata': {'id': 'subnet-test'}}]
        cloud.cli = mock.Mock()
        with self.assertRaisesRegex(SystemExit, 'No live spot quote'):
            cloud.create('test-name', 'eu-north1', 'gpu-h200-sxm', '8gpu-128vcpu-1600gb',
                         None, None, lambda: '#cloud-config')
        cloud.cli.assert_not_called()


    def test_nebius_can_retry_policy_cleanup_when_vm_is_gone(self):
        from gradctl.compute import nebius

        cloud = nebius.Nebius(lambda name: '', None)
        cloud.items = mock.Mock(return_value=[
            {'metadata': {'id': 'policy-id', 'labels': {'gradctl-vm': 'test-name'}}},
            {'metadata': {'id': 'other-id', 'labels': {'gradctl-vm': 'another-vm'}}},
            {'metadata': {'id': 'manual-id'}},
        ])
        cloud.remove_unused_policy = mock.Mock()
        with mock.patch.object(nebius, 'PROJECTS', {'eu-north1': 'test-project'}):
            cloud.remove_vm_policies('test-name')
        cloud.remove_unused_policy.assert_called_once_with('eu-north1', 'test-name', 'policy-id')


class ExtensionCommandTests(unittest.TestCase):
    def test_dispatch_preserves_provider_result(self):
        from unittest import mock
        from types import SimpleNamespace
        cloud = SimpleNamespace(name='sfcompute', extend=mock.Mock(return_value={
            'hours': 2, 'end_at': 10800, 'order_id': 'ordr_test'}))
        vm = {'name': 'exp'}
        args = argparse.Namespace(name='exp', provider='sfcompute', hours=2, max_price=3)
        with mock.patch.object(dev_training, 'locate', return_value=(cloud, vm)):
            result = dev_training.extend(args)
        cloud.extend.assert_called_once_with(vm, 2, 3)
        self.assertEqual(result.data['provider'], 'sfcompute')
        self.assertEqual(result.data['order_id'], 'ordr_test')

    def test_continuously_billed_providers_explain_why_extension_is_unnecessary(self):
        from unittest import mock
        from gradctl.core import UsageError
        for name in ('nebius', 'ornn', 'spheron'):
            cloud = dev_training.PROVIDERS[name](lambda name: '', None)
            args = argparse.Namespace(name='exp', provider=name, hours=1, max_price=3)
            with mock.patch.object(dev_training, 'locate', return_value=(cloud, {'name': 'exp'})):
                with self.assertRaisesRegex(UsageError, name):
                    dev_training.extend(args)

    def test_invalid_limits_fail_before_provider_lookup(self):
        from unittest import mock
        from gradctl.core import UsageError
        for hours, cap in ((0, 2), (float('nan'), 2), (1, float('inf')), (1, -1)):
            with mock.patch.object(dev_training, 'locate') as locate:
                with self.assertRaises(UsageError):
                    dev_training.extend(argparse.Namespace(hours=hours, max_price=cap))
                locate.assert_not_called()


class SshTests(unittest.TestCase):
    def test_json_ssh_puts_options_before_the_destination(self):
        from unittest import mock
        from gradctl.core import UsageError
        args = argparse.Namespace(name='exp', provider=None, vm=1, command=['--', 'nvidia-smi', '-L'])
        base = ['ssh', '-i', 'key', '-p', '22', 'ubuntu@203.0.113.7']
        with mock.patch.object(dev_training, 'located'), \
                mock.patch.object(dev_training, 'ssh_command', return_value=base), \
                mock.patch('subprocess.run') as run:
            run.return_value = mock.Mock(returncode=0, stdout='GPU 0', stderr='')
            result = dev_training.ssh(args, as_json=True)
        argv = run.call_args.args[0]
        self.assertEqual(argv, ['ssh', '-i', 'key', '-p', '22', '-o', 'BatchMode=yes', 'ubuntu@203.0.113.7',
                                'nvidia-smi', '-L'])
        self.assertEqual(result.data['stdout'], 'GPU 0')
        with self.assertRaises(UsageError):
            dev_training.ssh(argparse.Namespace(name='exp', provider=None, vm=1, command=[]), as_json=True)


if __name__ == '__main__':
    unittest.main()
