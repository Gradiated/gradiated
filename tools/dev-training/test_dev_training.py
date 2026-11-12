"""Search filters and provider choice: python3 -m unittest discover -s tools/dev-training"""

import argparse
import re
import unittest

import dev_training


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

    def test_each_platform_name_has_one_provider(self):
        for platform, expected in (('gpu-h100-sxm', 'nebius'), ('nvidia_b300', 'ornn'), ('cpu', 'ornn')):
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

        providers, dev_training.PROVIDERS = dev_training.PROVIDERS, {'nebius': Hung, 'ornn': Healthy}
        rows = []
        try:
            dev_training.each_provider(None, lambda name, cloud: rows.extend(cloud.offers(None)))
        finally:
            dev_training.PROVIDERS = providers
        self.assertEqual(rows, [OFFER])

    def test_nebius_max_price_uses_the_live_spot_price(self):
        from nebius import Nebius
        nebius = Nebius(lambda name: '', None)
        nebius.spot_prices = lambda: {('eu-north1', 'gpu-h100-sxm'): 2.37}
        nebius.estimate = lambda region, platform, preset, term: 99.0
        self.assertAlmostEqual(nebius.hourly_price('eu-north1', 'gpu-h100-sxm', '8gpu-128vcpu-1600gb', 'spot'), 18.96)
        self.assertEqual(nebius.hourly_price('eu-north1', 'gpu-h100-sxm', '1gpu-16vcpu-200gb', 'on-demand'), 99.0)
        self.assertEqual(nebius.hourly_price('eu-north1', 'gpu-l40s-a', '1gpu-8vcpu-32gb', 'spot'), 99.0)


if __name__ == '__main__':
    unittest.main()
