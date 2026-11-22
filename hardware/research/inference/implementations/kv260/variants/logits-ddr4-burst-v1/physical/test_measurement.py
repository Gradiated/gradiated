import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest

from lifecycle import Lifecycle
from measurement import CONTROL_CLOCKS, HOMOGENEOUS_REPLIES, verify_counters


class MeasurementTest(unittest.TestCase):
    def test_only_fully_scored_positions_fetch_logits(self):
        case = "encoded-max48"
        control = CONTROL_CLOCKS[case]
        header = {"context_count": 201, "skipped_positions": 96, "scores_consumed": 105 * 320,
                  "request_cycles": control}
        verify_counters(case, header, None, "bram")
        extra = 105 * 2880 + 32778
        header["request_cycles"] = {**control, "first": control["first"] + 3300,
                                   "last": control["last"] + extra - 3100, "done": control["done"] + extra}
        counters = {"mode": "ddr", "fault": False, "transport_busy": False, "faults": 0,
                    "reads": 105 * 320, "beats": 105 * 2560, "useful_bytes": 105 * 20480,
                    "projections": 105, "extra_clocks": extra, "response_waits": 32778,
                    "ar_stalls": 0, "projection_clocks": 105 * 1680 + extra}
        verify_counters(case, header, counters, "ddr")
        counters["projections"] = header["context_count"]
        with self.assertRaisesRegex(ValueError, "projections"):
            verify_counters(case, header, counters, "ddr")

    def test_abba_switches_three_times_and_preserves_all_blocks(self):
        events = []

        def arm(label, mode, pair, watchdog, smoke, homogeneous=None):
            events.append(("smoke" if smoke else "block", label, mode, homogeneous, pair))
            return {"requests": [{"observed": {"header": {"admitted_ns": 100,
                                                          "done_ns": 200}}} for _ in range(3)]}

        with tempfile.TemporaryDirectory() as output:
            fake = SimpleNamespace(output=Path(output), arm=arm,
                                   install_control=lambda s: events.append(("load", s)),
                                   drop_control=lambda _: events.append(("drop", "control")),
                                   install=lambda: events.append(("load", "B1")),
                                   snapshot=lambda *_, **__: {},
                                   release_ddr=lambda *_: events.append(("drop", "DDR")))
            Lifecycle.measure(fake)
        self.assertEqual([v[1] for v in events if v[0] == "load"], ["A1", "B1", "A2"])
        blocks = [v for v in events if v[0] == "block"]
        self.assertEqual(len(blocks), 20)
        self.assertEqual(len([v for v in events if v[0] == "smoke"]), 3)
        self.assertEqual(sum(HOMOGENEOUS_REPLIES[v[3]] if v[3] else 6 for v in blocks), 200)
        self.assertEqual(sum(1 if v[3] else 3 for v in blocks), 36)


if __name__ == "__main__":
    unittest.main()
