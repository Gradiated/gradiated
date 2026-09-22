"""CPU-only doubles; optionally exercise the local pinned API/encoder too."""
import ast
import asyncio
import json
import os
from pathlib import Path
import re
import sys
import threading
from types import SimpleNamespace
import unittest

import adapter

SOURCE = Path(os.environ["KEV_SOURCE"]) if os.environ.get("KEV_SOURCE") else None
namespace = {"re": re, "_SPECIAL_RE": re.compile(r"<\|([A-Za-z0-9_]+)\|>"),
             "SPECIAL": ["<|fim_prefix|>", "<|fim_middle|>", "<|box_start|>", "<|box_end|>", "<|fim_suffix|>"],
             "MAX_STATE": 384, "MAX_BRANCH": 1024, "OPT_NONE": -1, "OPT_DECIDE": -2}
if SOURCE is not None:
    sys.path.insert(0, str(SOURCE))
    from kev import api

    # Execute only pure upstream functions, without importing torch/transformers.
    tree = ast.parse((SOURCE / "kev/model.py").read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)
                 and node.name in ("user_tokens", "encode")]
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE / "kev/model.py"), "exec"), namespace)
else:
    from test_support import api, encode
    namespace["encode"] = encode


class Tokenizer:
    def __call__(self, text, **kwargs):
        return SimpleNamespace(input_ids=[ord(char) for char in text])

    def convert_tokens_to_ids(self, token):
        return 100000 + namespace["SPECIAL"].index(token)


class Probabilities(list):
    def tolist(self):
        return list(self)


class Model:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.isolation = False

    def encode(self, tok, rec, **kwargs):
        return namespace["encode"](tok, rec, option_isolation=self.isolation, **kwargs)

    def probs(self, enc):
        self.calls.append("plain")
        return [Probabilities([1 / len(options)] * len(options)) for options in enc["opt_idx"]]

    def probs_and_prefix(self, enc):
        result = self.probs(enc)
        self.calls[-1] = "miss"
        return result, tuple(enc["ids"][:enc["seg"].count(0)])

    def probs_with_prefix(self, enc, prefix):
        if self.fail:
            raise RuntimeError("secret model payload must not leak")
        assert prefix == tuple(enc["ids"][:enc["seg"].count(0)])
        result = self.probs(enc)
        self.calls[-1] = "hit"
        return result


def engine():
    server = SimpleNamespace(model=Model(), tok=Tokenizer(), prefix_cache={}, lock=threading.Lock(),
                             prefix_hits=0, prefix_misses=0, device="stub")
    return adapter.Engine(server, api, lambda device: None)


def request(state="x" * 400):
    return {"model": adapter.MODEL, "state": state, "questions": {
        "choose": {"type": "choice", "instructions": "pick", "criteria": {"a": "A", "b": "B"}},
        "yes": {"type": "noul", "instructions": "yes?"},
        "rank": {"type": "score", "instructions": "rank", "criteria": ["low", "high"]}}}


async def call(app, data=None, *, path="/v1/systemone", method="POST", headers=None, chunks=None):
    body = json.dumps(data).encode() if data is not None else b""
    events = list(chunks) if chunks is not None else [{"type": "http.request", "body": body}]
    sent = []

    async def receive():
        return events.pop(0)

    async def send(event):
        sent.append(event)

    await app({"type": "http", "path": path, "method": method,
               "headers": [(k.lower(), v) for k, v in headers] if headers is not None
               else [(b"content-type", b"application/json")]}, receive, send)
    if not sent:
        return None, None
    return sent[0]["status"], json.loads(sent[1]["body"])


class ModelTests(unittest.TestCase):
    def test_answers_and_authoritative_usage(self):
        e = engine()
        data = request()
        cold, warm = e.answer(data), e.answer(data)
        rec, _ = api.to_record(api.SystemOneRequest.model_validate(data))
        encoded = e.server.model.encode(e.server.tok, rec, max_state=8192, max_branch=8192, strict=True)
        self.assertEqual(cold["usage"], {"input_tokens": len(encoded["ids"]), "cached_input_tokens": 0, "output_tokens": 0})
        self.assertEqual(warm["usage"]["cached_input_tokens"], 401)
        self.assertEqual(cold["answers"], warm["answers"])
        self.assertEqual(cold["answers"]["choose"]["choice"], "a")
        self.assertEqual(cold["answers"]["yes"]["noul"], 0.5)
        self.assertEqual(cold["answers"]["rank"]["score"], 0.5)
        # Changing branches still reuses only the exact state prefix.
        data["questions"]["yes"]["instructions"] = "different?"
        self.assertEqual(e.answer(data)["usage"]["cached_input_tokens"], 401)
        self.assertEqual(e.server.model.calls, ["miss", "hit", "hit"])

    def test_lru_and_error_invalidation(self):
        e = engine()
        for char in "abcd":
            e.answer(request(char * 400))
        e.answer(request("a" * 400))  # a is most recently used, b is next evicted.
        e.answer(request("e" * 400))
        self.assertEqual(len(e.server.prefix_cache), 4)
        self.assertEqual(e.answer(request("a" * 400))["usage"]["cached_input_tokens"], 401)
        self.assertEqual(e.answer(request("b" * 400))["usage"]["cached_input_tokens"], 0)
        e.server.model.fail = True
        with self.assertRaises(RuntimeError):
            e.answer(request("b" * 400))
        self.assertFalse(e.server.prefix_cache)
        e.server.model.fail = False
        self.assertEqual(e.answer(request("b" * 400))["usage"]["cached_input_tokens"], 0)

    def test_short_state_and_isolation(self):
        e = engine()
        for _ in range(2):
            self.assertEqual(e.answer(request("short"))["usage"]["cached_input_tokens"], 0)
        self.assertFalse(e.server.prefix_cache)
        e.answer(request())
        e.server.model.isolation = True
        self.assertEqual(e.answer(request())["usage"]["cached_input_tokens"], 0)

    def test_token_limits_precede_forward(self):
        e = engine()
        cases = [request("x" * 8192), request("x" * 8170)]
        packed = request("")
        packed["questions"] = {str(i): {"type": "noul", "instructions": "x" * 150} for i in range(64)}
        cases.append(packed)
        # A tiny packed sequence can still create excessive padded hybrid rows.
        padded = request("x" * 400)
        padded["questions"] = {str(i): {"type": "noul", "instructions": "?"} for i in range(64)}
        cases.append(padded)
        for data in cases:
            with self.subTest(size=len(data["questions"])):
                with self.assertRaises(adapter.InvalidRequest):
                    e.answer(data)
        self.assertFalse(e.server.model.calls)


class HttpTests(unittest.IsolatedAsyncioTestCase):
    async def test_routes_auth_and_priorities(self):
        app = adapter.App(engine(), b"test-only-credential")
        good = [(b"content-type", b"application/json"), (b"authorization", b"Bearer test-only-credential")]
        self.assertEqual((await call(app, path="/health", method="GET"))[0], 401)
        self.assertEqual((await call(app, path="/health", method="GET", headers=good))[0], 200)
        status, models = await call(app, path="/v1/models", method="GET", headers=good)
        self.assertEqual(models, {"models": [{"id": adapter.MODEL}]})
        for priority in (-10, 0, 10):
            self.assertEqual((await call(app, {**request(), "priority": priority}, headers=good))[0], 200)
        self.assertEqual((await call(app, request(), headers=good + [good[-1]]))[0], 401)
        self.assertEqual((await call(app, path="/v1/chat/completions", headers=good))[0], 404)

    async def test_strict_validation(self):
        app = adapter.App(engine())
        mutations = [{"model": "kev-latest"}, {"model": "other"}, {"priority": True}, {"priority": 10.0},
                     {"priority": 1}, {"priority": "0"}, {"extra": 1}, {"questions": {}},
                     {"state": float("nan")}, {"state": float("inf")},
                     {"questions": {str(i): {"type": "noul", "instructions": "?"} for i in range(65)}}]
        for change in mutations:
            self.assertEqual((await call(app, {**request(), **change}))[0], 422, change)
        for question in ({"type": "choice", "instructions": "?", "criteria": {}},
                         {"type": "score", "instructions": "?", "criteria": ["a"]},
                         {"type": "noul", "instructions": "?", "ignored": True},
                         {"type": "noul", "instructions": "?", "criteria": {"typo": "x"}}):
            self.assertEqual((await call(app, {**request(), "questions": {"q": question}}))[0], 422)
        for body in (b'{"model": "a", "model": "b"}', b'{', b'\xff'):
            self.assertEqual((await call(app, chunks=[{"type": "http.request", "body": body}]))[0], 422)
        nested = "leaf"
        for _ in range(33):
            nested = [nested]
        self.assertEqual((await call(app, request(nested)))[0], 422)
        self.assertEqual((await call(app, request()))[0], 200)

    async def test_state_types_are_validated_before_inference(self):
        seen = []

        class RecordingEngine:
            def answer(self, data):
                seen.append(data["state"])
                return {"ok": True}

        app = adapter.App(RecordingEngine())
        for state in (None, True, False, 0, 42, 1.5):
            with self.subTest(rejected=state):
                self.assertEqual((await call(app, request(state)))[0], 422)
        missing = request()
        del missing["state"]
        self.assertEqual((await call(app, missing))[0], 422)
        self.assertEqual(seen, [])
        accepted = ["", "text", {}, {"value": 42}, [], [None, True, 1.5]]
        for state in accepted:
            with self.subTest(accepted=state):
                self.assertEqual((await call(app, request(state)))[0], 200)
        self.assertEqual(seen, accepted)

    async def test_question_count_and_key_boundaries(self):
        app = adapter.App(engine())
        data = request("")
        data["questions"] = {str(i): {"type": "noul", "instructions": "?"} for i in range(64)}
        self.assertEqual((await call(app, data))[0], 200)
        data["questions"] = {"k" * 200: {"type": "noul", "instructions": "?"}}
        self.assertEqual((await call(app, data))[0], 200)
        data["questions"] = {"k" * 201: {"type": "noul", "instructions": "?"}}
        self.assertEqual((await call(app, data))[0], 422)

    async def test_body_limits_and_disconnect(self):
        app = adapter.App(engine())
        headers = [(b"content-type", b"application/json"), (b"content-length", str(adapter.MAX_BODY + 1).encode())]
        self.assertEqual((await call(app, headers=headers))[0], 413)
        self.assertEqual((await call(app, chunks=[{"type": "http.request", "body": b"x" * adapter.MAX_BODY, "more_body": True},
                                                {"type": "http.request", "body": b"x"}]))[0], 413)
        self.assertEqual((await call(app, request(), headers=[]))[0], 415)
        self.assertEqual(await call(app, chunks=[{"type": "http.disconnect"}]), (None, None))
        self.assertEqual((await call(app, request()))[0], 200)

    async def test_busy_and_cancellation_keep_slot_until_worker_finishes(self):
        entered, release = threading.Event(), threading.Event()

        class Slow:
            def answer(self, data):
                entered.set()
                if not release.wait(5):
                    raise RuntimeError("test timeout")
                return {"done": True}

        app = adapter.App(Slow())
        first = asyncio.create_task(call(app, request()))
        try:
            self.assertTrue(await asyncio.to_thread(entered.wait, 2))
            self.assertEqual((await call(app, request()))[0], 429)
            first.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await first
            self.assertEqual((await call(app, request()))[0], 429)
            self.assertEqual((await call(app, path="/health", method="GET"))[0], 200)
        finally:
            release.set()
            await asyncio.gather(*app.tasks, return_exceptions=True)
        self.assertEqual((await call(app, request()))[0], 200)

    async def test_safe_error_and_recovery(self):
        e = engine()
        app = adapter.App(e)
        await call(app, request())
        e.server.model.fail = True
        status, body = await call(app, request())
        self.assertEqual(status, 500)
        self.assertEqual(body, {"error": {"message": "inference failed"}})
        e.server.model.fail = False
        self.assertEqual((await call(app, request()))[0], 200)
        self.assertEqual((await call(app, request("x" * 8192)))[0], 422)


if __name__ == "__main__":
    unittest.main()
