import ast
from dataclasses import dataclass
from typing import List, Optional
import unittest

from test_source_contract import source_root


class CpSliceWriter(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = source_root()
        if root is None:
            raise unittest.SkipTest('Pinned SGLang source is required')
        tree = ast.parse((root / 'srt/mem_cache/hicache_storage.py').read_text())
        config = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == 'HiCacheStorageConfig')
        namespace = {'dataclass': dataclass, 'List': List, 'Optional': Optional}
        exec(compile(ast.Module(body=[config], type_ignores=[]), 'installed-hicache-storage', 'exec'), namespace)
        cls.Config = namespace['HiCacheStorageConfig']

    def writer(self, tp_rank, tp_size, cp_rank, cp_size, mla=True, **kwargs):
        return self.Config(tp_rank=tp_rank, tp_size=tp_size, pp_rank=0, pp_size=1, attn_cp_rank=cp_rank,
                           attn_cp_size=cp_size, is_mla_model=mla, enable_storage_metrics=False,
                           is_page_first_layout=True, model_name='m', **kwargs).is_storage_writer

    def test_each_cp_slice_of_an_mla_page_has_a_writer(self):
        self.assertTrue(self.writer(0, 2, 0, 2))
        self.assertTrue(self.writer(1, 2, 1, 2))
        self.assertEqual([self.writer(rank, 4, rank // 2, 2) for rank in range(4)], [True, False, True, False])

    def test_without_cp_or_with_unified_keys_writers_are_unchanged(self):
        self.assertEqual([self.writer(rank, 2, 0, 1) for rank in range(2)], [True, False])
        self.assertEqual([self.writer(rank, 2, 0, 1, mla=False) for rank in range(2)], [True, True])
        self.assertEqual([self.writer(rank, 2, rank, 2, unified_suffixes=['c0']) for rank in range(2)], [True, False])


if __name__ == '__main__':
    unittest.main()
