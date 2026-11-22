from contextlib import contextmanager
import ctypes
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import board_bos
import board_resident as resident


class FakeSession:
    def __init__(self):
        self.context_count = 0
        self.calls = []
        self.picks = {}

    def clear(self):
        self.calls.append(("clear", self.context_count))
        self.context_count = 0
        return {"context_count": 0, "counters": [0, resident.MODEL_WORDS, 0, 0, 0]}

    def step(self, token):
        position = self.context_count
        if position == 0 and token != resident.BOS:
            raise AssertionError("Missing BOS")
        self.calls.append(("step", token))
        self.context_count += 1
        logits = [-100] * resident.VOCAB
        for chosen in self.picks.get(position, [0]):
            logits[chosen] = 100
        return {"api_result": 0, "counters": [0, resident.MODEL_WORDS, resident.VOCAB, self.context_count, 0],
                "context_count": self.context_count, "logits": logits}


class ResidentRequests(unittest.TestCase):
    def setUp(self):
        self.session = FakeSession()
        self.now = iter(range(1, 100000)).__next__
        self.runner = resident.ResidentRunner(self.session, board_bos.completion_prefix, self.now, 0, 1)

    def test_one_open_and_clear_between_runs_including_full_context(self):
        events = []

        @contextmanager
        def native(path):
            events.append(("begin", path))
            counters = [None] * 5
            library = source["ctypes"].CDLL("fake")
            library.board_session_begin.argtypes = ["signature"]
            library.board_session_begin.restype = int
            self.assertEqual(library.board_session_begin(counters), 0)
            try:
                yield self.session
            finally:
                events.append(("close", path))

        def begin(counters):
            self.assertEqual(begin.argtypes, ["signature"])
            self.assertIs(begin.restype, int)
            counters[:] = [0, resident.MODEL_WORDS, 0, 0, 0]
            return 0

        binding = SimpleNamespace(CDLL=lambda _: SimpleNamespace(board_session_begin=begin))
        source = {"NativeSession": native, "completion_prefix": board_bos.completion_prefix, "ctypes": binding}
        self.session.picks = {2: [65, 66], 3: [resident.EOS]}
        with patch.object(resident, "sealed_runner", return_value=source) as pinned:
            with resident.open_resident("model", now=self.now) as runner:
                first = runner.complete("a")
                second = runner.complete("b")
                full = runner.score_sequence([resident.BOS] + [0] * 255)
                last = runner.complete("a")
            pinned.assert_called_once_with(Path("model"))
        self.assertEqual(runner.begin, {"calls": 1, "counters": [0, resident.MODEL_WORDS, 0, 0, 0]})
        self.assertEqual(events, [("begin", Path("model")), ("close", Path("model"))])
        self.assertEqual(first["completion"], last["completion"])
        reply = first["completion"]
        self.assertEqual(reply["continuation_text"], "A")
        self.assertEqual(reply["input_tokens"], [256, 278, 289, 65])
        self.assertTrue(reply["eos"])
        self.assertEqual(full["context_count"], 256)
        self.assertIsNone(first["timing"]["clear"])
        self.assertEqual(last["timing"]["previous_context_count"], 256)
        self.assertEqual(second["timing"]["index"], 1)
        self.assertEqual([call for call in self.session.calls if call[0] == "clear"],
                         [("clear", 4), ("clear", 4), ("clear", 256)])
        timestamps = last["timing"]
        self.assertLess(timestamps["clear"]["end_ns"], timestamps["inference_begin_ns"])
        self.assertLess(timestamps["first_byte_ns"], timestamps["eos_ns"])

    def test_optional_byte_times_record_each_output_without_changing_decisions(self):
        self.session.picks = {2: [65], 3: [66], 4: [resident.EOS]}
        default = self.runner.complete("a")
        measured = self.runner.complete("a", time_each_byte=True)
        self.assertEqual(default["completion"], measured["completion"])
        self.assertNotIn("emitted_byte_ns", default["timing"])
        timing = measured["timing"]
        first, second = timing["emitted_byte_ns"]
        self.assertEqual(first, timing["first_byte_ns"])
        self.assertLess(first, second)
        self.assertLess(second, timing["eos_ns"])
        self.assertEqual(measured["completion"]["generated_tokens"], [65, 66])

    def test_eos_and_non_byte_ids_are_not_counted_as_emissions(self):
        for token, reason in ((resident.EOS, "eos"), (resident.BOS, "non_byte_token")):
            with self.subTest(token=token):
                self.session.picks = {2: [token]}
                result = self.runner.complete("a", time_each_byte=True)
                self.assertEqual(result["timing"]["emitted_byte_ns"], [])
                self.assertIsNone(result["timing"]["first_byte_ns"])
                self.assertEqual(result["completion"]["stop_reason"], reason)

    def test_counted_begin_forwards_ctypes_abi_and_blocks_second_call(self):
        signature = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.POINTER(ctypes.c_uint32))
        calls = []

        @signature
        def begin(counters):
            calls.append(True)
            for index, value in enumerate([0, resident.MODEL_WORDS, 0, 0, 0]):
                counters[index] = value
            return 0

        record = {"calls": 0, "counters": None}
        observed = resident.CountedBegin(begin, record)
        observed.argtypes = [ctypes.POINTER(ctypes.c_uint32)]
        observed.restype = ctypes.c_int
        counters = (ctypes.c_uint32 * 5)()
        self.assertEqual(observed(counters), 0)
        with self.assertRaisesRegex(RuntimeError, "second"):
            observed(counters)
        self.assertEqual(calls, [True])
        self.assertEqual(record, {"calls": 1, "counters": [0, resident.MODEL_WORDS, 0, 0, 0]})

    def test_missing_clear_or_changed_counters_poison_session(self):
        for reset, counters in ((False, [0, 29281, 0, 0, 0]), (True, [0, 0, 0, 0, 0])):
            with self.subTest(reset=reset, counters=counters):
                session = FakeSession()
                runner = resident.ResidentRunner(session, board_bos.completion_prefix, self.now, 0, 1)
                runner.score_sequence([256, 7])

                def clear():
                    if reset:
                        session.context_count = 0
                    return {"context_count": 0, "counters": counters}

                session.clear = clear
                calls = session.calls.copy()
                with self.assertRaisesRegex(RuntimeError, "zero|counters"):
                    runner.score_sequence([256])
                with self.assertRaisesRegex(RuntimeError, "failed"):
                    runner.score_sequence([256])
                self.assertEqual(session.calls, calls)

    def test_native_fault_stops_following_requests(self):
        with patch.object(self.session, "step", side_effect=TimeoutError("native deadline")) as step:
            with self.assertRaises(TimeoutError):
                self.runner.complete("a")
            with self.assertRaisesRegex(RuntimeError, "failed"):
                self.runner.complete("a")
            step.assert_called_once()

    def test_invalid_prompt_does_not_clear_or_use_native_session(self):
        with self.assertRaisesRegex(ValueError, "48 UTF-8 bytes"):
            self.runner.complete("é" * 25)
        self.assertEqual(self.session.calls, [])
        result = self.runner.score_sequence([256])
        self.assertEqual(result["timing"]["index"], 0)
        self.assertEqual(result["context_count"], 1)


if __name__ == "__main__":
    unittest.main()
