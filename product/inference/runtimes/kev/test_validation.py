import unittest

import adapter
from support import call, engine, request


def noul_questions(count):
    return {str(i): {"type": "noul", "instructions": "?"} for i in range(count)}


class RecordingEngine:
    model = adapter.MODEL

    def __init__(self):
        self.states = []

    def answer(self, data):
        self.states.append(data["state"])
        return {"ok": True}


class RequestSchemaTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_top_level_fields_are_rejected(self):
        app = adapter.App(engine())
        mutations = [{"model": "kev-latest"}, {"model": "other"}, {"priority": True}, {"priority": 10.0},
                     {"priority": 1}, {"priority": "0"}, {"extra": 1}, {"questions": {}},
                     {"questions": noul_questions(65)}]
        for change in mutations:
            with self.subTest(change):
                self.assertEqual((await call(app, {**request(), **change}))[0], 422)

    async def test_missing_model_is_rejected(self):
        data = request()
        del data["model"]

        self.assertEqual((await call(adapter.App(engine()), data))[0], 422)

    async def test_supported_priorities_are_accepted(self):
        app = adapter.App(engine())
        for priority in (-10, 0, 10):
            with self.subTest(priority):
                self.assertEqual((await call(app, {**request(), "priority": priority}))[0], 200)

    async def test_invalid_questions_are_rejected(self):
        app = adapter.App(engine())
        questions = [{"type": "choice", "instructions": "?", "criteria": {}},
                     {"type": "score", "instructions": "?", "criteria": []},
                     {"type": "noul", "instructions": "?", "ignored": True},
                     {"type": "noul", "instructions": "?", "criteria": {"typo": "x"}},
                     {"type": "other", "instructions": "?"}]
        for question in questions:
            with self.subTest(question):
                self.assertEqual((await call(app, {**request(), "questions": {"q": question}}))[0], 422)

    async def test_typesafe_optional_instructions_and_one_level_scores_are_accepted(self):
        # TypeSafe's API accepts both; its SDK omits instructions for criteria-only questions.
        app = adapter.App(engine())
        questions = [{"type": "noul"},
                     {"type": "noul", "criteria": {"true": "Angry", "false": "Calm"}},
                     {"type": "choice", "criteria": {"billing": "Charges", "access": "Login"}},
                     {"type": "score", "criteria": ["calm", "annoyed", "furious"]},
                     {"type": "score", "instructions": "Rate", "criteria": ["only"]}]
        for question in questions:
            with self.subTest(question):
                self.assertEqual(adapter.validate({**request(), "questions": {"q": question}})["questions"]["q"],
                                 question)
                status, body = await call(app, {**request(), "questions": {"q": question}})
                self.assertEqual(status, 200)
                self.assertEqual(body["answers"]["q"]["type"], question["type"])


class JsonBoundsTests(unittest.IsolatedAsyncioTestCase):
    async def test_nonfinite_numbers_are_rejected(self):
        app = adapter.App(engine())
        for value in (float("nan"), float("inf")):
            with self.subTest(value):
                self.assertEqual((await call(app, request({"value": value})))[0], 422)

    async def test_nesting_is_bounded_at_thirty_two_levels(self):
        app = adapter.App(RecordingEngine())
        for wraps, status in ((31, 200), (32, 422)):
            state = "leaf"
            for _ in range(wraps):
                state = [state]

            with self.subTest(wraps):
                self.assertEqual((await call(app, request(state)))[0], status)

    async def test_duplicate_keys_are_rejected(self):
        body = b'{"model": "a", "model": "b"}'

        self.assertEqual((await call(adapter.App(engine()), chunks=[{"type": "http.request", "body": body}]))[0], 422)

    async def test_malformed_json_is_rejected(self):
        app = adapter.App(engine())
        for body in (b'{', b'\xff', b''):
            with self.subTest(body):
                self.assertEqual((await call(app, chunks=[{"type": "http.request", "body": body}]))[0], 422)


class StateTypeTests(unittest.IsolatedAsyncioTestCase):
    async def test_scalar_and_missing_states_never_reach_inference(self):
        recorder = RecordingEngine()
        app = adapter.App(recorder)
        missing = request()
        del missing["state"]
        for data in [request(state) for state in (None, True, False, 0, 42, 1.5)] + [missing]:
            with self.subTest(data.get("state", "missing")):
                self.assertEqual((await call(app, data))[0], 422)

        self.assertEqual(recorder.states, [])

    async def test_string_object_and_array_states_are_accepted(self):
        recorder = RecordingEngine()
        app = adapter.App(recorder)
        accepted = ["", "text", {}, {"value": 42}, [], [None, True, 1.5]]
        for state in accepted:
            with self.subTest(state):
                self.assertEqual((await call(app, request(state)))[0], 200)

        self.assertEqual(recorder.states, accepted)


class QuestionBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_sixty_four_questions_are_accepted(self):
        self.assertEqual((await call(adapter.App(engine()), {**request(""), "questions": noul_questions(64)}))[0], 200)

    async def test_question_key_length_is_bounded(self):
        app = adapter.App(engine())
        for key, status in (("k" * 200, 200), ("k" * 201, 422), ("", 422)):
            with self.subTest(len(key)):
                data = {**request(""), "questions": {key: {"type": "noul", "instructions": "?"}}}
                self.assertEqual((await call(app, data))[0], status)
