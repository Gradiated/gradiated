import subprocess
from pathlib import Path
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

    @patch('image_build.APT_MIRROR', 'http://mirror.example/ubuntu')
    @patch('image_build.subprocess.run')
    def test_unreachable_mirror_falls_back_to_original_sources(self, run):
        dockerfiles = []

        def build(arguments, **kwargs):
            dockerfiles.append(Path(arguments[arguments.index('-f') + 1]).read_text())
            return self.result('Failed to fetch http://mirror.example/ubuntu/dists/noble/InRelease '
                               'connection timed out') if len(dockerfiles) == 1 else self.result()

        run.side_effect = build
        lines = ['FROM ubuntu:24.04', 'RUN apt-get update']
        build_image('test', lines, '.', timeout=30)
        self.assertEqual(run.call_count, 2)
        self.assertIn('http://mirror.example/ubuntu', dockerfiles[0])
        self.assertEqual(dockerfiles[1], '\n'.join(lines) + '\n')
        self.assertLessEqual(run.call_args_list[1].kwargs['timeout'], run.call_args_list[0].kwargs['timeout'])

    @patch('image_build.APT_MIRROR', 'http://mirror.example/ubuntu')
    @patch('image_build.subprocess.run')
    def test_https_upgraded_mirror_is_recognized(self, run):
        run.side_effect = [self.result('Failed to fetch https://mirror.example/ubuntu/dists/noble/InRelease '
                                       'connection timed out'), self.result()]
        build_image('test', ['FROM ubuntu:24.04'], '.')
        self.assertEqual(run.call_count, 2)

    @patch('image_build.APT_MIRROR', 'http://mirror.example/ubuntu')
    @patch('image_build.subprocess.run')
    def test_other_mirror_network_failure_is_not_retried(self, run):
        error = 'Failed to fetch https://mirror.example/ubuntu-other/dists/noble/InRelease Network is unreachable'
        run.return_value = self.result(error)
        with self.assertRaisesRegex(AssertionError, 'Network is unreachable'):
            build_image('test', ['FROM ubuntu:24.04'], '.')
        self.assertEqual(run.call_count, 1)

    @patch('image_build.APT_MIRROR', 'http://mirror.example/ubuntu')
    @patch('image_build.subprocess.run')
    def test_original_archive_network_failure_is_not_retried(self, run):
        error = 'Failed to fetch http://mirror.example/ubuntu/dists/noble/InRelease Network is unreachable'
        run.return_value = self.result(error)
        with self.assertRaisesRegex(AssertionError, 'Network is unreachable'):
            build_image('test', ['FROM ubuntu:24.04'], '.')
        self.assertEqual(run.call_count, 2)

    @patch('image_build.APT_MIRROR', 'http://mirror.example/ubuntu')
    @patch('image_build.subprocess.run')
    def test_cache_and_mirror_recovery_have_a_shared_bounded_budget(self, run):
        run.side_effect = [self.result('snapshot abc does not exist: not found'),
                           self.result('Failed to fetch http://mirror.example/ubuntu/dists/noble/InRelease '
                                       'Temporary failure resolving'), self.result()]
        build_image('test', ['FROM ubuntu:24.04'], '.', timeout=30)
        self.assertEqual(run.call_count, 3)
        self.assertIn('--no-cache', run.call_args_list[2].args[0])


if __name__ == '__main__':
    unittest.main()
