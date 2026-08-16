from __future__ import annotations

import unittest

try:
    import torch
except ImportError:
    torch = None

from multiresolution_global_kv import (
    COMPACT_TILE_TOKENS,
    GLOBAL_HEAD_DIM,
    GLOBAL_KV_HEADS,
    build_compact_block_plan,
    consume_compact_global_attention,
    materialize_compact_post_rope_kv,
)


class MultiResolutionGlobalKVTest(unittest.TestCase):
    def test_locked_target_verify_geometry_fits_one_tile(self) -> None:
        plan = build_compact_block_plan(
            4_214,
            12,
            protected_positions=tuple(range(8)),
        )
        self.assertEqual(set(plan.represented_positions), set(range(4_226)))
        self.assertEqual(len(plan.represented_positions), 4_226)
        self.assertLessEqual(plan.compact_tokens, COMPACT_TILE_TOKENS)
        self.assertEqual(plan.compact_tokens, 37)

    def test_max_prefill_query_block_fits_one_tile(self) -> None:
        plan = build_compact_block_plan(
            4_192,
            32,
            protected_positions=tuple(range(8)),
        )
        self.assertLessEqual(plan.compact_tokens, COMPACT_TILE_TOKENS)
        self.assertEqual(plan.compact_tokens, 57)

    @unittest.skipIf(torch is None, "torch unavailable on zero-GPU coordinator")
    def test_summary_multiplicity_reaches_attention_consumer(self) -> None:
        torch.manual_seed(11)
        sequence = 521
        query_start = 520
        k = torch.randn(sequence + 1, GLOBAL_KV_HEADS, GLOBAL_HEAD_DIM)
        v = torch.randn_like(k)
        q = torch.randn(1, 32, GLOBAL_HEAD_DIM)
        plan = build_compact_block_plan(query_start, 1)
        compact_k, compact_v, counts, causal_ends = materialize_compact_post_rope_kv(
            k, v, plan
        )
        output = consume_compact_global_attention(
            q,
            torch.tensor([query_start], dtype=torch.int32),
            compact_k,
            compact_v,
            counts,
            causal_ends,
        )
        changed_counts = counts.clone()
        changed_counts[0] = 1
        changed = consume_compact_global_attention(
            q,
            torch.tensor([query_start], dtype=torch.int32),
            compact_k,
            compact_v,
            changed_counts,
            causal_ends,
        )
        self.assertTrue(torch.isfinite(output).all())
        self.assertFalse(torch.equal(output, changed))


if __name__ == "__main__":
    unittest.main()
