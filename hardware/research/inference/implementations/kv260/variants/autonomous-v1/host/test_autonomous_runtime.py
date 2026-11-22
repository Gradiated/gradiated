from hashlib import sha256
import importlib
import json
import os
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
runtime = importlib.import_module("autonomous_runtime")
FRESH_PINS = (
    "9b23c8df5cb52633fe05bc02871d246e5538cb94a301aff756f37bfc7aa458ba",
    "e92f9d9d8ec33a6ccbfc715e42148a6aea441f017f89a931c08cad3a84197686",
    "1edfbd04efc45975a02cfec629601de65d430491313f93984a56a4f232ddb8a1",
)


class Clock:
    def __init__(self):
        self.tick = 100

    def __call__(self):
        self.tick += 1
        return self.tick


class Session:
    def __init__(self, logits):
        self.rows = iter(logits)
        self.inputs = []
        self.context_count = 0

    def step(self, token):
        self.inputs.append(token)
        self.context_count += 1
        return {"logits": next(self.rows)}


def scores(*winners):
    logits = [-100] * 320
    for winner in winners:
        logits[winner] = -1
    return logits


class FakePort:
    def __init__(self, output, count, reason=1, *, score_adjust=0, flags=48):
        self.output = list(output)
        self.launch = None
        self.now = Clock()
        self.status = 2 | (reason << 8) | flags
        self.values = {0x00: 1, 0x20: count, 0x3c: len(output), 0x44: 0,
                       0x48: 100, 0x4c: 200, 0x50: 300, 0x54: count, 0x58: count * 320 + score_adjust}

    def start(self, prefix, maximum, deadline):
        self.launch = (prefix, maximum, deadline)

    def wait(self, deadline):
        if self.output:
            return self.output.pop(0), self.now(), 9
        return None, self.now(), self.status

    def read(self, offset):
        return self.values[offset]


class AutonomousRuntimeTest(unittest.TestCase):
    def test_native_calls_receive_only_remaining_request_budget(self):
        namespace = {"CALL_BUDGET_NS": 30_000_000_000}
        exec("class Driver:\n"
             "    def step(self, fail=False):\n"
             "        if fail:\n"
             "            raise RuntimeError(CALL_BUDGET_NS)\n"
             "        return CALL_BUDGET_NS\n", namespace)
        driver = namespace["Driver"]()
        self.assertEqual(runtime.call_before(driver.step, lambda: 510, 910), 400)
        with self.assertRaisesRegex(RuntimeError, "400"):
            runtime.call_before(driver.step, lambda: 510, 910, True)
        self.assertEqual(namespace["CALL_BUDGET_NS"], 30_000_000_000)
        with self.assertRaises(runtime.RequestFailure):
            runtime.call_before(driver.step, lambda: 910, 910)

    def test_control_accepts_signed_tie_and_eos_without_feeding_eos(self):
        session = Session([scores(99), scores(13, 20), scores(257)])
        result = runtime.control_request(session, (256, 278), 255, Clock(), 1000)
        self.assertEqual(session.inputs, [256, 278, 13])
        self.assertEqual(result["output_ids"], [13])
        self.assertEqual(result["stop_reason"], "eos")

    def test_last_permitted_output_is_not_fed_back(self):
        session = Session([scores(97), scores(98)])
        result = runtime.control_request(session, (256,), 2, Clock(), 1000)
        self.assertEqual(session.inputs, [256, 97])
        self.assertEqual(result["output_ids"], [97, 98])
        self.assertEqual(result["stop_reason"], "output_limit")

    def test_non_byte_and_full_context(self):
        session = Session([scores(319)])
        result = runtime.control_request(session, (256,), 255, Clock(), 1000)
        self.assertEqual(result["output_ids"], [319])
        self.assertEqual(result["output_ns"], [])
        self.assertEqual(result["stop_reason"], "non_byte_token")
        prefix = (256,) + (65,) * 255
        session = Session([scores(99)] * 256)
        result = runtime.control_request(session, prefix, 0, Clock(), 2000)
        self.assertEqual(session.inputs, list(prefix))
        self.assertEqual(result["output_ids"], [])
        self.assertEqual(result["stop_reason"], "context_limit")

    def test_candidate_compact_and_drained(self):
        port = FakePort([71, 72], 3)
        result = runtime.compact_request(port, (256,), 255, 1000)
        self.assertEqual(port.launch, ((256,), 255, 1000))
        self.assertEqual(result["output_ids"], [71, 72])
        self.assertEqual(result["stop_reason"], "eos")
        self.assertEqual(result["scores_consumed"], 960)
        self.assertEqual(result["request_cycles"], dict(first=100, last=200, done=300))

    def test_candidate_immediate_eos_and_invalid_byte_are_distinct(self):
        zero = runtime.compact_request(FakePort([], 1, flags=0), (256,), 255, 1000)
        invalid = runtime.compact_request(FakePort([319], 1, reason=3, flags=0), (256,), 255, 1000)
        self.assertEqual((zero["stop_reason"], zero["output_ids"]), ("eos", []))
        self.assertEqual((invalid["stop_reason"], invalid["output_ids"]), ("non_byte_token", [319]))
        self.assertEqual(zero["output_ns"], invalid["output_ns"])

    def test_candidate_fails_on_incomplete_score_drain_and_extra_outputs(self):
        for fake, cap in ((FakePort([9], 3, score_adjust=-1), 255), (FakePort([9, 8], 3), 1),
                          (FakePort([319, 42], 3), 255)):
            with self.subTest(fake=fake, cap=cap), self.assertRaises(runtime.RequestFailure):
                runtime.compact_request(fake, (256,), cap, 1000)

    def test_candidate_rejects_invalid_terminal_state(self):
        for flag in (runtime.STATUS_OVERFLOW, runtime.STATUS_FAULT, runtime.STATUS_ACTIVE, runtime.STATUS_OUTPUT):
            with self.subTest(flag=flag), self.assertRaises(runtime.RequestFailure):
                runtime.compact_request(FakePort([9], 3, flags=48 | flag), (256,), 255, 1000)

    @unittest.skipUnless(os.environ.get("KV260_FRESH_TRACE_DIR"), "frozen KV260 physical traces not supplied")
    def test_against_three_exact_reference_traces(self):
        folder = Path(os.environ["KV260_FRESH_TRACE_DIR"])
        for index, pin in enumerate(FRESH_PINS, start=1):
            with self.subTest(index=index):
                path = folder / f"timed-01-{index}" / "runner.stdout"
                raw = path.read_bytes()
                self.assertEqual(sha256(raw).hexdigest(), pin)
                expected = json.loads(raw)["completion"]
                session = Session([frame["logits"] for frame in expected["frames"]])
                original = runtime.control_request(session, expected["prefix_tokens"], 255, Clock(), 1000)
                self.assertEqual(session.inputs, expected["input_tokens"])
                compact = runtime.compact_request(FakePort(expected["generated_tokens"], expected["context_count"]),
                                                  expected["prefix_tokens"], 255, 1000)
                for value in (original, compact):
                    value.update(prompt_hex=expected["prefix_utf8_hex"], prefix_ids=expected["prefix_tokens"])
                    runtime.compare_reference(value, expected)


if __name__ == "__main__":
    unittest.main()
