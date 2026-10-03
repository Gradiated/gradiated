import os
import unittest

try:
    import torch
    from vllm.v1.worker.gpu.block_table import BlockTables
except ImportError:
    torch = None
    BlockTables = None


@unittest.skipUnless(
    torch is not None and os.environ.get("GRADIATED_GLM_GPU_TEST") == "1",
    "requires the pinned vLLM runtime and an allocated GPU",
)
class SlotMappingTest(unittest.TestCase):
    def test_narrow_side_cache_is_padded_without_changing_attention_slots(self):
        device = torch.device("cuda")
        tables = BlockTables(
            block_sizes=[128, 4, 4],
            max_num_reqs=2,
            max_num_batched_tokens=1100,
            max_num_blocks_per_group=[8192, 1, 1],
            device=device,
            kernel_block_sizes=[128, 4, 4],
            slot_mapping_enabled=[True, True, False],
        )
        tables.append_block_ids(0, (list(range(8192)), [11], [13]), True)
        tables.apply_staged_writes()
        mapping = torch.tensor([0], device=device, dtype=torch.int32)
        starts = torch.tensor([0, 1025], device=device, dtype=torch.int32)
        for position in (0, 26112, 1047000):
            positions = torch.arange(position, position + 1025, device=device)
            slots = tables.compute_slot_mappings(mapping, starts, positions, 1100)
            torch.cuda.synchronize()
            torch.testing.assert_close(slots[0, :1025], positions, rtol=0, atol=0)
            expected = torch.where(positions < 4, positions + 44, -1)
            torch.testing.assert_close(slots[1, :1025], expected, rtol=0, atol=0)
            self.assertTrue(bool((slots[2] == -1).all()))
            self.assertTrue(bool((slots[:, 1025:] == -1).all()))


if __name__ == "__main__":
    unittest.main()
