import importlib.util
from pathlib import Path
import unittest
import base64
import json
import signal
import tempfile
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-host.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RuntimeUpdateTests(unittest.TestCase):
    def test_migration_only_reload_signals_the_existing_pid_one(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def mapped(value):
                return root / str(value).lstrip('/')
            config = {'instance_id': '019d5a4a-0000-7000-8000-000000000001',
                      'gpu_uuids': ['GPU-one'], 'runtimes': {'a' * 64: {}},
                      'token_file': '/etc/gradiated/kubelet-management.token'}
            state = mapped('/var/lib/gradiated-kubelet')
            state.mkdir(parents=True)
            bundle = state / 'bundles' / ('a' * 64)
            bundle.mkdir(parents=True)
            (bundle / '.bundle-sha256').write_text('a' * 64)
            (state / 'supervisor.json').write_text('{"pid":1,"birth":"42"}')
            proc = mapped('/proc/1')
            proc.mkdir(parents=True)
            (proc / 'stat').write_text('1 (python) ' + ' '.join(['S'] + ['0'] * 18 + ['42']))
            (proc / 'cmdline').write_bytes(b'python3\x00/opt/gradiated/kubelet/supervise.py\x00')
            mapped('/etc/gradiated').mkdir(parents=True)
            payload = {'instance_id': config['instance_id'], 'management_token': 'a' * 48,
                       'config': config, 'base_id': 'test-base', 'desmondd': base64.b64encode(b'binary').decode()}
            source = Path(__file__).resolve().parents[2] / 'product/inference/gpu'
            for name in ('host_state.py', 'host_bundle.py', 'host-agent.py', 'supervise.py'):
                payload[name] = (source / name).read_text()
            with patch.object(installer, 'Path', side_effect=mapped), \
                    patch.object(installer.subprocess, 'check_output', return_value='GPU-one\n'), \
                    patch.object(installer.os, 'kill') as kill, patch.object(installer.subprocess, 'Popen') as spawn:
                installer.install(payload)
            kill.assert_called_once_with(1, signal.SIGHUP)
            spawn.assert_not_called()
            recovery = mapped('/opt/gradiated/kubelet/recovery/host-agent.py')
            self.assertEqual(recovery.read_text(), payload['host-agent.py'])
            self.assertIn('host-launcher.py', mapped('/opt/gradiated/kubelet/host-agent.py').read_text())

    def test_preserves_active_profiles_and_allows_unused_profile_cleanup(self):
        previous = {'runtimes': {'a' * 64: {'cpu': '16'}, 'b' * 64: {'cpu': '32'}}}
        state = {'pod': {'spec': {'containers': [{'image': 'model@sha256:' + 'a' * 64}]}}}
        installer.validate_runtime_update(previous, {'runtimes': {'a' * 64: {'cpu': '16'}}}, [state])
        installer.validate_runtime_update(previous, {'runtimes': {'a' * 64: {'cpu': '16'}, 'b' * 64: {'hf_home': '/local/cache'}}}, [state])
        for config in [{'runtimes': {}}, {'runtimes': {'a' * 64: {'cpu': '32'}}}]:
            with self.assertRaises(ValueError): installer.validate_runtime_update(previous, config, [state])


if __name__ == '__main__':
    unittest.main()
