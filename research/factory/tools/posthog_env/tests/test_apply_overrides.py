"""Unit tests for apply_overrides (twin-date -> production-date conversion and merging)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, "/opt/posthog-env/runner")
import apply_overrides as A  # noqa: E402


class Merge(unittest.TestCase):
    def test_spike_dates_shift_back_to_production(self):
        out = A.merge({}, [{"kind": "spike", "event": "e", "from": "2026-10-10", "to": "2026-10-30", "factor": 0}], 10)
        self.assertEqual(out["spikes"][0]["from"], "2026-09-30")
        self.assertEqual(out["spikes"][0]["to"], "2026-10-20")
        self.assertEqual(out["spikes"][0]["factor"], 0.0)

    def test_multiplier_compounds_and_history_takes_max(self):
        out = A.merge({"events": {"e": 2.0}, "history_days": 200},
                      [{"kind": "event_multiplier", "event": "e", "factor": 3}, {"kind": "history_days", "days": 120}], 0)
        self.assertEqual(out["events"]["e"], 6.0)
        self.assertEqual(out["history_days"], 200)

    def test_same_spike_replaced(self):
        cur = {"spikes": [{"event": "e", "from": "2026-09-30", "to": "2026-10-01", "factor": 5}]}
        out = A.merge(cur, [{"kind": "spike", "event": "e", "from": "2026-10-10", "to": "2026-10-11", "factor": 0}], 10)
        self.assertEqual(len(out["spikes"]), 1)
        self.assertEqual(out["spikes"][0]["factor"], 0.0)


if __name__ == "__main__":
    unittest.main()
