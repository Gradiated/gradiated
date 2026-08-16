#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


P = Path(__file__).resolve().parent
S = importlib.util.spec_from_file_location('owner', P / 'h200_endpoint_owner.py')
M = importlib.util.module_from_spec(S)
S.loader.exec_module(M)


class OwnerRegression(unittest.TestCase):
    def test_diagnostic_contract_requires_log_state_exit_oom_and_gpu(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            label = 'readiness_failure'
            for name, contents in {
                f'{label}.container.log': 'load failed',
                f'{label}.container-state.json': json.dumps({'Running': False, 'ExitCode': 1, 'OOMKilled': False}),
                f'{label}.container-exit-code.txt': '1\n',
                f'{label}.container-oom.txt': 'false\n',
                f'{label}.gpu.csv': 'NVIDIA H200, 0, 0, 70\n',
            }.items():
                (root / name).write_text(contents)
            self.assertTrue(M.diagnostic_contract(root, label)['pass'])
            (root / f'{label}.container.log').unlink()
            self.assertFalse(M.diagnostic_contract(root, label)['pass'])
            (root / f'{label}.container.log').write_text('no container')
            (root / f'{label}.container-state.json').write_text('error: no such object')
            self.assertFalse(M.diagnostic_contract(root, label)['pass'])

    def test_owner_uses_real_retained_context_and_retrieval(self):
        source = (P / 'h200_endpoint_owner.py').read_text()
        self.assertIn('retained_development_window(out, events, args.deadline_epoch, 600)', source)
        self.assertIn('retrieve_container_diagnostics(ip, out, events, work, \'readiness_failure\')', source)
        self.assertIn('--kv-cache-dtype fp8_e4m3', source)
        self.assertNotIn('--kv-cache-dtype fp8_e4m3fn', source)
        self.assertNotIn('{IMAGE} vllm serve {work}/checkpoint', source)
        self.assertIn('--dtype float16', source)
        self.assertIn('--max-num-batched-tokens 8192', source)
        self.assertNotIn('--max-num-batched-tokens 524288', source)
        self.assertNotIn('docker run -d --rm --name w4-endpoint', source)
        self.assertIn("'action': 'retain', 'until_epoch': args.deadline_epoch", source)
        self.assertIn('repair_lease_regression_pass', source)


if __name__ == '__main__':
    unittest.main()
