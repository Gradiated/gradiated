import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('download', Path(__file__).with_name('download-runtime.py'))
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


class PrivateDownloadTests(unittest.TestCase):
    def test_signed_get_ranges_work_without_an_aws_key_or_url_in_argv(self):
        grant = 'https://bucket.s3.us-east-1.amazonaws.com/bundle?X-Amz-Signature=synthetic'
        response = io.BytesIO(json.dumps({'url': grant}).encode())
        archive = b'synthetic-runtime-data'
        commands = []
        def curl(command, **options):
            commands.append(command)
            self.assertNotIn(grant, command)
            self.assertNotIn('--head', command)
            self.assertIn(grant, options['input'].decode())
            if '--write-out' in command:
                return subprocess.CompletedProcess(command, 0, f'bytes 0-0/{len(archive)}'.encode())
            start, end = map(int, command[command.index('--range') + 1].split('-'))
            options['stdout'].write(archive[start:end + 1])
            return subprocess.CompletedProcess(command, 0)
        with tempfile.TemporaryDirectory() as directory, patch('urllib.request.urlopen', return_value=response), patch.object(download.subprocess, 'run', side_effect=curl):
            target = Path(directory) / 'bundle'
            download.download('https://bucket.s3.us-east-1.amazonaws.com/bundles/sha256/' + 'a' * 64 + '.tar.gz', target)
            self.assertEqual(target.read_bytes(), archive)
        self.assertGreater(len(commands), 1)


if __name__ == '__main__':
    unittest.main()
