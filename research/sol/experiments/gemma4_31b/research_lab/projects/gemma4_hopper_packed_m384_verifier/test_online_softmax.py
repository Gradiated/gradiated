from __future__ import annotations

import math
import unittest


def merge(states):
    merged_max = -math.inf
    merged_sum = 0.0
    merged_out = [0.0 for _ in states[0][2]]
    for part_max, part_sum, part_out in states:
        new_max = max(merged_max, part_max)
        old_scale = 0.0 if merged_max == -math.inf else math.exp(merged_max - new_max)
        part_scale = 0.0 if part_max == -math.inf else math.exp(part_max - new_max)
        merged_sum = merged_sum * old_scale + part_sum * part_scale
        merged_out = [
            old * old_scale + part * part_scale
            for old, part in zip(merged_out, part_out, strict=True)
        ]
        merged_max = new_max
    return merged_max, merged_sum, merged_out


def state(scores, values):
    maximum = max(scores)
    weights = [math.exp(value - maximum) for value in scores]
    denominator = sum(weights)
    output = [
        sum(weight * row[column] for weight, row in zip(weights, values, strict=True))
        for column in range(len(values[0]))
    ]
    return maximum, denominator, output


class OnlineSoftmaxTest(unittest.TestCase):
    def test_partition_merge_matches_single_state(self):
        scores = [-4.0, -1.0, 2.0, 0.5, 6.0, -7.0, 3.0]
        values = [[index * 0.25, 1.0 - index] for index in range(len(scores))]
        merged = merge(
            [
                state(scores[:2], values[:2]),
                state(scores[2:5], values[2:5]),
                state(scores[5:], values[5:]),
            ]
        )
        expected = state(scores, values)
        self.assertAlmostEqual(merged[0], expected[0], places=12)
        self.assertAlmostEqual(merged[1], expected[1], places=12)
        for actual, wanted in zip(merged[2], expected[2], strict=True):
            self.assertAlmostEqual(actual, wanted, places=11)

    def test_running_max_rescales_prior_output(self):
        first = state([100.0], [[2.0, -3.0]])
        second = state([1000.0], [[5.0, 7.0]])
        merged = merge([first, second])
        self.assertEqual(merged[2], second[2])


if __name__ == "__main__":
    unittest.main()
