from collections import Counter
from copy import deepcopy
from itertools import permutations
from types import SimpleNamespace
import unittest

import board_resident_benchmark as bench


def reference(context_count=5):
    return {
        "prefix_text": "fixed", "generated_tokens": [1, 2], "context_count": context_count,
        "frames": [{"logits": [-2, -1, 3], "logits_sha256": "frame", "counters": [0, 29281, 320, 1, 0]}],
    }


class Replay:
    def __init__(self, ref):
        self.ref = ref
        self.calls = 0
        self.requests = 0
        self.session = SimpleNamespace(context_count=0)
        self.setup = {"ready_ns": 1}
        self.now = iter(range(2, 10000)).__next__

    def complete(self, prompt, *, time_each_byte=False):
        self.calls += 1
        previous = self.session.context_count
        timing = {"index": self.requests, "previous_context_count": previous, "clear": None}
        if self.requests:
            timing["clear"] = {"begin_ns": self.now(), "end_ns": self.now(), "context_count": 0,
                               "counters": bench.CLEAR_COUNTERS}
        timing["inference_begin_ns"] = self.now()
        timing["first_byte_ns"] = self.now()
        second = self.now()
        timing["eos_ns"] = self.now()
        timing["inference_end_ns"] = self.now()
        if time_each_byte:
            timing["emitted_byte_ns"] = [timing["first_byte_ns"], second]
        self.requests += 1
        self.session.context_count = self.ref["context_count"]
        return {"completion": deepcopy(self.ref), "timing": timing}


class BenchmarkBlocks(unittest.TestCase):
    def test_balanced_schedule_and_observer_order(self):
        patterns = Counter()
        for index in range(3):
            schedule = dict(bench.schedule(index))
            short = schedule["short"]
            self.assertEqual(Counter(case for case, _ in schedule["warmup"]), dict.fromkeys(bench.CASES, 2))
            self.assertEqual(Counter(case for case, _ in short), dict.fromkeys(bench.CASES, 4))
            self.assertTrue(all(measured for _, measured in short))
            observer = [(bench.B, False), (bench.B, True)]
            self.assertEqual(schedule["observer"], observer if index != 1 else observer[::-1])
            patterns.update(tuple(case for case, _ in short[j:j+3]) for j in range(0, len(short), 3))
            self.assertEqual("long" in schedule, index == 2)
        self.assertEqual(patterns, dict.fromkeys(permutations(bench.CASES), 2))
        self.assertEqual(Counter(case for case, _ in schedule["long"]), dict.fromkeys(bench.CASES, 16))

    def test_block_has_exact_boundaries_and_equal_capture_with_optional_ticks(self):
        expected = reference()
        runner = Replay(expected)
        cases = [(bench.B, False), (bench.B, True)]
        block, examples = bench.run_block(runner, cases, {bench.B: expected}, lambda: None, capture_examples=True)
        off, on = block["requests"]
        self.assertEqual(off["observed"], on["observed"])
        self.assertNotIn("emitted_byte_ns", off["timing"])
        self.assertEqual(len(on["timing"]["emitted_byte_ns"]), 2)
        self.assertEqual(examples, {bench.B: expected})
        self.assertNotIn("logits", on["observed"]["frames"][0])
        self.assertEqual(block["begin_ns"], off["admitted_ns"])
        self.assertEqual(block["end_ns"], on["verified_ns"])
        self.assertGreater(on["admitted_ns"], off["verified_ns"])
        self.assertGreater(on["verified_ns"], on["returned_ns"])
        self.assertEqual(bench.validate_block(block, cases, {bench.B: bench.compact(expected)}, 0, 0, 1),
                         (2, 5, block["end_ns"]))

    def test_mismatch_or_deadline_stops_before_later_calls(self):
        expected = reference()
        cases = [(bench.B, True)] * 3
        runner = Replay(expected)
        native = runner.complete

        def incorrect(*arguments, **options):
            reply = native(*arguments, **options)
            if runner.calls == 2:
                reply["completion"]["frames"][0]["logits"][0] -= 1
            return reply

        runner.complete = incorrect
        with self.assertRaises(bench.BlockFailure) as stop:
            bench.run_block(runner, cases, {bench.B: expected}, lambda: None)
        self.assertEqual(runner.calls, 2)
        self.assertEqual(len(stop.exception.completed), 1)
        self.assertEqual(stop.exception.detail["actual"]["logits"], [-3, -1, 3])
        runner = Replay(expected)
        permits = iter([None])

        def expired():
            try:
                next(permits)
            except StopIteration as error:
                raise TimeoutError("absolute deadline") from error

        with self.assertRaisesRegex(bench.BlockFailure, "absolute deadline"):
            bench.run_block(runner, cases, {bench.B: expected}, expired)
        self.assertEqual(runner.calls, 1)

    def test_extra_frame_is_preserved_on_length_mismatch(self):
        fixed = reference()
        actual = deepcopy(fixed)
        extra = {"logits": [4, 5, 6]}
        actual["frames"].append(extra)
        with self.assertRaises(bench.Mismatch) as stop:
            bench.check_actual(actual, fixed)
        self.assertEqual(stop.exception.detail["actual"], extra)
        self.assertEqual(stop.exception.detail["position"], 1)

    def test_compact_verifier_rejects_bad_order_count_digest_and_boundaries(self):
        expected = reference()
        specs = [(bench.B, True), (bench.B, True)]
        block, _ = bench.run_block(Replay(expected), specs, {bench.B: expected}, lambda: None)
        expected_compact = {bench.B: bench.compact(expected)}

        def verify(value):
            return bench.validate_block(value, specs, expected_compact, 0, 0, 1)

        self.assertEqual(verify(block)[:2], (2, 5))
        changes = (
            lambda v: v["requests"].pop(),
            lambda v: v["requests"][0]["observed"]["frames"][0].__setitem__(0, "bad"),
            lambda v: v["requests"][1]["timing"].update(index=7),
            lambda v: v["requests"][1]["timing"].update(clear=None),
            lambda v: v["requests"][0]["timing"]["emitted_byte_ns"].pop(),
            lambda v: v["requests"][1].update(admitted_ns=1),
            lambda v: v.update(end_ns=v["requests"][-1]["returned_ns"]),
        )
        for change in changes:
            broken = deepcopy(block)
            change(broken)
            with self.assertRaises(ValueError):
                verify(broken)


if __name__ == "__main__":
    unittest.main()
