import importlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
comp = importlib.import_module("autonomous_comparison")
runtime = importlib.import_module("autonomous_runtime")


class ComparisonTests(unittest.TestCase):
    def test_equal_prompt_counts_and_matched_idle(self):
        a, b, c = "a", "b", "c"
        base = SimpleNamespace(FORWARD=((a,b,c),(b,c,a),(c,a,b)),
                               REVERSE=((a,c,b),(b,a,c),(c,b,a)))
        for pair in range(3):
            warm, measured = comp.schedule(base, pair)
            self.assertEqual(warm[-1][0], measured[-1][0])
            self.assertCountEqual((case for case, _ in measured), (a,a,b,b,c,c))

    def test_capped_reference_keeps_only_prefix_in_context(self):
        logits = [-15] * 320
        logits[65] = -1
        reference = {"generated_tokens": [65, 70], "prefix_tokens": [256, 278], "context_count": 4,
                     "stop_reason": "eos", "frames": [{"logits": logits}, {"logits": logits}]}
        for cap, ids in ((0, []), (1, [65])):
            limited = comp.capped_reference(reference, cap)
            self.assertEqual((limited["generated_tokens"], limited["context_count"], limited["stop_reason"]),
                             (ids, 2, "output_limit"))
            self.assertEqual(limited["byte_prefix_hex"], bytes(ids).hex())

    def test_timing_uses_only_useful_output_and_device_observation(self):
        observed = {"admitted_ns": 1_000_000, "done_ns": 8_000_000,
                    "output_ns": [2_000_000, 3_000_000, 7_000_000]}
        row = {"case": "sample", "verified_ns": 10_000_000, "observed": {"header": observed}}
        self.assertEqual(comp.timings({"requests": [row]})["sample"],
                         {"ttft_ms":[1.0], "decode_bytes_per_second":[400.0],
                          "completion_ms":[7.0], "verified_ms":[9.0]})
        observed["output_ns"] = []
        self.assertEqual(comp.timings({"requests": [row]})["sample"]["decode_bytes_per_second"], [])


if __name__ == "__main__":
    unittest.main()
