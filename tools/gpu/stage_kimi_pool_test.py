import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('stage_kimi', Path(__file__).with_name('stage-kimi-pool.py'))
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


class KimiStageTests(unittest.TestCase):
    def setUp(self):
        self.models = {'other': {'runtime': 'existing', 'replicas': 3}}
        self.runtimes = {'existing': {'model_id': 'other/model'}}
        self.source = 'a' * 40
        self.digest = 'b' * 64
        self.base = 'ubuntu24-cuda13-amd64-v3'
        self.pins = {'hostBundle': {'baseId': self.base}}
        self.release = {'bundle': 'kimi-k31-pro', 'source': self.source, 'sha256': self.digest,
                        'runtimeProfiles': ['b300-tp8'],
                        'baseId': self.base, 'baseImage': 'example/base@sha256:' + 'c' * 64,
                        'url': f's3::https://{staging.BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{self.digest}.tar.gz'}
        self.hosts = [{'spec': {'instanceId': instance, 'provider': {'name': 'runpod'},
                               'inventory': {'gpuProduct': 'B300', 'gpuCount': 8, 'cpu': 97, 'memoryGiB': 1389}}}
                      for instance in sorted(staging.INSTANCES)]

    def stage(self, **updates):
        inputs = {'models': self.models, 'runtimes': self.runtimes, 'pins': self.pins,
                  'hosts': self.hosts, 'release': self.release, 'source': self.source}
        return staging.stage(**{**inputs, **updates})

    def test_limits_placement_and_existing_models_are_preserved(self):
        before = copy.deepcopy((self.models, self.runtimes))
        models, runtimes = self.stage()
        self.assertEqual(before, (self.models, self.runtimes))
        self.assertEqual(models['other'], self.models['other'])
        self.assertEqual(runtimes['existing'], self.runtimes['existing'])
        model, runtime = models['kimi-k31-pro'], runtimes[self.digest]
        self.assertEqual((model['replicas'], model['max_surge'], model['max_unavailable']), (1, 0, 1))
        self.assertTrue(model['allow_single_replica_unavailable'])
        expression = model['affinity']['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0]['matchExpressions'][0]
        self.assertEqual(set(expression['values']), staging.INSTANCES)
        self.assertEqual((runtime['gpus'], runtime['cpu'], runtime['memory']), (8, '80', '1024Gi'))
        self.assertEqual(runtime['hf_home'], '/var/lib/kimi-k31/hf')
        self.assertEqual(runtime['active_requests'], 2)
        self.assertEqual(model['autoscaling']['target_concurrency'], 2)
        runtime_spec = importlib.util.spec_from_file_location('kimi_runtime_config',
            staging.ROOT / 'product/inference/runtimes/kimi-k31/config.py')
        runtime_config = importlib.util.module_from_spec(runtime_spec)
        runtime_spec.loader.exec_module(runtime_config)
        self.assertEqual(runtime['active_requests'], runtime_config.ACTIVE_REQUESTS)
        self.assertNotIn('tokenizer_mode', runtime['release'])
        self.assertEqual(self.stage(models=models, runtimes=runtimes), (models, runtimes))

    def test_unqualified_releases_and_insufficient_hosts_are_rejected(self):
        for update in [{'source': 'd' * 40}, {'bundle': 'glm-5-3-flash-sglang'}, {'sha256': '../escape'},
                       {'baseId': 'wrong'}, {'baseImage': 'example/base:latest'}, {'runtimeProfiles': []},
                       {'url': 'https://untrusted.example/archive'}]:
            with self.subTest(update=update), self.assertRaises(ValueError):
                self.stage(release={**self.release, **update})
        with self.assertRaises(ValueError):
            self.stage(hosts=[])
        for field, value in [('gpuProduct', 'H200'), ('gpuCount', 4), ('cpu', 79), ('memoryGiB', 1023)]:
            hosts = copy.deepcopy(self.hosts)
            hosts[0]['spec']['inventory'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.stage(hosts=hosts)

    def test_existing_definitions_cannot_be_silently_replaced(self):
        models, runtimes = self.stage()
        models['kimi-k31-pro']['replicas'] = 2
        with self.assertRaisesRegex(ValueError, 'deployment differs'):
            self.stage(models=models)
        runtimes[self.digest]['active_requests'] = 3
        with self.assertRaisesRegex(ValueError, 'immutable definition'):
            self.stage(runtimes=runtimes)


if __name__ == '__main__':
    unittest.main()
