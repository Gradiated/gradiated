import importlib.util
import io
import json
from pathlib import Path
import unittest
from unittest.mock import MagicMock

spec = importlib.util.spec_from_file_location('mint', Path(__file__).with_name('mint-bootstrap-key.py'))
mint = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mint)


def responder(body):
    opened = MagicMock()
    opened.return_value.__enter__.return_value = io.StringIO(json.dumps(body))
    return opened


class BootstrapKeyTests(unittest.TestCase):
    def test_requests_a_single_use_preauthorized_bootstrap_tag(self):
        request = mint.key_request('yzno396wdsidu4', 6)
        create = request['capabilities']['devices']['create']
        self.assertEqual(create, {'reusable': False, 'ephemeral': False, 'preauthorized': True,
                                  'tags': ['tag:gpu-bootstrap']})
        self.assertEqual(request['expirySeconds'], 6 * 3600)

    def test_rejects_long_lived_keys_and_invalid_pods(self):
        for pod, hours in (('pod', 25), ('pod', 0), ('-oProxy', 1), ('POD', 1)):
            with self.subTest(pod=pod, hours=hours), self.assertRaises(ValueError):
                mint.key_request(pod, hours)

    def test_rejects_non_auth_keys(self):
        with self.assertRaises(ValueError):
            mint.mint('pod', 1, 'bearer', responder({'key': 'tskey-client-oops', 'id': 'k1'}))
        created = mint.mint('pod', 1, 'bearer', responder({'key': 'tskey-auth-ok', 'id': 'k1'}))
        self.assertEqual(created['id'], 'k1')


if __name__ == '__main__':
    unittest.main()
