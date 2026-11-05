import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

spec = importlib.util.spec_from_file_location('stage_pool', Path(__file__).with_name('stage-glm-pool.py'))
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class H200Staging(unittest.TestCase):
    GPU, PRODUCT, PROFILE, ACTIVE = 'h200', 'H200', 'h200-tp2', 4

    def setUp(self):
        self.name = stage.name(self.GPU)
        self.models = json.loads((stage.GPU / 'models.json').read_text())
        # Exercise staging from the B300-only catalogue, independent of any committed pool.
        for gpu in stage.POOLS:
            self.models.pop(stage.name(gpu), None)
        self.runtimes = json.loads((stage.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        self.pins = json.loads((stage.GPU / 'pins.json').read_text())
        self.hosts = [host for host in yaml.safe_load_all((stage.GPU / 'hosts.yaml').read_text()) if host]
        host = copy.deepcopy(self.hosts[0])
        self.instance = '019d5a4a-0000-7000-8000-000000000001'
        host['spec']['instanceId'] = self.instance
        host['spec']['inventory'] = {'gpuProduct': self.PRODUCT, 'gpuCount': 2, 'cpu': 57, 'memoryGiB': 335}
        self.hosts.append(host)
        self.source = 'a' * 40
        digest = 'b' * 64
        self.release = {'source': self.source, 'bundle': 'glm-5-3-flash-sglang', 'sha256': digest,
                        'runtimeProfiles': ['b300-pcp2', 'h200-tp2', 'b200-pcp2'],
                        'baseId': self.pins['hostBundle']['baseId'], 'baseImage': 'registry/base@sha256:' + 'c' * 64,
                        'url': f's3::https://{stage.BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz'}

    def stage(self, **changes):
        return stage.stage(**{'models': self.models, 'runtimes': self.runtimes, 'pins': self.pins,
                              'hosts': self.hosts, 'release': self.release, 'source': self.source,
                              'instances': [self.instance], 'gpu': self.GPU, **changes})

    def test_stages_pool_without_changing_any_b300_model_or_runtime(self):
        before = copy.deepcopy((self.models, self.runtimes, self.pins, self.hosts))
        models, runtimes = self.stage()
        self.assertEqual((self.models, self.runtimes, self.pins, self.hosts), before)
        for name, model in self.models.items():
            self.assertEqual(models[name], model)
        for name, runtime in self.runtimes.items():
            self.assertEqual(runtimes[name], runtime)
        candidate = models[self.name]
        self.assertEqual(candidate['serving_mode'], 'qualification')
        self.assertEqual(candidate['node_selector']['nvidia.com/gpu.product'], self.PRODUCT)
        self.assertEqual(candidate['autoscaling']['target_concurrency'], self.ACTIVE)
        runtime = runtimes[candidate['runtime']]
        # Host agents reject unlisted environment variables, so the profile is detected from the GPUs.
        self.assertEqual(runtime['environment'], {'TENSOR_PARALLEL_SIZE': '2'})
        self.assertEqual(runtime['model_id'], f'{stage.MODEL}-sglang-{self.GPU}')
        self.assertEqual(runtime['memory'], '320Gi')
        self.assertNotEqual(candidate['runtime'], self.release['sha256'])
        self.assertEqual(list(runtime['bundles'].values()), [self.release['sha256']])
        self.assertEqual(self.stage(models=models, runtimes=runtimes), (models, runtimes))

    def test_only_exact_staged_profile_can_be_promoted(self):
        with self.assertRaisesRegex(ValueError, 'previously staged'):
            self.stage(promote=True)
        models, runtimes = self.stage()
        promoted, _ = self.stage(models=models, runtimes=runtimes, promote=True)
        self.assertEqual(promoted[self.name]['serving_mode'], 'production')
        models[self.name]['autoscaling']['max_replicas'] = 3
        with self.assertRaisesRegex(ValueError, 'previously staged'):
            self.stage(models=models, runtimes=runtimes, promote=True)

    def test_rejects_stale_artifacts_and_impossible_placement(self):
        for change in [{'source': 'd' * 40}, {'runtimeProfiles': [p for p in self.release['runtimeProfiles'] if p != self.PROFILE]}, {'sha256': 'bad'},
                       {'baseId': 'other-base'}, {'url': 's3::https://other/archive'}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.stage(release={**self.release, **change})
        for change in [{'gpuProduct': 'B300'}, {'gpuCount': 1}, {'memoryGiB': 300}, {'cpu': 16}]:
            hosts = copy.deepcopy(self.hosts)
            hosts[-1]['spec']['inventory'].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.stage(hosts=hosts)
        for changes in [{'instances': []}, {'instances': [self.instance, self.instance]},
                        {'instances': ['019d5a4a-0000-7000-8000-000000000002']}, {'replicas': 3}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.stage(**changes)

    def test_rendered_rollout_preserves_qualification_and_resources(self):
        spec = importlib.util.spec_from_file_location('pool_renderer', Path(__file__).with_name('render-config.py'))
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        models, runtimes = self.stage()
        renderer.validate_canaries(models, runtimes)
        rollout = renderer.rollout(self.name, models[self.name], runtimes)
        pod = rollout['spec']['template']
        self.assertEqual(pod['metadata']['annotations']['gradiated.com/serving-mode'], 'qualification')
        self.assertEqual(pod['spec']['containers'][0]['resources']['requests']['memory'], '320Gi')
        self.assertEqual(pod['spec']['nodeSelector']['nvidia.com/gpu.product'], self.PRODUCT)

class CommittedPools(unittest.TestCase):
    def test_generalised_helper_reproduces_the_committed_h200_runtime_key(self):
        runtimes = json.loads((stage.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        h200 = [(key, runtime) for key, runtime in runtimes.items()
                if runtime.get('model_id') == f'{stage.MODEL}-sglang-h200']
        self.assertTrue(h200)
        for key, runtime in h200:
            bundle, = runtime['bundles'].values()
            self.assertEqual(hashlib.sha256(f'{bundle}:h200-tp2'.encode()).hexdigest(), key)
            self.assertEqual(runtime['model_id'], f'{stage.MODEL}-sglang-h200')
            self.assertEqual(runtime['release']['runtime_revision'], f'glm-h200-{bundle[:12]}')


class B200Staging(H200Staging):
    GPU, PRODUCT, PROFILE, ACTIVE = 'b200', 'B200', 'b200-pcp2', 8

    def test_b200_pool_is_separate_from_h200(self):
        models, runtimes = self.stage()
        self.assertNotIn(stage.name('h200'), models)
        self.assertNotEqual(models[self.name]['runtime'], hashlib.sha256(f"{'b' * 64}:h200-tp2".encode()).hexdigest())
        with self.assertRaisesRegex(ValueError, 'H200 profile requires'):
            self.stage(gpu='h200')

    def test_staged_runtime_declares_its_launcher_active_request_limit(self):
        models, runtimes = self.stage()
        self.assertEqual(runtimes[models[self.name]['runtime']]['active_requests'], 8)
        renderer = importlib.util.spec_from_file_location('render_config', Path(stage.__file__).with_name('render-config.py'))
        render = importlib.util.module_from_spec(renderer)
        renderer.loader.exec_module(render)
        render.validate_active_requests({self.name: models[self.name]}, runtimes, render.glm_sglang_profiles())


if __name__ == '__main__':
    unittest.main()
