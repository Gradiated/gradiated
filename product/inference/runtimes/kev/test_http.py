import asyncio
import json
import threading
import unittest
from unittest import mock

import adapter
from support import Probabilities, call, engine, exchange, rejecting_api, request

TOKEN = b"test-only-credential"
JSON = (b"content-type", b"application/json")
BEARER = (b"authorization", b"Bearer " + TOKEN)


class BlockingEngine:
    model = adapter.MODEL

    def __init__(self, log=None):
        self.entered, self.release = threading.Event(), threading.Event()
        self.log = log if log is not None else []

    def answer(self, data):
        self.entered.set()
        if not self.release.wait(5):
            raise RuntimeError("test timeout")

        self.log.append("worker finished")
        return {"done": True}


class AuthTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = adapter.App(engine(), TOKEN)

    async def test_missing_token_is_rejected_on_every_route(self):
        for path, method in (("/health", "GET"), ("/v1/models", "GET"), ("/metrics", "GET"), ("/v1/systemone", "POST")):
            with self.subTest(path):
                status, body = await call(self.app, request(), path=path, method=method, headers=[JSON])
                self.assertEqual((status, body), (401, {"error": {"message": "unauthorized"}}))

    async def test_valid_bearer_token_is_accepted(self):
        self.assertEqual((await call(self.app, request(), headers=[JSON, BEARER]))[0], 200)

    async def test_wrong_token_is_rejected(self):
        headers = [JSON, (b"authorization", b"Bearer wrong-test-only-credential")]

        self.assertEqual((await call(self.app, request(), headers=headers))[0], 401)

    async def test_token_without_bearer_prefix_is_rejected(self):
        headers = [JSON, (b"authorization", TOKEN)]

        self.assertEqual((await call(self.app, request(), headers=headers))[0], 401)

    async def test_duplicate_authorization_headers_are_rejected(self):
        self.assertEqual((await call(self.app, request(), headers=[JSON, BEARER, BEARER]))[0], 401)


class RouteTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = adapter.App(engine())

    async def test_health_reports_the_served_model(self):
        response = await call(self.app, path="/health", method="GET")

        self.assertEqual(response, (200, {"status": "ok", "model": adapter.MODEL}))

    async def test_models_lists_only_the_served_model(self):
        response = await call(self.app, path="/v1/models", method="GET")

        self.assertEqual(response, (200, {"models": [{"id": adapter.MODEL}]}))

    async def test_metrics_report_an_idle_runtime(self):
        sent = await exchange(self.app, path="/metrics", method="GET")

        self.assertEqual(sent[0]["status"], 200)
        self.assertIn(b"kev_busy 0\n", sent[1]["body"])
        self.assertIn(b"kev_busy_rejections_total 0\n", sent[1]["body"])

    async def test_unknown_path_is_not_found(self):
        self.assertEqual((await call(self.app, request(), path="/v1/chat/completions"))[0], 404)

    async def test_get_systemone_is_not_allowed(self):
        response = await call(self.app, path="/v1/systemone", method="GET")

        self.assertEqual(response, (405, {"error": {"message": "method not allowed"}}))

    async def test_systemone_answers_with_usage(self):
        status, body = await call(self.app, request())

        self.assertEqual(status, 200)
        self.assertEqual(body["model"], adapter.MODEL)
        self.assertEqual(set(body["answers"]), {"choose", "yes", "rank"})
        self.assertEqual(body["usage"]["output_tokens"], 0)


class BodyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.app = adapter.App(engine())

    async def test_declared_oversized_body_is_rejected(self):
        headers = [JSON, (b"content-length", str(adapter.MAX_BODY + 1).encode())]

        self.assertEqual((await call(self.app, headers=headers))[0], 413)

    async def test_streamed_oversized_body_is_rejected(self):
        chunks = [{"type": "http.request", "body": b"x" * adapter.MAX_BODY, "more_body": True},
                  {"type": "http.request", "body": b"x"}]

        self.assertEqual((await call(self.app, chunks=chunks))[0], 413)

    async def test_chunked_body_is_reassembled(self):
        body = json.dumps(request()).encode()
        chunks = [{"type": "http.request", "body": body[:10], "more_body": True},
                  {"type": "http.request", "body": body[10:]}]

        self.assertEqual((await call(self.app, chunks=chunks))[0], 200)

    async def test_non_numeric_content_length_is_rejected(self):
        headers = [JSON, (b"content-length", b"many")]

        response = await call(self.app, request(), headers=headers)

        self.assertEqual(response, (400, {"error": {"message": "invalid content-length"}}))

    async def test_signed_content_length_is_rejected(self):
        for length in (b"-1", b"+5"):
            with self.subTest(length):
                response = await call(self.app, request(), headers=[JSON, (b"content-length", length)])
                self.assertEqual(response, (400, {"error": {"message": "invalid content-length"}}))

    async def test_missing_content_type_is_rejected(self):
        self.assertEqual((await call(self.app, request(), headers=[]))[0], 415)

    async def test_other_content_type_is_rejected(self):
        self.assertEqual((await call(self.app, request(), headers=[(b"content-type", b"text/plain")]))[0], 415)

    async def test_json_with_charset_is_accepted(self):
        headers = [(b"content-type", b"application/json; charset=utf-8")]

        self.assertEqual((await call(self.app, request(), headers=headers))[0], 200)

    async def test_slow_body_times_out(self):
        async def receive():
            await asyncio.sleep(1)

        sent = []

        async def send(event):
            sent.append(event)

        scope = {"type": "http", "path": "/v1/systemone", "method": "POST", "headers": [JSON]}
        with mock.patch.object(adapter, "BODY_READ_TIMEOUT_SECONDS", 0.01):
            await self.app(scope, receive, send)

        self.assertEqual(sent[0]["status"], 408)
        self.assertEqual((await call(self.app, request()))[0], 200)

    async def test_disconnect_before_body_sends_nothing(self):
        self.assertEqual(await exchange(self.app, chunks=[{"type": "http.disconnect"}]), [])
        self.assertEqual((await call(self.app, request()))[0], 200)


class AdmissionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.engine = BlockingEngine()
        self.app = adapter.App(self.engine)
        self.first = asyncio.create_task(call(self.app, request()))
        self.assertTrue(await asyncio.to_thread(self.engine.entered.wait, 2))

    async def asyncTearDown(self):
        self.engine.release.set()
        await asyncio.gather(self.first, *self.app.tasks, return_exceptions=True)

    async def test_concurrent_request_is_rejected_with_retry_after(self):
        sent = await exchange(self.app, request())

        self.assertEqual(sent[0]["status"], 429)
        self.assertIn((b"retry-after", b"1"), sent[0]["headers"])

    async def test_cancelled_request_keeps_the_slot_until_the_worker_finishes(self):
        self.first.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await self.first

        self.assertEqual((await call(self.app, request()))[0], 429)
        self.engine.release.set()
        await asyncio.gather(*self.app.tasks)
        self.assertEqual((await call(self.app, request()))[0], 200)

    async def test_health_stays_responsive_while_busy(self):
        self.assertEqual((await call(self.app, path="/health", method="GET"))[0], 200)

    async def test_metrics_report_the_busy_slot_and_rejections(self):
        await exchange(self.app, request())

        body = (await exchange(self.app, path="/metrics", method="GET"))[1]["body"]
        self.assertIn(b"kev_busy 1\n", body)
        self.assertIn(b"kev_busy_rejections_total 1\n", body)


class InferenceErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_model_failure_hides_the_cause_and_recovers(self):
        e = engine()
        app = adapter.App(e)
        await call(app, request())
        e.server.model.fail = True

        with self.assertLogs("kev.adapter", "ERROR"):
            self.assertEqual(await call(app, request()), (500, {"error": {"message": "inference failed"}}))
        e.server.model.fail = False
        self.assertEqual((await call(app, request()))[0], 200)

    async def test_model_failure_logs_a_bounded_code_without_the_payload(self):
        e = engine()
        app = adapter.App(e)
        await call(app, request())
        e.server.model.fail = True

        with self.assertLogs("kev.adapter", "ERROR") as logs:
            await call(app, request())

        self.assertEqual(logs.output, ["ERROR:kev.adapter:inference_failed error=RuntimeError"])

    async def test_invalid_model_output_logs_its_own_code(self):
        e = engine()
        e.server.model.output = [Probabilities([1.0])] * 3

        with self.assertLogs("kev.adapter", "ERROR") as logs:
            self.assertEqual((await call(adapter.App(e), request()))[0], 500)

        self.assertEqual(logs.output, ["ERROR:kev.adapter:invalid_model_output error=InvalidModelOutput"])

    async def test_upstream_schema_rejection_is_an_invalid_request(self):
        app = adapter.App(engine(upstream=rejecting_api))

        with self.assertNoLogs("kev.adapter"):
            response = await call(app, request())

        self.assertEqual(response, (422, {"error": {"message": "invalid request"}}))

    async def test_token_limit_is_an_invalid_request_and_logs_nothing(self):
        with self.assertNoLogs("kev.adapter"):
            self.assertEqual((await call(adapter.App(engine()), request("x" * 8192)))[0], 422)


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_idle_startup_and_shutdown_complete(self):
        events = [{"type": "lifespan.startup"}, {"type": "lifespan.shutdown"}]
        sent = []

        async def receive():
            return events.pop(0)

        async def send(event):
            sent.append(event["type"])

        await adapter.App(engine())({"type": "lifespan"}, receive, send)

        self.assertEqual(sent, ["lifespan.startup.complete", "lifespan.shutdown.complete"])

    async def test_shutdown_waits_for_the_in_flight_worker(self):
        log = []
        blocking = BlockingEngine(log)
        app = adapter.App(blocking)
        inflight = asyncio.create_task(call(app, request()))
        self.assertTrue(await asyncio.to_thread(blocking.entered.wait, 2))
        shutdown_requested = asyncio.Event()

        async def receive():
            shutdown_requested.set()
            return {"type": "lifespan.shutdown"}

        async def send(event):
            log.append(event["type"])

        lifespan = asyncio.create_task(app({"type": "lifespan"}, receive, send))
        await shutdown_requested.wait()
        for _ in range(5):
            await asyncio.sleep(0)

        self.assertEqual(log, [])
        blocking.release.set()
        await asyncio.wait_for(lifespan, 5)
        self.assertEqual(log, ["worker finished", "lifespan.shutdown.complete"])
        self.assertEqual((await inflight)[0], 200)
