"""Check four-mode traffic accounting and the frozen arm order."""

from collections import Counter
from itertools import permutations
import unittest

from measurement import CONTROL_CLOCKS, HOMOGENEOUS_ORDERS, HOMOGENEOUS_REPLIES
from measurement import MIXED_ORDERS, verify_counters


PROMPT = "encoded-hello"
MODES = ("bram", "scalar", "beat", "row")


def request(mode, context=101):
    ar, r = {"bram": (0, 0), "scalar": (1024, 1024),
             "beat": (256, 256), "row": (32, 256)}[mode]
    reads, beats = context * ar, context * r
    address, wait = (3, 7) if reads else (0, 0)
    extra = reads + beats + address + wait
    end = dict(CONTROL_CLOCKS[PROMPT])
    if mode != "bram":
        end["first"] += 100
        end["last"] += 1000
        end["done"] += extra
    counts = {
        "mode": mode, "fault": False, "transport_busy": False, "faults": 0,
        "projections": context, "reads": reads, "beats": beats,
        "useful_bytes": 0 if mode == "bram" else 2048 * context,
        "extra_clocks": extra, "ar_stalls": address, "response_waits": wait,
        "projection_clocks": 2112 * context + extra,
    }
    return {"context_count": context, "request_cycles": end}, counts


class MeasurementTest(unittest.TestCase):
    def test_mixed_schedule_balances_position_and_ordered_neighbors(self):
        for position in range(4):
            self.assertEqual(set(row[position] for row in MIXED_ORDERS), set(MODES))
        observed = Counter(pair for row in MIXED_ORDERS for pair in zip(row, row[1:]))
        self.assertEqual(observed, Counter(permutations(MODES, 2)))

    def test_homogeneous_schedule_reverses_each_prompt_and_all_modes(self):
        self.assertEqual([name for _, name, _ in HOMOGENEOUS_ORDERS[:3]],
                         list(HOMOGENEOUS_REPLIES))
        self.assertEqual([name for _, name, _ in HOMOGENEOUS_ORDERS[3:]],
                         list(reversed(HOMOGENEOUS_REPLIES)))
        for lhs, rhs in zip(HOMOGENEOUS_ORDERS[:3], reversed(HOMOGENEOUS_ORDERS[3:])):
            self.assertEqual(lhs[1], rhs[1])
            self.assertEqual(lhs[2], tuple(reversed(rhs[2])))

    def test_all_modes_and_retained_read_clocks(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                header, counts = request(mode)
                verify_counters(PROMPT, header, counts, mode)
                if mode == "row":
                    counts["extra_clocks"] -= counts["beats"] - counts["reads"]
                    with self.assertRaisesRegex(ValueError, "nonfinal beats"):
                        verify_counters(PROMPT, header, counts, mode)

    def test_read_counts_different_from_row_beats(self):
        header, counts = request("row")
        counts["beats"] = counts["reads"]
        with self.assertRaisesRegex(ValueError, "beats"):
            verify_counters(PROMPT, header, counts, "row")

    def test_bram_exact_cycle_reference(self):
        header, counts = request("bram")
        header["request_cycles"]["done"] += 1
        with self.assertRaisesRegex(ValueError, "BRAM mode differs"):
            verify_counters(PROMPT, header, counts, "bram")


if __name__ == "__main__":
    unittest.main()
