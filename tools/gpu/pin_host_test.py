import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('pin_host', Path(__file__).with_name('pin-host.py'))
pin_host = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pin_host)


class PinHostTest(unittest.TestCase):
    def test_host_pin_cannot_select_a_model_runtime_artifact(self):
        release = {'sha256': 'a' * 64, 'baseId': 'base', 'bundle': 'host'}
        self.assertEqual(pin_host.pin(release), {'sha256': 'a' * 64, 'base_id': 'base'})
        with self.assertRaises(ValueError):
            pin_host.pin({**release, 'bundle': 'training'})


if __name__ == '__main__':
    unittest.main()
