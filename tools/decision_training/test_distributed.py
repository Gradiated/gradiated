import unittest

from distributed import rank_batches
from train import validate_resume_arguments


class DistributedGeometryTests(unittest.TestCase):
    def test_ranks_cover_distinct_equal_length_bucket_batches(self):
        rows = [{"id": i, "ids": [0] * (i + 1)} for i in range(67)]
        schedules = [rank_batches(rows, 2, 8, rank) for rank in range(8)]
        self.assertEqual({dropped for _, dropped in schedules}, {3})
        used = [
            row["id"] for batches, _ in schedules for batch in batches for row in batch
        ]
        self.assertEqual(len(used), 64)
        self.assertEqual(len(set(used)), 64)
        self.assertEqual(set(used), set(range(64)))
        self.assertEqual({len(batches) for batches, _ in schedules}, {4})
        # Every collective update contains adjacent length buckets across ranks.
        for step in range(4):
            ids = [row["id"] for batches, _ in schedules for row in batches[step]]
            self.assertEqual(max(ids) - min(ids), 15)

    def test_resume_schedule_is_reproducible_and_cannot_change_world_size(self):
        rows = [{"id": i, "ids": [0]} for i in range(16)]
        self.assertEqual(rank_batches(rows, 2, 2, 1), rank_batches(rows, 2, 2, 1))
        settings = {
            "batch_size": 2,
            "accumulation": 2,
            "max_length": 2048,
            "learning_rate": 1e-4,
            "brier_weight": 1,
            "rank": 32,
            "steps": 100,
        }
        with self.assertRaisesRegex(ValueError, "training_world_size"):
            validate_resume_arguments(
                {**settings, "training_world_size": 8},
                {**settings, "training_world_size": 4},
            )

    def test_insufficient_data_fails_instead_of_unequal_collective_counts(self):
        with self.assertRaisesRegex(ValueError, "not enough"):
            rank_batches([{"ids": [0]}], 2, 8, 0)


if __name__ == "__main__":
    unittest.main()
