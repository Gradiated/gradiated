import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import uuid

spec = importlib.util.spec_from_file_location('bootstrap', Path(__file__).with_name('bootstrap.py'))
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def payload(self):
        instance = str(uuid.uuid4())
        return {'instance_id': instance, 'management_token': 'synthetic_' + 'a' * 48,
                'config': {'instance_id': instance, 'gpu_uuids': ['GPU-one'],
                           'runtimes': {'a' * 64: {'image': 'model@sha256:' + 'a' * 64}}}}

    def test_defaults_to_the_real_gpu_inventory(self):
        payload = self.payload()
        del payload['config']['gpu_uuids']
        config = bootstrap.validate(payload, ['GPU-one', 'GPU-two'])
        self.assertEqual(config['gpu_uuids'], ['GPU-one', 'GPU-two'])
        self.assertEqual(config['token_file'], '/etc/gradiated/kubelet-management.token')

    def test_rejects_identity_device_and_runtime_mismatches(self):
        for field in ['instance', 'gpu', 'image', 'key']:
            payload = self.payload()
            if field == 'instance': payload['config']['instance_id'] = str(uuid.uuid4())
            if field == 'gpu': payload['config']['gpu_uuids'] = ['GPU-other']
            if field == 'image': payload['config']['runtimes']['a' * 64]['image'] = 'unpinned'
            if field == 'key': payload['management_token'] = 'short'
            with self.subTest(field=field), self.assertRaises(ValueError):
                bootstrap.validate(payload, ['GPU-one'])

    def test_refuses_to_bootstrap_over_a_running_pod(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pod = root / 'pods' / str(uuid.uuid4())
            pod.mkdir(parents=True)
            (pod / 'state.json').write_text('{}')
            with patch.object(bootstrap, 'ROOT', root), patch.object(bootstrap.subprocess, 'check_output') as inventory:
                with self.assertRaises(ValueError): bootstrap.enroll(self.payload())
                inventory.assert_not_called()

    def test_matching_bootstrap_resumes_active_workloads_without_rotating_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = self.payload()
            token = root / 'management.token'
            token.write_text(payload['management_token'])
            config = {**payload['config'], 'token_file': str(token)}
            config_path = root / 'config.json'
            config_path.write_text(json.dumps(config))
            pod = root / 'pods' / str(uuid.uuid4())
            pod.mkdir(parents=True)
            (pod / 'state.json').write_text('{}')
            marker = root / 'bundles' / ('a' * 64) / '.bundle-sha256'
            marker.parent.mkdir(parents=True)
            marker.write_text('a' * 64)
            with patch.object(bootstrap, 'ROOT', root), patch.object(bootstrap, 'CONFIG', config_path), patch.object(bootstrap, 'validate', return_value=config), patch.object(bootstrap.subprocess, 'check_output', return_value='GPU-one\n'), patch.object(bootstrap.subprocess, 'run') as run:
                bootstrap.enroll(payload)
                run.assert_called_once_with(['bash', '/opt/gradiated/bin/start-tailscale'], check=True, timeout=10)
                self.assertEqual(token.read_text(), payload['management_token'])
                changed = {**payload, 'management_token': 'different_' + 'a' * 48}
                with self.assertRaises(ValueError): bootstrap.enroll(changed)

    def test_private_configuration_refuses_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'target'
            target.write_text('preserved')
            link = Path(directory) / 'config'
            link.symlink_to(target)
            with self.assertRaises(OSError): bootstrap.private_json(link, {'secret': 'synthetic'})
            self.assertEqual(target.read_text(), 'preserved')


if __name__ == '__main__':
    unittest.main()
