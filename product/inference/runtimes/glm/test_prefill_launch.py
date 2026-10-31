import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ENTRYPOINT = Path(__file__).resolve().parents[2] / 'bundles/glm-5-3-flash/entrypoint'


class PrefillLaunchTests(unittest.TestCase):
    def launch(self, budget=None, queue_tokens=None, queue_requests=None, request_threshold=None,
               prefix_unit=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / 'python/bin/python3'
            executable.parent.mkdir(parents=True)
            executable.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$TEST_ARGS"\n')
            executable.chmod(0o755)
            args_path = root / 'args'
            env = {**os.environ, 'GRADIATED_RUNTIME_ROOT': directory,
                   'NVIDIA_VISIBLE_DEVICES': 'GPU-test', 'RUNTIME_PORT': '28100',
                   'WARMUP_PORT': '28101', 'LORA_ENABLED': 'false', 'TEST_ARGS': str(args_path)}
            for name in ('GLM_PREFILL_TOKEN_BUDGET', 'GLM_LONG_PREFILL_TOKEN_THRESHOLD', 'GLM_PREFIX_MATCH_UNIT',
                         'MAX_QUEUED_TOKENS', 'MAX_QUEUED_REQUESTS'):
                env.pop(name, None)
            if prefix_unit is not None:
                env['GLM_PREFIX_MATCH_UNIT'] = prefix_unit
            if request_threshold is not None:
                env['GLM_LONG_PREFILL_TOKEN_THRESHOLD'] = request_threshold
            if queue_tokens is not None:
                env['MAX_QUEUED_TOKENS'] = queue_tokens
            if queue_requests is not None:
                env['MAX_QUEUED_REQUESTS'] = queue_requests
            if budget is not None:
                env['GLM_PREFILL_TOKEN_BUDGET'] = budget
            result = subprocess.run(['bash', str(ENTRYPOINT)], env=env, capture_output=True, text=True)
            return result, args_path.read_text().splitlines() if args_path.exists() else []

    def test_default_preserves_runtime_scheduler_defaults(self):
        result, args = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('--max-num-batched-tokens', args)
        self.assertNotIn('--enable-chunked-prefill', args)
        self.assertNotIn('--long-prefill-token-threshold', args)
        self.assertNotIn('--prefix-match-unit', args)
        self.assertNotIn('--enable-mamba-fine-grained-prefix-cache', args)
        self.assertEqual(args[args.index('--max-num-seqs') + 1], '4')

    def test_budget_enables_chunking_without_changing_sequence_limit(self):
        result, args = self.launch('2048')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--enable-chunked-prefill', args)
        self.assertEqual(args[args.index('--max-num-batched-tokens') + 1], '2048')
        self.assertEqual(args[args.index('--max-num-seqs') + 1], '4')

    def test_budget_can_equal_the_sequence_limit(self):
        result, args = self.launch('4')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--max-num-batched-tokens') + 1], '4')

    def test_per_request_threshold_preserves_the_total_budget_unless_explicit(self):
        result, args = self.launch(request_threshold='2048')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--long-prefill-token-threshold')+1], '2048')
        self.assertNotIn('--max-num-batched-tokens', args)
        self.assertEqual(args.count('--enable-chunked-prefill'), 1)
        result, args = self.launch('16384', request_threshold='2048', queue_tokens='32768', queue_requests='4')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--max-num-batched-tokens')+1], '16384')
        self.assertEqual(args.count('--enable-chunked-prefill'), 1)
        result, args = self.launch(request_threshold='1048576')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--long-prefill-token-threshold')+1], '1048576')

    def test_invalid_per_request_thresholds_fail_before_launch(self):
        for value in ('0', '-1', '1.5', '2048 extra', '1048577', '9'*30):
            with self.subTest(value=value):
                result, args = self.launch(request_threshold=value)
                self.assertEqual(result.returncode, 64)
                self.assertFalse(args)

    def test_prefix_matching_unit_is_independent_of_the_physical_block_flag(self):
        result, args = self.launch(prefix_unit='128')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--prefix-match-unit')+1], '128')
        self.assertEqual(args[args.index('--block-size')+1], '128')
        self.assertIn('--enable-prefix-caching', args)
        self.assertIn('--enable-mamba-fine-grained-prefix-cache', args)
        result, args = self.launch(prefix_unit='64')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--prefix-match-unit')+1], '64')
        for value in ('0', '-1', '1.5', '3', '256', '1048577', '064', '0128', '08'):
            with self.subTest(value=value):
                result, args = self.launch(prefix_unit=value)
                self.assertEqual(result.returncode, 64)
                self.assertFalse(args)

    def test_queue_caps_are_opt_in_and_preserve_the_sequence_limit(self):
        result, args = self.launch(queue_tokens='32768', queue_requests='4')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(args[args.index('--max-num-queued-tokens')+1], '32768')
        self.assertEqual(args[args.index('--max-num-queued-reqs')+1], '4')
        self.assertEqual(args[args.index('--max-num-seqs')+1], '4')
        self.assertIn('gradiated_queue_metrics.QueueMetricsMiddleware', args)
        result, args = self.launch()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('--max-num-queued-tokens', args)
        self.assertNotIn('--max-num-queued-reqs', args)

    def test_invalid_queue_caps_fail_before_launch(self):
        for value in ('0', '-1', '1.5', '32768 extra'):
            for name in ('queue_tokens', 'queue_requests'):
                with self.subTest(name=name, value=value):
                    result, args = self.launch(**{name: value})
                    self.assertEqual(result.returncode, 64)
                    self.assertFalse(args)

    def test_invalid_budgets_fail_before_launch(self):
        for budget in ('0', '1', '2', '3', '-1', '1.5', '2048 extra'):
            with self.subTest(budget=budget):
                result, args = self.launch(budget)
                self.assertEqual(result.returncode, 64)
                self.assertFalse(args)


if __name__ == '__main__':
    unittest.main()
