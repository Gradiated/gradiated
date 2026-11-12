import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('stage_kimi', Path(__file__).with_name('stage-kimi-pool.py'))
staging = importlib.util.module_from_spec(spec)
spec.loader.exec_module(staging)


class KimiStageTests(unittest.TestCase):
    def setUp(self):
        self.models = {'other/model': {'min_slots': 3, 'pools': {'other': {'runtime': 'existing', 'max_replicas': 3}}}}
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
                                'extraTaints': [dict(staging.RESERVATION)],
                               'inventory': {'gpuProduct': 'B300', 'gpuCount': 8, 'cpu': 97, 'memoryGiB': 1389}}}
                      for instance in ('01a0fbf7-5276-700b-903b-7e04da150ed6', '01a0fbf8-06fc-7658-96e1-ae72f7dba135')]
        # Unreserved hosts, even matching ones, never take Kimi.
        self.hosts.append({'spec': {'instanceId': '019d5a4a-0000-7000-8000-000000000001', 'provider': {'name': 'runpod'},
                                    'inventory': {'gpuProduct': 'B300', 'gpuCount': 8, 'cpu': 97, 'memoryGiB': 1389}}})

    def stage(self, **updates):
        inputs = {'models': self.models, 'runtimes': self.runtimes, 'pins': self.pins,
                  'hosts': self.hosts, 'release': self.release, 'source': self.source}
        return staging.stage(**{**inputs, **updates})

    def test_limits_placement_and_existing_models_are_preserved(self):
        before = copy.deepcopy((self.models, self.runtimes))
        models, runtimes = self.stage()
        self.assertEqual(before, (self.models, self.runtimes))
        self.assertEqual(models['other/model'], self.models['other/model'])
        self.assertEqual(runtimes['existing'], self.runtimes['existing'])
        model, runtime = models[staging.MODEL], runtimes[self.digest]
        # Both replicas stay warm: ten slots fill the two reserved hosts.
        self.assertEqual(model['min_slots'], 10)
        pool = model['pools']['kimi-k31-pro']
        self.assertEqual((pool['max_replicas'], pool['max_surge'], pool['max_unavailable']), (2, 1, 1))
        # The host reservation places Kimi; the pool names no hosts.
        self.assertEqual((pool['gpu'], pool['gpu_count'], pool['reservation']), ('B300', 8, 'kimi-k31'))
        self.assertNotIn('affinity', pool)
        self.assertEqual((runtime['gpus'], runtime['cpu'], runtime['memory']), (8, '80', '1000Gi'))
        self.assertEqual(runtime['hf_home'], '/var/lib/kimi-k31/hf')
        self.assertEqual(runtime['active_requests'], 5)
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
        for index in range(2):
            with self.subTest(missing=index), self.assertRaises(ValueError):
                self.stage(hosts=self.hosts[:index] + self.hosts[index + 1:])
            hosts = copy.deepcopy(self.hosts)
            hosts[index]['spec']['extraTaints'] = []
            with self.subTest(untainted=index), self.assertRaisesRegex(ValueError, 'reservation taint'):
                self.stage(hosts=hosts)
        for field, value in [('gpuProduct', 'H200'), ('gpuCount', 4), ('cpu', 79), ('memoryGiB', 1023)]:
            hosts = copy.deepcopy(self.hosts)
            hosts[0]['spec']['inventory'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.stage(hosts=hosts)

    def test_staged_pool_renders_on_the_reserved_hosts_only(self):
        spec = importlib.util.spec_from_file_location('kimi_renderer', Path(__file__).with_name('render-config.py'))
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        documents = [item for item in renderer.yaml.safe_load_all((renderer.GPU / 'hosts.yaml').read_text()) if item]
        models, runtimes = self.stage(hosts=documents, models={}, runtimes={})
        hosts, _ = renderer.inventory(documents)
        pool = renderer.plan(models, runtimes, hosts)['kimi-k31-pro']
        self.assertEqual((pool['floor'], pool['maximum'], pool['slots']), (2, 2, 5))
        affinity = renderer.rollout('kimi-k31-pro', pool, runtimes)['spec']['template']['spec']['affinity']
        expression, = affinity['nodeAffinity']['requiredDuringSchedulingIgnoredDuringExecution']['nodeSelectorTerms'][0]['matchExpressions']
        self.assertEqual(expression['values'], ['01a0fbf7-5276-700b-903b-7e04da150ed6', '01a0fbf8-06fc-7658-96e1-ae72f7dba135'])

    def test_existing_definitions_cannot_be_silently_replaced(self):
        models, runtimes = self.stage()
        models[staging.MODEL]['pools']['kimi-k31-pro']['max_replicas'] = 3
        with self.assertRaisesRegex(ValueError, 'deployment differs'):
            self.stage(models=models)
        runtimes[self.digest]['active_requests'] = 6
        with self.assertRaisesRegex(ValueError, 'immutable definition'):
            self.stage(runtimes=runtimes)


if __name__ == '__main__':
    unittest.main()
