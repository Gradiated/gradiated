import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2] / 'product/inference/gpu'
sys.path.insert(0, str(ROOT))
import host_state as state


class DurabilityTests(unittest.TestCase):
    def test_failed_commit_preserves_whole_record_and_cleans_temporary_files(self):
        for operation, call_number, expected in [('fsync', 1, 1), ('replace', 1, 1), ('fsync', 2, 2)]:
            with self.subTest(operation=operation, call_number=call_number), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'fence.json'
                state.atomic_json(path, {'epoch': 1})
                original = getattr(state.os, operation)
                calls = 0
                def failing(*args):
                    nonlocal calls
                    calls += 1
                    if calls == call_number:
                        raise OSError('injected storage failure')
                    return original(*args)
                with patch.object(state.os, operation, failing), self.assertRaises(OSError):
                    state.atomic_json(path, {'epoch': 2})
                self.assertEqual(json.loads(path.read_text()), {'epoch': expected})
                self.assertEqual(list(Path(directory).iterdir()), [path])
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_process_crash_before_or_after_replace_leaves_complete_record(self):
        for after, expected in [(False, 1), (True, 2)]:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'fence.json'
                state.atomic_json(path, {'epoch': 1})
                script = '''import os,sys
sys.path.insert(0,sys.argv[1])
import host_state as state
replace=state.os.replace
def crash(*args):
    if sys.argv[3]=='after':replace(*args)
    os._exit(91)
state.os.replace=crash
state.atomic_json(sys.argv[2],{'epoch':2})
'''
                result = subprocess.run([sys.executable, '-c', script, str(ROOT), str(path), 'after' if after else 'before'], timeout=5)
                self.assertEqual(result.returncode, 91)
                self.assertEqual(json.loads(path.read_text()), {'epoch': expected})

    def test_log_truncation_keeps_recent_bytes_and_existing_writer(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'task.log'
            path.write_bytes(b'a' * 128 + b'b' * 64)
            with path.open('ab') as writer:
                state.bound_log(path, 128)
                writer.write(b'new-record')
            self.assertEqual(path.read_bytes(), b'b' * 64 + b'new-record')

    def test_log_symlink_cannot_truncate_another_file(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'state.json'
            target.write_bytes(b'a' * 256)
            link = Path(directory) / 'task.log'
            link.symlink_to(target)
            with self.assertRaises(OSError):
                state.bound_log(link, 16)
            self.assertEqual(target.read_bytes(), b'a' * 256)


if __name__ == '__main__':
    unittest.main()
