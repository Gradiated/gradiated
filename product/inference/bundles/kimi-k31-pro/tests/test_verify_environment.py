"""Exercise the Docker verification shell without importing CUDA or Torch."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class VerificationEnvironment(unittest.TestCase):
    def test_every_verification_interpreter_inherits_runtime_libraries(self):
        here = Path(__file__).resolve().parent
        # The image carries an adjacent copy; the repository owns the file one
        # directory above these tests. Missing fixtures remain a hard failure.
        dockerfile = here / 'Dockerfile'
        if not dockerfile.exists():
            dockerfile = here.parent / 'Dockerfile'
        text = dockerfile.read_text()
        step = re.search(r'RUN --mount=from=package[^\n]*\n((?:.*\\\n)*.*)', text).group(1)
        step = step.replace('\\\n', ' ')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / 'bundle'
            tools = root / 'tools'
            tools.mkdir()
            (tools / 'tar').write_text('#!/bin/sh\nexit 0\n')
            (tools / 'tar').chmod(0o755)
            python = bundle / 'python/bin/python3'
            # The real step creates /bundle; let it see an existing directory.
            # Its Python calls execute a stand-in that verifies the inherited
            # loader environment in every invocation.
            python.parent.mkdir(parents=True)
            python.write_text(
                '#!/bin/sh\n'
                '[ "$CUDA_HOME" = "$EXPECTED_CUDA_HOME" ] || exit 91\n'
                '[ "$LD_LIBRARY_PATH" = "$EXPECTED_LD_LIBRARY_PATH" ] || exit 92\n'
                'echo "$*" >> "$VERIFY_CALLS"\n'
            )
            python.chmod(0o755)
            step = step.replace('mkdir /bundle', 'mkdir -p /bundle')
            step = step.replace('/bundle', str(bundle)).replace('/verified', str(root / 'verified'))
            environment = {key: value for key, value in os.environ.items()
                           if key not in ('LD_LIBRARY_PATH', 'CUDA_HOME')}
            environment.update(
                PATH=str(tools) + ':' + environment['PATH'],
                EXPECTED_CUDA_HOME=str(bundle / 'cuda'),
                EXPECTED_LD_LIBRARY_PATH=':'.join(str(bundle / path) for path in
                    ('python/lib', 'cuda/lib64', 'python/lib/python3.12/site-packages/torch/lib')),
                VERIFY_CALLS=str(root / 'calls'),
            )
            subprocess.run(['sh', '-ec', step], env=environment, check=True, capture_output=True)
            calls = (root / 'calls').read_text().splitlines()
            self.assertEqual(len(calls), 4)
            self.assertIn('verify-build.py', calls[0])
            self.assertIn('unittest discover', calls[1])
            self.assertIn('unittest discover', calls[2])
            self.assertIn('/energy', calls[3])
            self.assertTrue((root / 'verified').exists())


if __name__ == '__main__':
    unittest.main()
