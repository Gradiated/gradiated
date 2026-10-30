import subprocess
import unittest
from unittest.mock import patch
from image_build import build_image


class BuildRetryTest(unittest.TestCase):
    def result(self, error=''):
        return subprocess.CompletedProcess([], bool(error), '', error)

    @patch('image_build.subprocess.run')
    def test_missing_builder_snapshot_retries_once_without_cache(self, run):
        run.side_effect = [self.result('snapshot abc does not exist: not found'), self.result()]
        build_image('test', ['FROM scratch'], '.', timeout=30)
        self.assertEqual(run.call_count, 2)
        self.assertNotIn('--no-cache', run.call_args_list[0].args[0])
        self.assertIn('--no-cache', run.call_args_list[1].args[0])
        self.assertLessEqual(run.call_args_list[1].kwargs['timeout'], run.call_args_list[0].kwargs['timeout'])

    @patch('image_build.subprocess.run')
    def test_real_build_failure_is_not_retried(self, run):
        run.return_value = self.result('compilation failed')
        with self.assertRaisesRegex(AssertionError, 'compilation failed'):
            build_image('test', [], '.')
        self.assertEqual(run.call_count, 1)

    @patch('image_build.subprocess.run')
    def test_repeated_snapshot_failure_stops_after_one_retry(self, run):
        run.return_value = self.result('snapshot abc does not exist: not found')
        with self.assertRaisesRegex(AssertionError, 'snapshot abc'):
            build_image('test', [], '.')
        self.assertEqual(run.call_count, 2)


if __name__ == '__main__':
    unittest.main()
