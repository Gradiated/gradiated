"""The gradiated-gpu scheduler reads its config only at startup, so its pod
template carries the config's sha256: editing the config must change the
annotation, which rolls the pods."""
import hashlib
import pathlib
import unittest

import yaml

MANIFEST = (pathlib.Path(__file__).resolve().parents[2]
            / 'infra/environments/prod/us-east-1/kubernetes/gpu-inference/gpu-scheduler.yaml')


class GpuSchedulerTest(unittest.TestCase):
    def test_pod_template_tracks_config(self):
        docs = {d['kind']: d for d in yaml.safe_load_all(MANIFEST.read_text())
                if d['kind'] in ('ConfigMap', 'Deployment')}
        config = docs['ConfigMap']['data']['config.yaml']
        annotation = docs['Deployment']['spec']['template']['metadata']['annotations']['gradiated.com/config-sha256']
        self.assertEqual(annotation, hashlib.sha256(config.encode()).hexdigest(),
                         'set gradiated.com/config-sha256 to the sha256 of config.yaml')


if __name__ == '__main__':
    unittest.main()
