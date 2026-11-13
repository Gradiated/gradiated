import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from estimator import EnergyEstimator
from middleware import EnergyMiddleware, mark_generation_started


class EstimatorTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.estimator = EnergyEstimator(clock=lambda: self.now)
        self.estimator.started = True

    def test_concurrent_requests_share_energy_without_double_counting(self):
        self.estimator.sample(100)
        first = self.estimator.begin()
        self.now = 1
        second = self.estimator.begin()
        self.now = 2
        self.estimator.sample(200)
        first_joules = self.estimator.finish(first)
        self.now = 3
        second_joules = self.estimator.finish(second)
        self.assertEqual(first_joules, 150)
        self.assertEqual(second_joules, 250)
        self.assertEqual(first_joules + second_joules, 400)

    def test_idle_energy_is_not_assigned_to_the_next_request(self):
        self.estimator.sample(100)
        self.now = 1
        ticket = self.estimator.begin()
        self.now = 2
        self.assertEqual(self.estimator.finish(ticket), 100)

    def test_missing_stale_or_interrupted_readings_omit_the_estimate(self):
        for failure in ['missing', 'stale', 'interrupted']:
            with self.subTest(failure=failure):
                self.setUp()
                if failure != 'missing':
                    self.estimator.sample(100)
                ticket = self.estimator.begin()
                self.now = 1
                if failure == 'interrupted':
                    self.estimator.sample(None)
                    self.estimator.sample(100)
                if failure == 'stale':
                    self.now = 3
                self.assertIsNone(self.estimator.finish(ticket))
                self.assertEqual(self.estimator.active, 0)

    def test_invalid_power_is_unavailable(self):
        for power in [None, -1, float('nan'), float('inf')]:
            self.estimator.sample(power)
            ticket = self.estimator.begin()
            self.assertIsNone(self.estimator.finish(ticket))

    def test_sampler_sums_only_assigned_gpu_uuids(self):
        nvml = SimpleNamespace(nvmlInit=Mock(), nvmlDeviceGetHandleByUUID=Mock(side_effect=lambda uuid: uuid),
                               nvmlDeviceGetPowerUsage=Mock(side_effect=[100000, 200000]))
        with patch.dict(sys.modules, {'pynvml': nvml}), \
                patch.dict('os.environ', {'NVIDIA_VISIBLE_DEVICES': 'GPU-a,GPU-b'}), \
                patch('estimator.time.sleep', side_effect=StopIteration):
            with self.assertRaises(StopIteration):
                self.estimator._sample_forever()
        self.assertEqual(self.estimator.power, 300)
        self.assertEqual(nvml.nvmlDeviceGetHandleByUUID.call_args_list[0].args, ('GPU-a',))
        self.assertEqual(nvml.nvmlDeviceGetHandleByUUID.call_args_list[1].args, ('GPU-b',))

    def test_unavailable_nvml_or_ambiguous_gpu_assignment_does_not_raise(self):
        with patch.dict(sys.modules, {'pynvml': None}):
            self.estimator._sample_forever()
        nvml = SimpleNamespace(nvmlInit=Mock())
        for devices in ['', 'all', '0,1', 'GPU-a,GPU-a']:
            with patch.dict(sys.modules, {'pynvml': nvml}), \
                    patch.dict('os.environ', {'NVIDIA_VISIBLE_DEVICES': devices}):
                self.estimator._sample_forever()
        nvml.nvmlInit.assert_not_called()


class MiddlewareTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.now = 0
        self.estimator = EnergyEstimator(clock=lambda: self.now)
        self.estimator.started = True
        self.estimator.sample(100)

    async def run_response(self, chunks, streaming=False, status=200, path='/v1/chat/completions', headers=None, expected_active=0):
        sent = []

        async def app(scope, receive, send):
            if status == 200:
                mark_generation_started()
            response_headers = headers or [(b'content-type', b'text/event-stream' if streaming else b'application/json'),
                                            (b'content-length', str(sum(map(len, chunks))).encode())]
            await send({'type': 'http.response.start', 'status': status, 'headers': response_headers})
            for i, body in enumerate(chunks):
                self.now = 1
                await send({'type': 'http.response.body', 'body': body, 'more_body': i != len(chunks) - 1})

        async def send(message):
            sent.append(message)

        await EnergyMiddleware(app, self.estimator)({'type': 'http', 'path': path, 'method': 'POST'}, None, send)
        self.assertEqual(self.estimator.active, expected_active)
        return sent[0], b''.join(message.get('body', b'') for message in sent[1:])

    async def test_nonstreaming_adds_energy_and_preserves_tokens_and_choices(self):
        value = {'choices': [{'message': {'content': 'hello'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2}}
        encoded = json.dumps(value).encode()
        start, body = await self.run_response([encoded[:15], encoded[15:]])
        value['usage']['estimated_joules'] = 100
        self.assertEqual(json.loads(body), value)
        self.assertNotIn(b'content-length', dict(start['headers']))

    async def test_streaming_keeps_content_frames_and_adds_only_terminal_energy(self):
        content = b'data: {"choices":[{"delta":{"content":"hi"}}]}\n\n'
        terminal = b'data: {"choices":[],"usage":{"prompt_tokens":10,"completion_tokens":2}}\n\n'
        done = b'data: [DONE]\n\n'
        original = content + terminal + done
        _, body = await self.run_response([original[:7], original[7:55], original[55:]], streaming=True)
        self.assertTrue(body.startswith(content))
        self.assertTrue(body.endswith(done))
        usage = json.loads(body.split(b'\n\n')[1][6:])['usage']
        self.assertEqual(usage, {'prompt_tokens': 10, 'completion_tokens': 2, 'estimated_joules': 100})

    async def test_missing_energy_keeps_response_bytes(self):
        self.estimator.sample(None)
        for streaming, value in [(False, b'{"usage":{"prompt_tokens":1}}'),
                                 (True, b'data: {"choices":[],"usage":{"prompt_tokens":1}}\n\ndata: [DONE]\n\n')]:
            _, body = await self.run_response([value], streaming=streaming)
            self.assertEqual(body, value)

    async def test_errors_other_routes_and_malformed_responses_are_unchanged(self):
        for options, value in [({'status': 503}, b'{"error":"busy"}'),
                               ({'path': '/health'}, b'ok'),
                               ({}, b'not json'),
                               ({}, b'{"usage":null}'),
                               ({'streaming': True}, b'data: bad json\n\ndata: [DONE]\n\n'),
                               ({'headers': [(b'content-encoding', b'gzip')]}, b'compressed')]:
            with self.subTest(options=options):
                _, body = await self.run_response([value], **options)
                self.assertEqual(body, value)

    async def test_oversized_response_passes_through(self):
        with patch('middleware.MAX_BUFFER', 5):
            _, body = await self.run_response([b'{"usage":', b'{}}'])
        self.assertEqual(body, b'{"usage":{}}')

    async def test_disconnect_releases_request(self):
        async def app(*args):
            mark_generation_started()
            raise ConnectionError('disconnected')

        with self.assertRaises(ConnectionError):
            await EnergyMiddleware(app, self.estimator)({'type': 'http', 'path': '/v1/chat/completions', 'method': 'POST'}, None, None)
        self.assertEqual(self.estimator.active, 0)

    async def test_rejected_requests_do_not_dilute_a_valid_generation(self):
        valid_ticket = self.estimator.begin()
        self.now = .5

        _, body = await self.run_response([b'{"error":"invalid"}'], status=400, expected_active=1)

        self.assertEqual(body, b'{"error":"invalid"}')
        self.assertEqual(self.estimator.active, 1)
        self.now = 2
        self.assertEqual(self.estimator.finish(valid_ticket), 200)


if __name__ == '__main__':
    unittest.main()
