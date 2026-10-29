import unittest
from reuse import input_key, trusted_run


class ReuseTest(unittest.TestCase):
    def test_documentation_only_changes_reuse_but_material_changes_do_not(self):
        key = lambda tree: input_key(tree, {'unit': 'true', 'packages': '["api"]'})
        original = b'100644 blob aaa\tproduct/services/api/index.ts\0'
        self.assertEqual(key(original), key(original + b'100644 blob bbb\tdocs/DEPLOYMENT.md\0'))
        self.assertNotEqual(key(original), key(original.replace(b'aaa', b'ccc')))
        self.assertNotEqual(key(original), key(original + b'100644 blob ddd\t.github/workflows/tests.yml\0'))

    def test_scope_changes_never_borrow_passes(self):
        self.assertNotEqual(input_key(b'', {'unit': True}), input_key(b'', {'unit': False}))
        self.assertEqual(input_key(b'', {'format': True}), input_key(b'', {'format': False}))

    def test_base_merge_changes_are_material(self):
        self.assertNotEqual(input_key(b'100644 blob aaa\tbase-code.ts\0', {}),
                            input_key(b'100644 blob bbb\tbase-code.ts\0', {}))

    def test_only_completed_successful_same_repository_pr_runs_qualify(self):
        run = dict(status='completed', conclusion='success', event='pull_request',
                   path='.github/workflows/tests.yml', head_repository={'full_name': 'org/repo'})
        self.assertTrue(trusted_run(run, 'org/repo'))
        for change in ({'status': 'in_progress'}, {'conclusion': 'failure'}, {'event': 'push'},
                       {'head_repository': {'full_name': 'fork/repo'}}, {'path': 'other.yml'}):
            self.assertFalse(trusted_run(run | change, 'org/repo'))
