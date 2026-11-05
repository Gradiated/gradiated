import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare_enrollment', Path(__file__).with_name('prepare-enrollment.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class BootstrapPreparation(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.package = self.root / 'opt/gradiated/lib/gradiated_host'
        self.package.mkdir(parents=True)
        (self.package / 'enroll.py').write_text('OLD = True\n')
        (self.package / 'enrollment-result.schema.json').write_text('{}\n')
        (self.root / 'etc/gradiated').mkdir(parents=True)
        (self.root / 'etc/gradiated/tailscale.json').write_text('{"pod":"h200pod"}')
        self.document = {'pod': 'h200pod', 'source': 'a' * 40, 'product': 'H200',
                         'files': {'enroll.py': 'H200 = True\n', 'enrollment-result.schema.json': '{"new":true}\n'}}

    def run_remote(self, names='NVIDIA H200\nNVIDIA H200\n', busy=''):
        real_path = Path
        def path(value):
            original = real_path(value)
            return self.root / str(original).lstrip('/') if original.is_absolute() else original
        with patch('pathlib.Path', side_effect=path), patch('os.geteuid', return_value=0), \
             patch('sys.stdin', io.StringIO(json.dumps(self.document))), \
             patch('subprocess.check_output', side_effect=[names, busy]), contextlib.redirect_stdout(io.StringIO()):
            exec(compile(prepare.REMOTE, 'bootstrap-preparation', 'exec'), {})

    def test_prepares_only_enrollment_files_with_backups_and_is_idempotent(self):
        self.run_remote()
        self.run_remote()
        self.assertEqual((self.package / 'enroll.py').read_text(), 'H200 = True\n')
        self.assertEqual((self.package / 'enroll.py.before-h200').read_text(), 'OLD = True\n')
        self.assertEqual((self.package / 'enroll.py').stat().st_mode & 0o777, 0o644)
        self.assertFalse((self.root / 'etc/gradiated/kubelet.json').exists())

    def test_refuses_wrong_product_or_active_workloads_before_writes(self):
        for names, busy in [('NVIDIA GH200\nNVIDIA GH200\n', ''), ('NVIDIA H200\nNVIDIA H200\n', '1234')]:
            with self.subTest(names=names, busy=busy), self.assertRaises(SystemExit):
                self.run_remote(names, busy)
            self.assertEqual((self.package / 'enroll.py').read_text(), 'OLD = True\n')

    def test_b200_preparation_requires_b200_gpus(self):
        self.document['product'] = 'B200'
        for names in ['NVIDIA H200\nNVIDIA H200\n', 'NVIDIA GB200\nNVIDIA GB200\n', 'NVIDIA B300\nNVIDIA B300\n']:
            with self.subTest(names=names), self.assertRaisesRegex(SystemExit, 'B200'):
                self.run_remote(names)
        self.run_remote('NVIDIA B200\nNVIDIA B200\n')
        self.assertEqual((self.package / 'enroll.py.before-b200').read_text(), 'OLD = True\n')

    def test_refuses_unsupported_product_before_reading_source(self):
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            prepare.payload('pod', 'a' * 40, 'B300')

    def test_refuses_already_enrolled_or_wrong_bootstrap_identity(self):
        (self.root / 'etc/gradiated/kubelet.json').write_text('{}')
        with self.assertRaisesRegex(SystemExit, 'already enrolled'):
            self.run_remote()
        (self.root / 'etc/gradiated/kubelet.json').unlink()
        self.document['pod'] = 'otherpod'
        with self.assertRaisesRegex(SystemExit, 'identity'):
            self.run_remote()


if __name__ == '__main__':
    unittest.main()
