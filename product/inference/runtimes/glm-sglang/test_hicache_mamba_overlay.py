import ast
from enum import Enum
from types import SimpleNamespace
from typing import NamedTuple, Optional
import unittest

from test_source_contract import source_root


class ComponentType(Enum):
    FULL = 'full'
    MAMBA = 'mamba'


class BackupKV(NamedTuple):
    node_ids: list


class Pending(NamedTuple):
    node_id: int
    lock_params: Optional[object]
    publish_node_ids: list


class EndpointMambaBackup(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = source_root()
        if root is None:
            raise unittest.SkipTest('Pinned SGLang source is required')
        tree = ast.parse((root / 'srt/mem_cache/unified_radix_cache.py').read_text())
        cache = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'UnifiedRadixCache')
        methods = {node.name: node for node in cache.body if isinstance(node, ast.FunctionDef)}
        cls.checkpoint_source = ast.unparse(methods['checkpoint_into_tree'])
        module = ast.Module(body=[ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0),
                                  methods['_backup_endpoint_mamba'], methods['_finish_write_through_ack']],
                            type_ignores=[])
        cls.methods = {'ComponentType': ComponentType, 'BackupKV': BackupKV, 'Optional': Optional}
        exec(compile(ast.fix_missing_locations(module), 'installed-unified-radix-cache', 'exec'), cls.methods)

    def cache(self, enabled=True, backuped=True, mamba_on_device=True):
        events = []
        state = SimpleNamespace(
            mamba_prompt_end_checkpoint=enabled, cache_controller=object(), buffer_pipeline=None,
            is_write_back=False, write_through_threshold=1, enable_storage=True,
            components={ComponentType.FULL: None, ComponentType.MAMBA: None},
            ongoing_write_through={}, mamba_backup_after_ack=set(), events=events)

        def backup(action):
            events.append(('backup', tuple(action.node_ids)))
            for node_id in action.node_ids:
                state.ongoing_write_through[node_id] = Pending(node_id, None, [node_id])
            return 0

        state.tree_core = SimpleNamespace(
            is_root=lambda node_id: node_id == 0, is_backuped=lambda node_id: backuped,
            build_backup_spec=lambda node_id: ([], {ComponentType.MAMBA: ['state']} if mamba_on_device else {}),
            finish_write_through=lambda ids, ack: events.append(('finish', ack)))
        state._execute_and_commit_kv_backup = backup
        state.dec_lock_ref = lambda node_id, params: events.append(('unlock', node_id))
        state.write_backup_storage = lambda node_id: events.append(('storage', node_id))
        state._backup_endpoint_mamba = lambda node_id: self.methods['_backup_endpoint_mamba'](state, node_id)
        state.ack = lambda ack_id: self.methods['_finish_write_through_ack'](state, ack_id)
        return state

    def test_checkpoint_backs_up_prompt_end_and_request_end_states(self):
        self.assertIn('if is_finished or up_to >= len(req.origin_input_ids):\n'
                      '        self._backup_endpoint_mamba(new_last_node)', self.checkpoint_source)
        self.assertIn('if is_finished and req.last_node is not None:\n'
                      '            self._backup_endpoint_mamba(req.last_node)', self.checkpoint_source)

    def test_flag_off_or_nothing_to_copy_submits_nothing(self):
        for kwargs in [{'enabled': False}, {'backuped': False}, {'mamba_on_device': False}]:
            cache = self.cache(**kwargs)
            self.assertFalse(cache._backup_endpoint_mamba(7), kwargs)
            self.assertFalse(cache._backup_endpoint_mamba(0), kwargs)
            self.assertEqual(cache.events, [], kwargs)

    def test_backed_up_node_gets_a_state_only_copy(self):
        cache = self.cache()
        self.assertTrue(cache._backup_endpoint_mamba(7))
        self.assertEqual(cache.events, [('backup', (7,))])

    def test_pending_kv_copy_defers_the_state_and_its_storage_write(self):
        cache = self.cache()
        cache.ongoing_write_through[3] = Pending(3, 'lock', [3, 7])
        self.assertFalse(cache._backup_endpoint_mamba(7))
        self.assertEqual(cache.events, [])

        cache.ack(3)
        self.assertEqual(cache.events, [('finish', 3), ('unlock', 3), ('backup', (7,)), ('storage', 3)])
        self.assertEqual(cache.mamba_backup_after_ack, set())

        cache.events.clear()
        cache.ack(7)
        self.assertEqual(cache.events, [('finish', 7), ('storage', 7)])


if __name__ == '__main__':
    unittest.main()
