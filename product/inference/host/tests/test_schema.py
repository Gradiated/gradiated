import copy
import unittest

import support  # noqa: F401

from gradiated_host import schema

TOKEN = 'management_' + 'x' * 40
PAYLOAD = {
    'version': 1,
    'instance_id': '019d5a4a-0000-7000-8000-000000000001',
    'management_token': TOKEN,
    'auth_key': 'tskey-auth-kSecret-0123',
    'api_endpoint': '100.64.0.1',
    'host_bundle': {'sha256': 'a' * 64, 'base_id': 'ubuntu24-cuda13-amd64-v2',
                    'url': 'https://bucket.s3.amazonaws.com/bundles/sha256/x.tar.gz?X-Amz-Signature=secret'},
}
RESULT = {'version': 1, 'tailscale_ip': '100.101.172.112', 'gpu_count': 4, 'gpu_product': 'B300',
          'cpu': 57, 'memory_gib': 880, 'promotion': True}


def changed(path, value):
    document = copy.deepcopy(PAYLOAD)
    target = document
    for name in path[:-1]:
        target = target[name]
    if value is KeyError:
        del target[path[-1]]
    else:
        target[path[-1]] = value
    return document


class PayloadSchema(unittest.TestCase):
    def test_accepts_a_complete_payload(self):
        self.assertEqual(schema.payload(copy.deepcopy(PAYLOAD)), PAYLOAD)

    def test_rejects_wrong_missing_and_extra_fields(self):
        cases = {
            'version 2': changed(['version'], 2),
            'boolean version': changed(['version'], True),
            'short token': changed(['management_token'], 'short'),
            'public endpoint': changed(['api_endpoint'], '203.0.113.1'),
            'endpoint outside the tailnet range': changed(['api_endpoint'], '100.128.0.1'),
            'not an auth key': changed(['auth_key'], 'tskey-client-abc'),
            'upper-case instance id': changed(['instance_id'], PAYLOAD['instance_id'].upper()),
            'plain HTTP bundle': changed(['host_bundle', 'url'], 'http://bucket/x.tar.gz'),
            'short digest': changed(['host_bundle', 'sha256'], 'a' * 63),
            'missing auth key': changed(['auth_key'], KeyError),
            'extra field': {**PAYLOAD, 'public_key': 'ssh-ed25519 AAAA'},
            'extra bundle field': changed(['host_bundle', 'path'], '/tmp/x'),
            'trailing newline': changed(['instance_id'], PAYLOAD['instance_id'] + '\n'),
        }
        for name, document in cases.items():
            with self.subTest(name), self.assertRaises(ValueError):
                schema.payload(document)

    def test_errors_never_repeat_payload_values(self):
        for document in (changed(['management_token'], TOKEN + '!'), changed(['version'], 3),
                         changed(['host_bundle', 'url'], 'ftp://secret-place')):
            with self.assertRaises(ValueError) as failure:
                schema.payload(document)
            message = str(failure.exception)
            self.assertNotIn('secret', message)
            self.assertNotIn(TOKEN, message)

    def test_rejects_keywords_it_does_not_check(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported schema keywords'):
            schema.check({'type': 'string', 'format': 'uuid'}, 'value')


class ResultSchema(unittest.TestCase):
    def test_accepts_a_result(self):
        self.assertEqual(schema.result(dict(RESULT)), RESULT)

    def test_rejects_out_of_range_inventory(self):
        for name, value in (('gpu_count', 0), ('gpu_count', 9), ('gpu_product', 'H100'), ('cpu', 1.5),
                            ('promotion', 'yes'), ('tailscale_ip', '10.0.0.1')):
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                schema.result({**RESULT, name: value})


if __name__ == '__main__':
    unittest.main()
