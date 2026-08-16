from __future__ import annotations

import unittest

from ring_ownership import RingOwnership


class RingOwnershipTest(unittest.TestCase):
    def test_padding_is_negative_and_real_slots_are_bijective(self) -> None:
        ownership = RingOwnership(request_pool_size=64, tokens_per_row=1024)

        rows = ownership.rows_for_slots([0, 1, 32, 64])

        self.assertEqual(rows, [-1, 0, 31, 63])
        self.assertEqual(len(set(ownership.slot_to_row[1:])), 64)

    def test_reordering_and_slot_reuse_preserve_ownership(self) -> None:
        ownership = RingOwnership(request_pool_size=4, tokens_per_row=1024)

        first = ownership.rows_for_slots([4, 1, 3])
        reordered = ownership.rows_for_slots([3, 4, 1])
        reused = ownership.rows_for_slots([4])

        self.assertEqual(first, [3, 0, 2])
        self.assertEqual(reordered, [2, 3, 0])
        self.assertEqual(reused, [3])

    def test_invalid_slots_fail_before_indexing(self) -> None:
        ownership = RingOwnership(request_pool_size=4, tokens_per_row=1024)

        with self.assertRaises(ValueError):
            ownership.rows_for_slots([5])

    def test_geometry_is_bound_to_power_of_two_ring(self) -> None:
        with self.assertRaises(ValueError):
            RingOwnership(request_pool_size=4, tokens_per_row=1000)


if __name__ == "__main__":
    unittest.main()
