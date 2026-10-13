import importlib.util
from pathlib import Path
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('rollout', Path(__file__).with_name('rollout-host.py'))
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)
pin_spec = importlib.util.spec_from_file_location('pin_host', Path(__file__).with_name('pin-host.py'))
pin_host = importlib.util.module_from_spec(pin_spec)
pin_spec.loader.exec_module(pin_host)


class RolloutTests(unittest.TestCase):
    def test_host_pin_cannot_select_a_model_runtime_artifact(self):
        release = {'sha256': 'a' * 64, 'baseId': 'base', 'bundle': 'host'}
        self.assertEqual(pin_host.pin(release), {'sha256': 'a' * 64, 'base_id': 'base'})
        with self.assertRaises(ValueError):
            pin_host.pin({**release, 'bundle': 'training'})

    def test_stops_on_first_failure(self):
        called = []
        def run(command, **kwargs):
            called.append(command)
            raise subprocess.CalledProcessError(1, command)
        with self.assertRaises(subprocess.CalledProcessError):
            rollout.rollout([{'instance_id': 'first', 'ssh': 'root@gpu-a'},
                             {'instance_id': 'second', 'ssh': 'root@gpu-b'}], b'binary', 'base', run)
        self.assertEqual(len(called), 1)

    def test_rejects_ssh_option_injection(self):
        with self.assertRaises(ValueError):
            rollout.rollout([{'instance_id': 'first', 'ssh': '-oProxyCommand=evil'}], b'binary', 'base')


if __name__ == '__main__':
    unittest.main()
