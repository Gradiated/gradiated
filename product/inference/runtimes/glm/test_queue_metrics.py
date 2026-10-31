import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest

source = Path(__file__).with_name('queue_metrics.py')
if source.exists():
    spec = importlib.util.spec_from_file_location('queue_metrics', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
else:
    import gradiated_queue_metrics as module


class QueueTelemetryTests(unittest.TestCase):
    def invoke(self, path='/metrics', engine=True, status=200, compressed=False):
        config = SimpleNamespace(max_num_queued_tokens=32768, max_num_queued_reqs=None)
        client = SimpleNamespace(scheduler_config=config, get_num_queued_tokens=lambda: 1000000,
                                 get_num_unfinished_requests=lambda: 4)
        scope = {'type': 'http', 'path': path, 'headers': [(b'accept-encoding', b'gzip')],
                 'app': SimpleNamespace(state=SimpleNamespace(engine_client=client if engine else None))}
        sent, received = [], []

        async def app(incoming, _receive, send):
            received.append(incoming)
            headers = [(b'content-length', b'10')]
            if compressed:
                headers.append((b'content-encoding', b'gzip'))
            await send({'type': 'http.response.start', 'status': status, 'headers': headers})
            await send({'type': 'http.response.body', 'body': b'native 1\n', 'more_body': True})
            await send({'type': 'http.response.body', 'body': b'\n'})

        async def send(message):
            sent.append(message)
        asyncio.run(module.QueueMetricsMiddleware(app)(scope, None, send))
        return sent, received[0]

    def test_metrics_preserve_native_stream_and_report_actual_frontend_counts(self):
        sent, incoming = self.invoke()
        body = b''.join(item.get('body', b'') for item in sent)
        self.assertTrue(body.startswith(b'native 1\n'))
        self.assertIn(b'gradiated_runtime_prefill_backlog_prompt_tokens 1000000\n', body)
        self.assertIn(b'gradiated_runtime_inflight_requests 4\n', body)
        self.assertIn(b'gradiated_runtime_queue_token_limit 32768\n', body)
        self.assertIn(b'gradiated_runtime_queue_request_limit -1\n', body)
        self.assertNotIn((b'content-length', b'10'), sent[0]['headers'])
        self.assertIn((b'accept-encoding', b'identity'), incoming['headers'])

    def test_inference_requests_pass_through_untouched(self):
        sent, incoming = self.invoke('/v1/chat/completions')
        self.assertEqual(b''.join(item.get('body', b'') for item in sent), b'native 1\n\n')
        self.assertIn((b'accept-encoding', b'gzip'), incoming['headers'])

    def test_missing_engine_is_reported_without_breaking_metrics(self):
        sent, _ = self.invoke(engine=False)
        self.assertIn(b'gradiated_runtime_queue_telemetry_available 0\n', sent[-1]['body'])

    def test_errors_and_unexpected_compression_are_not_modified(self):
        for options in ({'status': 503}, {'compressed': True}):
            with self.subTest(options=options):
                sent, _ = self.invoke(**options)
                self.assertNotIn(b'gradiated_runtime_', sent[-1]['body'])
                self.assertIn((b'content-length', b'10'), sent[0]['headers'])


if __name__ == '__main__':
    unittest.main()
