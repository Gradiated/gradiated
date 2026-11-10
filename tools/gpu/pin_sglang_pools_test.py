import copy
import importlib.util
import json
from pathlib import Path
import unittest

import yaml

spec = importlib.util.spec_from_file_location('pin_pools', Path(__file__).with_name('pin-sglang-pools.py'))
pin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin)
render_spec = importlib.util.spec_from_file_location('render_config', Path(__file__).with_name('render-config.py'))
render = importlib.util.module_from_spec(render_spec)
render_spec.loader.exec_module(render)


class SGLangPins(unittest.TestCase):
    def setUp(self):
        self.models = json.loads((pin.GPU / 'models.json').read_text())
        self.runtimes = json.loads(pin.RUNTIMES.read_text())
        self.pins = json.loads((pin.GPU / 'pins.json').read_text())
        self.hosts = [host for host in yaml.safe_load_all((pin.GPU / 'hosts.yaml').read_text()) if host]
        self.source = 'a' * 40
        self.releases = {}
        for bundle, digest, profiles in [('glm-5-3-flash-sglang', 'b' * 64, ['b300-pcp2', 'h200-tp2', 'b200-pcp2']),
                                         ('deepseek-v4-1-flash-sglang', 'c' * 64, ['b300-tp4'])]:
            self.releases[bundle] = {
                'bundle': bundle, 'source': self.source, 'sha256': digest, 'runtimeProfiles': profiles,
                'baseId': self.pins['hostBundle']['baseId'], 'baseImage': 'registry/base@sha256:' + 'd' * 64,
                'url': f's3::https://{pin.BUCKET}.s3.us-east-1.amazonaws.com/bundles/sha256/{digest}.tar.gz'}

    def pin(self, **changes):
        return pin.pin(**{'model_catalog': self.models, 'runtimes': self.runtimes, 'pins': self.pins,
                          'releases': self.releases, 'source': self.source, **changes})

    def test_pools_move_to_sglang_runtimes_and_keep_rollback(self):
        before = copy.deepcopy((self.models, self.runtimes))
        models, runtimes = self.pin()
        self.assertEqual((self.models, self.runtimes), before)
        self.assertTrue(set(self.runtimes) <= set(runtimes))
        self.assertNotIn('deepseek/deepseek-v4.1-flash', models)
        for model_id, pool_name, digest, gpus in [('z-ai/glm-5.3-flash', 'glm', 'b' * 64, 2),
                                                  ('deepseek/deepseek-v4.1-flash-1017', 'deepseek', 'c' * 64, 4)]:
            pool = models[model_id]['pools'][pool_name]
            runtime = runtimes[pool['runtime']]
            self.assertEqual(runtime['image'].rsplit('@sha256:', 1)[1], pool['runtime'])
            self.assertEqual(runtime['bundles'], {self.pins['hostBundle']['baseId']: digest})
            self.assertEqual((runtime['model_id'], runtime['gpus'], pool['max_replicas']), (model_id, gpus, 1))
            self.assertEqual(runtime['environment']['LORA_ENABLED'], 'true')
            self.assertNotIn('slots', pool)
            self.assertNotIn('gpu_count', pool)
        self.assertEqual(models['z-ai/glm-5.3-flash']['pools']['glm']['spread'], 'required')
        glm = runtimes[models['z-ai/glm-5.3-flash']['pools']['glm']['runtime']]
        self.assertEqual(glm['release']['model_path'], 'nvidia/GLM-5.3-Flash-NVFP4')
        self.assertEqual(glm['release']['runtime_model_name'], 'zai-org/GLM-5.3-Flash')
        # The rendered plan accepts the pinned catalogues.
        hosts, _ = render.inventory(self.hosts)
        pools = render.plan(models, runtimes, hosts)
        render.validate_active_requests(pools, runtimes, render.glm_sglang_profiles())

    def test_mismatched_release_or_source_is_rejected(self):
        for bundle, change in [('glm-5-3-flash-sglang', {'source': 'e' * 40}),
                               ('deepseek-v4-1-flash-sglang', {'runtimeProfiles': []}),
                               ('glm-5-3-flash-sglang', {'baseId': 'other'}),
                               ('deepseek-v4-1-flash-sglang', {'url': 's3::https://elsewhere/x.tar.gz'}),
                               ('deepseek-v4-1-flash-sglang', {'bundle': 'glm-5-3-flash-sglang'})]:
            releases = copy.deepcopy(self.releases)
            releases[bundle].update(change)
            with self.subTest(bundle=bundle, change=change), self.assertRaises((ValueError, KeyError)):
                self.pin(releases=releases)

    def test_render_rejects_a_deepseek_runtime_that_drifts_from_its_launcher(self):
        models, runtimes = self.pin()
        runtime = models['deepseek/deepseek-v4.1-flash-1017']['pools']['deepseek']['runtime']
        runtimes[runtime]['active_requests'] += 1
        hosts, _ = render.inventory(self.hosts)
        with self.assertRaisesRegex(ValueError, 'DeepSeek launcher profile'):
            render.validate_active_requests(render.plan(models, runtimes, hosts), runtimes, render.glm_sglang_profiles())

    def test_repinning_is_idempotent(self):
        models, runtimes = self.pin()
        again = pin.pin(models, runtimes, self.pins, self.releases, self.source)
        self.assertEqual(again, (models, runtimes))


if __name__ == '__main__':
    unittest.main()
