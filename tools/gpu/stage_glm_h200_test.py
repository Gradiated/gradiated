import copy
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

spec = importlib.util.spec_from_file_location('stage_h200', Path(__file__).with_name('stage-glm-h200.py'))
stage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage)


class H200Staging(unittest.TestCase):
    def setUp(self):
        self.models = json.loads((stage.GPU / 'models.json').read_text())
        # Exercise staging from the B300-only catalogue, independent of a committed H200 pool.
        self.models.pop(stage.NAME, None)
        self.runtimes = json.loads((stage.ROOT / 'product/inference/gpu/runtimes.json').read_text())
        self.pins = json.loads((stage.GPU / 'pins.json').read_text())
        self.hosts = [host for host in yaml.safe_load_all((stage.GPU / 'hosts.yaml').read_text()) if host]
        host = copy.deepcopy(self.hosts[0])
        self.instance = '019d5a4a-0000-7000-8000-000000000001'
        host['spec']['instanceId'] = self.instance
        host['spec']['inventory'] = {'gpuProduct': 'H200', 'gpuCount': 2, 'cpu': 57, 'memoryGiB': 335}
        self.hosts.append(host)
        self.source = 'a' * 40
        digest = 'b' * 64
        self.release = {'source': self.source, 'bundle': 'glm-5-3-flash-sglang', 'sha256': digest,
                        'runtimeProfiles': ['b300-pcp2', 'h200-tp2'],
                        'baseId': self.pins['hostBundle']['baseId'], 'baseImage': 'registry/base@sha256:' + 'c' * 64,
                        'url': f's3::https://{stage.BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz'}

    def stage(self, **changes):
        return stage.stage(**{'models': self.models, 'runtimes': self.runtimes, 'pins': self.pins,
                              'hosts': self.hosts, 'release': self.release, 'source': self.source,
                              'instances': [self.instance], **changes})

    def test_stages_h200_without_changing_any_b300_model_or_runtime(self):
        before = copy.deepcopy((self.models, self.runtimes, self.pins, self.hosts))
        models, runtimes = self.stage()
        self.assertEqual((self.models, self.runtimes, self.pins, self.hosts), before)
        for name, model in self.models.items():
            self.assertEqual(models[name], model)
        for name, runtime in self.runtimes.items():
            self.assertEqual(runtimes[name], runtime)
        candidate = models[stage.NAME]
        self.assertEqual(candidate['serving_mode'], 'qualification')
        self.assertEqual(candidate['node_selector']['nvidia.com/gpu.product'], 'H200')
        runtime = runtimes[candidate['runtime']]
        self.assertEqual(runtime['environment']['GLM_SGLANG_PROFILE'], 'h200-tp2')
        self.assertEqual(runtime['memory'], '320Gi')
        self.assertNotEqual(candidate['runtime'], self.release['sha256'])
        self.assertEqual(list(runtime['bundles'].values()), [self.release['sha256']])
        self.assertEqual(self.stage(models=models, runtimes=runtimes), (models, runtimes))

    def test_only_exact_staged_profile_can_be_promoted(self):
        with self.assertRaisesRegex(ValueError, 'previously staged'):
            self.stage(promote=True)
        models, runtimes = self.stage()
        promoted, _ = self.stage(models=models, runtimes=runtimes, promote=True)
        self.assertEqual(promoted[stage.NAME]['serving_mode'], 'production')
        models[stage.NAME]['autoscaling']['max_replicas'] = 3
        with self.assertRaisesRegex(ValueError, 'previously staged'):
            self.stage(models=models, runtimes=runtimes, promote=True)

    def test_rejects_stale_artifacts_and_impossible_placement(self):
        for change in [{'source': 'd' * 40}, {'runtimeProfiles': ['b300-pcp2']}, {'sha256': 'bad'},
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

    def test_rendered_h200_rollout_preserves_qualification_and_resources(self):
        spec = importlib.util.spec_from_file_location('h200_renderer', Path(__file__).with_name('render-config.py'))
        renderer = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(renderer)
        models, runtimes = self.stage()
        renderer.validate_canaries(models, runtimes)
        rollout = renderer.rollout(stage.NAME, models[stage.NAME], runtimes)
        pod = rollout['spec']['template']
        self.assertEqual(pod['metadata']['annotations']['gradiated.com/serving-mode'], 'qualification')
        self.assertEqual(pod['spec']['containers'][0]['resources']['requests']['memory'], '320Gi')
        self.assertEqual(pod['spec']['nodeSelector']['nvidia.com/gpu.product'], 'H200')


if __name__ == '__main__':
    unittest.main()
