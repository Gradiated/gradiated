import hashlib
import math
import os
from types import SimpleNamespace
import unittest

try:
    import torch
    from vllm.v1.core.block_pool import BlockPool
    from vllm.v1.core.single_type_kv_cache_manager import FullAttentionManager
    from vllm.v1.kv_cache_interface import FullAttentionSpec, get_mamba_prefill_checkpoint_position
except ImportError:
    if os.environ.get('GRADIATED_REQUIRE_GLM_CACHE') == '1':
        raise
    FullAttentionManager = None


@unittest.skipUnless(FullAttentionManager, 'requires the pinned vLLM runtime')
class PrefixTailTest(unittest.TestCase):
    def setup_cache(self, length, *, salt='original', block_size=8704, computed=None):
        pool = BlockPool(num_gpu_blocks=256, enable_caching=True,
                         hash_block_size=128, enable_kv_cache_events=False)
        spec = FullAttentionSpec(block_size=block_size, num_kv_heads=1,
                                 head_size=128, dtype=torch.float16)
        manager = FullAttentionManager(kv_cache_spec=spec, block_pool=pool,
                                      enable_caching=True, kv_cache_group_id=0,
                                      scheduler_block_size=block_size)
        request = SimpleNamespace(request_id='request', num_prompt_tokens=length,
                                  shared_prefix_boundary=0,
                                  block_hashes=self.hashes(length, salt))
        blocks = pool.get_new_blocks(math.ceil(length / block_size))
        manager.req_to_blocks[request.request_id] = blocks
        manager.cache_blocks(request, length if computed is None else computed,
                             replay_boundary=max(length - 1, 0))
        return pool, manager, spec, request, blocks

    @staticmethod
    def hashes(length, salt):
        return [hashlib.sha256(f'{salt}:{i}'.encode()).digest() for i in range(length // 128)]

    def hit(self, pool, spec, length, *, salt='original', eagle=True):
        return FullAttentionManager.find_longest_cache_hit(
            block_hashes=self.hashes(length, salt), max_length=max(length - 1, 0),
            kv_cache_group_ids=[0], block_pool=pool, kv_cache_spec=spec,
            drop_eagle_block=eagle, alignment_tokens=128)[1]

    def test_fine_tail_remains_reachable_at_hash_and_physical_boundaries(self):
        for eagle in (False, True):
            for length in (0, 1, 127, 128, 129, 255, 256, 257, 8192, 8703, 8704,
                           8705, 17408, 32767, 32768, 32769, 65536, 1000000, 1047552):
                with self.subTest(length=length, eagle=eagle):
                    pool, _, spec, _, _ = self.setup_cache(length)
                    expected = get_mamba_prefill_checkpoint_position(length, 128, eagle)
                    self.assertEqual(self.hit(pool, spec, length, eagle=eagle), expected)

    def test_chunked_prefill_caches_only_computed_tokens(self):
        pool, manager, spec, request, _ = self.setup_cache(32768, computed=2048)
        self.assertEqual(self.hit(pool, spec, 32768), 0)
        for computed in (16384, 32639, 32640, 32768, 32896):
            manager.cache_blocks(request, computed, replay_boundary=32767)
            hit = self.hit(pool, spec, 32768)
            self.assertLessEqual(hit, computed)
            if computed >= 32640:
                self.assertEqual(hit, 32512)
            else:
                self.assertLess(hit, 32512)

    def test_changed_early_prefix_does_not_hit(self):
        for length in (8704, 32767, 32768, 32769, 1000000):
            with self.subTest(length=length):
                pool, _, spec, _, _ = self.setup_cache(length)
                self.assertEqual(self.hit(pool, spec, length, salt='changed'), 0)

    def test_eviction_removes_full_and_partial_aliases(self):
        pool, _, spec, _, blocks = self.setup_cache(32768)
        self.assertEqual(self.hit(pool, spec, 32768), 32512)
        pool.free_blocks(blocks)
        pool.get_new_blocks(255)
        self.assertEqual(self.hit(pool, spec, 32768), 0)

    def test_ordinary_same_size_blocks_keep_existing_hits(self):
        for length in (128, 129, 256, 257, 1024):
            with self.subTest(length=length):
                pool, _, spec, _, _ = self.setup_cache(length, block_size=128)
                self.assertEqual(self.hit(pool, spec, length),
                                 get_mamba_prefill_checkpoint_position(length, 128, True))


if __name__ == '__main__':
    unittest.main()
