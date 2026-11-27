from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


class PackagedLaunchers(unittest.TestCase):
    def test_shared_launchers_start_with_qwen3_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'qwen3-sglang'
            runtime.mkdir()
            shared = HERE.parent / 'glm-sglang'
            # The built bundle already has these files beside its Qwen3 config.
            for name in ['launch.py', 'service.py']:
                source = HERE / name if (HERE / name).is_file() else shared / name
                shutil.copyfile(source, runtime / name)
            shutil.copyfile(HERE / 'config.py', runtime / 'config.py')
            warmup = HERE.parent / 'warmup-base.py'
            if not warmup.is_file():
                warmup = HERE.parent / 'glm/warmup-supervisor.py'
            shutil.copyfile(warmup, root / 'warmup-base.py')
            program = '''
from pathlib import Path
import sys
from unittest.mock import patch
import config
import launch
import service

environment = {'GRADIATED_RUNTIME_ROOT': str(Path.cwd().parent),
               'RUNTIME_PORT': '18080', 'WARMUP_PORT': '18083',
               'NVIDIA_VISIBLE_DEVICES': 'GPU-a'}
assert launch.qualification_records({'HOME': '/tmp/runtime'}) == Path('/tmp/runtime/.cache/qwen3-sglang/qualification')
with patch.object(launch, 'detect_profile', side_effect=lambda value: value), \
     patch.object(launch.Supervisor, 'run', return_value=0):
    assert launch.main(environment) == 0
assert launch.base.MODEL == config.MODEL

class ReachedBackend(Exception):
    pass

with patch.object(service, 'detect_profile', side_effect=lambda value: value), \
     patch.object(service, 'validate_hardware'), \
     patch.object(service.signal, 'signal'), \
     patch.object(service.subprocess, 'Popen', side_effect=ReachedBackend):
    try:
        service.run(environment)
    except ReachedBackend:
        pass
    else:
        raise AssertionError('Qwen3 service did not reach engine startup')
'''
            result = subprocess.run([sys.executable, '-c', program], cwd=runtime,
                                    capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
