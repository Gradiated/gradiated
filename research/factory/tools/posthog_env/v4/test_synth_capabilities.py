import importlib.util
from pathlib import Path
import random
import sys
import types
import unittest
from unittest.mock import patch


class FamilyCapabilities(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("synth_under_test", Path(__file__).with_name("synth_tasks.py"))
        cls.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {k: types.ModuleType(k) for k in ("llm_proxy", "curate_tasks", "spot_card")}):
            spec.loader.exec_module(cls.module)

    def test_unsupported_families_and_duplicate_jobs_are_excluded(self):
        base = {"supported_families": ["warehouse", "funnel_conversion"]}
        weights = {"warehouse": 1, "funnel_conversion": 1, "session_replay": 100}
        got = self.module.choose_families(base, weights, 5, random.Random(1), set())
        self.assertEqual(set(got), {"warehouse", "funnel_conversion"})
        self.assertEqual(len(got), 2)

    def test_explicit_empty_capabilities_do_not_enable_everything(self):
        self.assertEqual(self.module.choose_families({"supported_families": []}, {"warehouse": 1}, 3,
                                                    random.Random(1), set()), [])

    def test_requested_calibration_subset_is_respected(self):
        got = self.module.choose_families({}, {"warehouse": 1, "funnel_conversion": 1}, 3,
                                          random.Random(1), {"warehouse"})
        self.assertEqual(got, ["warehouse"])


if __name__ == "__main__":
    unittest.main()
