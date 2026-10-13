import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('installer', Path(__file__).with_name('install-host.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class RuntimeUpdateTests(unittest.TestCase):
    def test_preserves_active_profiles_and_allows_unused_profile_cleanup(self):
        previous = {'runtimes': {'a' * 64: {'cpu': '16'}, 'b' * 64: {'cpu': '32'}}}
        state = {'pod': {'spec': {'containers': [{'image': 'model@sha256:' + 'a' * 64}]}}}
        installer.validate_runtime_update(previous, {'runtimes': {'a' * 64: {'cpu': '16'}}}, [state])
        installer.validate_runtime_update(previous, {'runtimes': {'a' * 64: {'cpu': '16'}, 'b' * 64: {'hf_home': '/local/cache'}}}, [state])
        for config in [{'runtimes': {}}, {'runtimes': {'a' * 64: {'cpu': '32'}}}]:
            with self.assertRaises(ValueError): installer.validate_runtime_update(previous, config, [state])


if __name__ == '__main__':
    unittest.main()
