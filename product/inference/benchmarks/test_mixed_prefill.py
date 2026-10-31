import http.server
import io
import tempfile
from unittest.mock import patch
import importlib.util
import json
from pathlib import Path
import threading
import time
import unittest

spec = importlib.util.spec_from_file_location('mixed_prefill', Path(__file__).with_name('mixed_prefill.py'))
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


class StreamingMeasurementTests(unittest.TestCase):
    def measure(self, mode, protocol="completions", idle_timeout=30, first_signal=None, request_deadline=630):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.server.seen = (self.path, payload)
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                events = [
                    {'choices': [{'text': ''}]},
                    {'choices': [{'text': 'hello'}]},
                    {'choices': [{'text': ' world'}]},
                    {'choices': [], 'usage': {'prompt_tokens': 16,
                                              'completion_tokens': payload['max_tokens'] + (mode == 'bad_usage')}},
                ]
                if mode == 'empty':
                    events = [events[0], events[-1]]
                if protocol == 'chat':
                    for event in events:
                        for choice in event.get('choices', []):
                            choice['delta'] = {'reasoning': choice.pop('text')}
                if mode == 'prefill_stall':
                    time.sleep(.1)
                    return
                if mode == 'prefill':
                    time.sleep(.1)
                for index, event in enumerate(events):
                    self.wfile.write(b'data: ' + json.dumps(event).encode() + b'\n\n')
                    self.wfile.flush()
                    if mode == 'slow' and index == 1:
                        time.sleep(.1)
                        return
                    time.sleep(.01)
                if mode != 'truncated':
                    self.wfile.write(b'data: [DONE]\n\n')
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            row = benchmark.request(f'http://127.0.0.1:{server.server_port}', 'test', 16, 2, 123, 0, time.monotonic(),
                                    protocol, ([{'role': 'user', 'content': 'test'}], 16), idle_timeout, request_deadline, first_signal)
            if protocol == 'chat':
                self.assertEqual(server.seen[0], '/v1/chat/completions')
                self.assertIn('messages', server.seen[1])
                self.assertNotIn('prompt', server.seen[1])
            return row
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_stream_records_nonempty_events_and_exact_usage(self):
        row = self.measure('ok')
        self.assertTrue(row['ok'], row)
        self.assertEqual(row['stream_events'], 2)
        self.assertEqual(row['usage']['prompt_tokens'], 16)
        self.assertGreater(row['stream_gap_max_s'], 0)
        self.assertGreater(row['elapsed_s'], row['ttft_s'])

    def test_chat_reasoning_stream_is_timed_through_chat_endpoint(self):
        row = self.measure('ok', 'chat')
        self.assertTrue(row['ok'], row)
        self.assertEqual(row['stream_events'], 2)

    def test_production_idle_limit_rejects_a_stalled_stream(self):
        row = self.measure('slow', idle_timeout=.01)
        self.assertFalse(row['ok'])
        self.assertIn('timed out', row['error'])

    def test_prefill_can_exceed_the_generation_idle_limit(self):
        row = self.measure('prefill', idle_timeout=.05)
        self.assertTrue(row['ok'], row)
        self.assertGreater(row['ttft_s'], .1)

    def test_total_deadline_still_bounds_prefill(self):
        row = self.measure('prefill_stall', idle_timeout=.01, request_deadline=.03)
        self.assertFalse(row['ok'])
        self.assertIn('timed out', row['error'])

    def test_long_prompt_gate_waits_for_nonempty_output(self):
        signal = threading.Event()
        self.assertFalse(self.measure('empty', first_signal=signal)['ok'])
        self.assertFalse(signal.is_set())
        self.assertTrue(self.measure('ok', first_signal=signal)['ok'])
        self.assertTrue(signal.is_set())

    def test_missing_terminator_invalidates_measurement(self):
        self.assertFalse(self.measure('truncated')['ok'])

    def test_wrong_token_count_invalidates_measurement(self):
        self.assertFalse(self.measure('bad_usage')['ok'])


class FixtureTests(unittest.TestCase):
    def test_batch_encoding_token_count_and_fixture_reuse(self):
        class Tokenizer:
            name_or_path = 'pinned-test-tokenizer'

            def encode(self, text, **_):
                return list(range(len(text)))

            def decode(self, ids):
                return 'a'*len(ids)

            def apply_chat_template(self, messages, **_):
                count = len(messages[0]['content'])+40
                return {'input_ids': list(range(count)), 'attention_mask': [1]*count}

        tokenizer = Tokenizer()
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory)
            response = io.BytesIO(b'{"count":512}')
            with patch.object(benchmark.urllib.request, 'urlopen', return_value=response) as opening:
                first = benchmark.prepare_chat('http://unused', 'model', 512, 7, tokenizer, cache)
                self.assertEqual(first[1], 512)
                self.assertEqual(opening.call_count, 1)
            with patch.object(benchmark.urllib.request, 'urlopen', side_effect=AssertionError('cache miss')):
                second = benchmark.prepare_chat('http://unused', 'model', 512, 7, tokenizer, cache)
            self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
