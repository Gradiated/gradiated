import importlib.util
from pathlib import Path
import subprocess
import unittest

spec = importlib.util.spec_from_file_location('rollout', Path(__file__).with_name('rollout-host.py'))
rollout = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rollout)


class RolloutTests(unittest.TestCase):
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
