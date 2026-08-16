import unittest

from validation.qwen_vllm_repeatability.schedule import build_schedule


class ScheduleTests(unittest.TestCase):
    def test_is_deterministic_randomized_and_complete(self) -> None:
        first = build_schedule((1, 2, 4, 8), repeat_pairs=5, seed=20260712)
        second = build_schedule((1, 2, 4, 8), repeat_pairs=5, seed=20260712)

        self.assertEqual(first, second)
        self.assertEqual(len(first), 40)
        self.assertNotEqual(
            [run.concurrency for run in first[::2]],
            [1] * 5 + [2] * 5 + [4] * 5 + [8] * 5,
        )

        observed = {(run.concurrency, run.repeat_index, run.state) for run in first}
        expected = {
            (concurrency, repeat_index, state)
            for concurrency in (1, 2, 4, 8)
            for repeat_index in range(1, 6)
            for state in ("cold_engine", "warm_engine")
        }
        self.assertEqual(observed, expected)

    def test_keeps_paired_cold_then_warm_runs_adjacent(self) -> None:
        schedule = build_schedule((1, 2, 4, 8), repeat_pairs=5, seed=9)

        for cold, warm in zip(schedule[::2], schedule[1::2]):
            self.assertEqual(cold.state, "cold_engine")
            self.assertEqual(warm.state, "warm_engine")
            self.assertEqual(cold.pair_id, warm.pair_id)
            self.assertEqual(cold.concurrency, warm.concurrency)


if __name__ == "__main__":
    unittest.main()
