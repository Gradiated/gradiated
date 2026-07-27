from __future__ import annotations

import unittest
from pathlib import Path

from dual_kv4_contract import (
    CanonicalTierDirectory,
    CONCURRENCY,
    DYNAMIC_RESERVE_BYTES,
    GLOBAL_LAYER_IDS,
    LOCAL_LAYER_IDS,
    MAX_SEQUENCE_TOKENS,
    OLD_CAPACITY,
    PEAK_LIVE_PHYSICAL_ROWS,
    PHYSICAL_CAPACITY,
    RECENT_CAPACITY,
    STATIC_LIMIT_BYTES,
    WINDOW,
    exact_memory_ledger,
    physical_rows,
    validate_layer_schedule,
)


class DualKV4ContractTests(unittest.TestCase):
    def test_exact_memory_ledger_is_positive_and_partitioned_once(self):
        ledger = exact_memory_ledger()
        self.assertEqual(
            STATIC_LIMIT_BYTES + DYNAMIC_RESERVE_BYTES,
            ledger["physical_bytes"],
        )
        self.assertEqual(
            ledger["static"]["required_interval_bytes"],
            {"lower": 43_488_047_772, "upper": 44_455_551_348},
        )
        self.assertEqual(
            ledger["static"]["margin_interval_bytes"],
            {"lower": 1_579_875_259, "upper": 2_547_378_835},
        )
        self.assertEqual(
            ledger["complete_physical"]["margin_interval_bytes"],
            ledger["static"]["margin_interval_bytes"],
        )
        self.assertTrue(ledger["complete_physical"]["fit"])
        self.assertGreater(
            ledger["dynamic"]["observed_assigned_only_margin_interval_bytes"][
                "lower"
            ],
            0,
        )

    def test_exact_five_local_one_global_schedule(self):
        layer_types = [
            "full_attention" if layer_id % 6 == 5 else "sliding_attention"
            for layer_id in range(60)
        ]
        validate_layer_schedule(layer_types)
        self.assertEqual(len(LOCAL_LAYER_IDS), 50)
        self.assertEqual(len(GLOBAL_LAYER_IDS), 10)
        broken = list(layer_types)
        broken[31] = "full_attention"
        with self.assertRaises(ValueError):
            validate_layer_schedule(broken)

    def test_1023_1024_1025_transition_and_padded_noop(self):
        for length, expected_old in ((1023, 0), (1024, 0), (1025, 1)):
            directory = CanonicalTierDirectory(
                physical_capacity=length + 2,
                recent_capacity=length + 1,
                old_capacity=max(1, expected_old),
            )
            directory.route_new(range(length), ())
            if expected_old:
                transitions = directory.begin_transition((0, -1))
                self.assertEqual(len(transitions), 1)
                self.assertGreaterEqual(directory.recent_locations[0], 0)
                self.assertGreaterEqual(directory.old_locations[0], 0)
                directory.finish_transition()
                self.assertEqual(directory.recent_locations[0], -1)
            else:
                self.assertEqual(sum(x >= 0 for x in directory.old_locations), 0)

    def test_c1_c31_c32_and_maximum_live_rows(self):
        self.assertEqual(physical_rows(1, MAX_SEQUENCE_TOKENS), MAX_SEQUENCE_TOKENS)
        self.assertEqual(physical_rows(31, MAX_SEQUENCE_TOKENS), 125_651)
        self.assertEqual(
            physical_rows(CONCURRENCY, MAX_SEQUENCE_TOKENS),
            PEAK_LIVE_PHYSICAL_ROWS,
        )
        self.assertEqual(PHYSICAL_CAPACITY, PEAK_LIVE_PHYSICAL_ROWS + 1)

    def test_prefill_spill_and_arena_maxima(self):
        directory = CanonicalTierDirectory()
        recent = tuple(range(RECENT_CAPACITY))
        directory.route_new(recent, ())
        self.assertEqual(directory.available_recent, 0)
        with self.assertRaises(RuntimeError):
            directory.route_new((RECENT_CAPACITY,), ())
        old_directory = CanonicalTierDirectory()
        old_directory.route_new((), range(OLD_CAPACITY))
        self.assertEqual(old_directory.available_old, 0)

    def test_all_global_payload_barrier_release_and_page_reuse(self):
        directory = CanonicalTierDirectory(
            physical_capacity=8, recent_capacity=4, old_capacity=4
        )
        directory.route_new((1, 2), ())
        recent_location = directory.recent_locations[1]
        transitions = directory.begin_transition((1,))
        self.assertEqual(transitions[0].recent, recent_location)
        for layer_id in GLOBAL_LAYER_IDS:
            self.assertEqual(directory.pending_transition(), transitions)
            self.assertGreaterEqual(directory.recent_locations[1], 0)
            self.assertGreaterEqual(directory.old_locations[1], 0)
            self.assertIn(layer_id, GLOBAL_LAYER_IDS)
        directory.finish_transition()
        old_location = directory.old_locations[1]
        generation = directory.generations[1]
        directory.release((1, -1))
        self.assertEqual(directory.generations[1], generation + 1)
        self.assertEqual(directory.old_locations[1], -1)
        _, reused = directory.route_new((), (1,))
        self.assertEqual(reused, ((1, old_location),))
        self.assertNotEqual(directory.generations[1], generation)

    def test_canonical_move_transfers_compact_owner_without_payload_copy(self):
        directory = CanonicalTierDirectory(
            physical_capacity=8, recent_capacity=4, old_capacity=4
        )
        directory.route_new((1,), (2,))
        recent = directory.recent_locations[1]
        old = directory.old_locations[2]
        directory.move(3, 1)
        directory.move(4, 2)
        self.assertEqual(directory.recent_locations[3], recent)
        self.assertEqual(directory.old_locations[4], old)
        self.assertEqual(directory.recent_locations[1], -1)
        self.assertEqual(directory.old_locations[2], -1)

    def test_current_runtime_seam_reaches_both_real_producers_and_consumers(self):
        source = (Path(__file__).parent / "sglang_dual_kv4.py").read_text()
        for token in (
            "LocalKV4OutlierKVCacheMethod",
            "fused_local_attention(",
            "load_global_extension",
            '("new_recent", "store_recent")',
            '("new_old", "pack_old")',
            "extension.retire_recent(",
            "def retire_all_layers(self, routes: dict)",
            "for local_layer_id in range(GLOBAL_LAYERS)",
            "self.directory.finish_transition()",
            "load_global_extension().paged_attention(",
            "class DualKV4Allocator",
            "self._kvcache.full_kv_pool.release(free_index)",
            "self.full_kv_pool.move_kv_cache(target, source)",
            "kv_cache_configurator.SWAKVPool = DualKV4SWAKVPool",
            "kv_cache_configurator.SWATokenToKVPoolAllocator = DualKV4Allocator",
            "backend_class.forward_extend = forward_extend",
            "backend_class.forward_decode = forward_decode",
        ):
            self.assertIn(token, source)
        self.assertNotIn("dequant_cache", source)


if __name__ == "__main__":
    unittest.main()
