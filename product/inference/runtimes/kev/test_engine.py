import unittest

import adapter
from support import Probabilities, api, engine, rejecting_api, request

STATE_PREFIX_TOKENS = 401


def cached(e, data):
    return e.answer(data)["usage"]["cached_input_tokens"]


class UsageTests(unittest.TestCase):
    def test_cold_request_counts_every_encoded_token(self):
        e = engine()
        data = request()
        record, _ = api.to_record(api.SystemOneRequest.model_validate(data))
        encoded = e.server.model.encode(e.server.tok, record, max_state=8192, max_branch=8192, strict=True)

        usage = e.answer(data)["usage"]

        self.assertEqual(usage, {"input_tokens": len(encoded["ids"]), "cached_input_tokens": 0, "output_tokens": 0})

    def test_warm_request_reports_the_state_prefix_as_cached(self):
        e = engine()
        e.answer(request())

        self.assertEqual(cached(e, request()), STATE_PREFIX_TOKENS)
        self.assertEqual(e.server.model.calls, ["miss", "hit"])

    def test_cache_hit_returns_the_same_answers(self):
        e = engine()

        cold, warm = e.answer(request()), e.answer(request())

        self.assertEqual(cold["answers"], warm["answers"])
        self.assertEqual(cold["answers"]["choose"]["choice"], "a")
        self.assertEqual(cold["answers"]["yes"]["noul"], 0.5)
        self.assertEqual(cold["answers"]["rank"]["score"], 0.5)

    def test_changed_questions_reuse_the_state_prefix(self):
        e = engine()
        data = request()
        e.answer(data)
        data["questions"]["yes"]["instructions"] = "different?"

        self.assertEqual(cached(e, data), STATE_PREFIX_TOKENS)


class PrefixCacheTests(unittest.TestCase):
    def test_cache_holds_at_most_four_prefixes(self):
        e = engine()
        for char in "abcde":
            e.answer(request(char * 400))

        self.assertEqual(len(e.server.prefix_cache), 4)
        self.assertEqual(cached(e, request("a" * 400)), 0)
        self.assertEqual(cached(e, request("e" * 400)), STATE_PREFIX_TOKENS)

    def test_recently_used_prefix_survives_eviction(self):
        e = engine()
        for char in "abcd":
            e.answer(request(char * 400))
        e.answer(request("a" * 400))
        e.answer(request("e" * 400))

        self.assertEqual(cached(e, request("a" * 400)), STATE_PREFIX_TOKENS)
        self.assertEqual(cached(e, request("b" * 400)), 0)

    def test_short_state_is_never_cached(self):
        e = engine()

        for _ in range(2):
            self.assertEqual(cached(e, request("short")), 0)
        self.assertFalse(e.server.prefix_cache)

    def test_option_isolation_separates_cache_entries(self):
        e = engine()
        e.answer(request())
        e.server.model.isolation = True

        self.assertEqual(cached(e, request()), 0)


class FailureTests(unittest.TestCase):
    def test_model_failure_clears_the_cache(self):
        e = engine()
        e.answer(request())
        e.server.model.fail = True

        with self.assertRaises(RuntimeError):
            e.answer(request())

        self.assertFalse(e.server.prefix_cache)
        e.server.model.fail = False
        self.assertEqual(cached(e, request()), 0)

    def test_model_failure_synchronizes_the_device_before_raising(self):
        synced = []
        e = engine(synced.append)
        e.answer(request())
        synced.clear()
        e.server.model.fail = True

        with self.assertRaises(RuntimeError):
            e.answer(request())

        self.assertEqual(synced, ["stub", "stub"])

    def test_invalid_model_output_is_rejected_and_clears_the_cache(self):
        outputs = {"missing question": [Probabilities([0.5, 0.5])],
                   "nonfinite": [Probabilities([float("nan"), 0.5])] * 3,
                   "wrong option count": [Probabilities([1.0])] * 3}
        for name, output in outputs.items():
            with self.subTest(name):
                synced = []
                e = engine(synced.append)
                e.answer(request())
                synced.clear()
                e.server.model.output = output

                with self.assertRaises(adapter.InvalidModelOutput):
                    e.answer(request())

                self.assertFalse(e.server.prefix_cache)
                self.assertEqual(synced, ["stub", "stub", "stub"])

    def test_upstream_schema_rejection_is_an_invalid_request(self):
        e = engine()
        e.answer(request())
        e.api = rejecting_api
        cache = dict(e.server.prefix_cache)

        with self.assertRaisesRegex(adapter.InvalidRequest, "^invalid request$"):
            e.answer(request())

        self.assertEqual(e.server.prefix_cache, cache)
        self.assertEqual(e.server.model.calls, ["miss"])

    def test_token_limits_are_enforced_before_the_forward_pass(self):
        packed = request("")
        packed["questions"] = {str(i): {"type": "noul", "instructions": "x" * 150} for i in range(64)}
        padded = request("x" * 400)
        padded["questions"] = {str(i): {"type": "noul", "instructions": "?"} for i in range(64)}
        cases = {"state": request("x" * 8192), "state plus question": request("x" * 8170),
                 "packed": packed, "padded rows": padded}
        for name, data in cases.items():
            with self.subTest(name):
                e = engine()

                with self.assertRaises(adapter.InvalidRequest):
                    e.answer(data)

                self.assertFalse(e.server.model.calls)
