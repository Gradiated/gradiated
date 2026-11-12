import importlib.util
import http.server
import json
import sys
import subprocess
import time
import types
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('kimi_probe', Path(__file__).with_name('probe.py'))
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def chunk(text, count=None, ids=None, reasoning=False):
    event = {'choices': [{'delta': {'reasoning_content' if reasoning else 'content': text}}]}
    if count is not None:
        event['usage'] = {'prompt_tokens': 2048, 'completion_tokens': count}
    if ids is not None:
        event['choices'][0]['internal_content'] = [{'token_ids': list(range(ids))}]
    return event


class AccountingTests(unittest.TestCase):
    def test_speculative_first_burst_does_not_inflate_speed(self):
        events = [(1, chunk('reasoning', 5, 5, True)), (1.1, chunk('answer', 10, 5)),
                  (1.11, {'choices': [], 'usage': {'prompt_tokens': 2048, 'completion_tokens': 10}}),
                  (1.12, '[DONE]')]
        row = probe.measure_events(events, 0, 1.12, minimum_output=10)
        self.assertTrue(row['ok'], row)
        self.assertAlmostEqual(row['nominal_decode_tps'], 90)
        self.assertAlmostEqual(row['burst_adjusted_decode_tps'], 50)
        self.assertFalse(row['slo_met'])
        self.assertEqual(row['stream_events'], 2)
        self.assertEqual(row['internal_token_occurrences'], 10)

    def test_overlapping_token_provenance_does_not_override_continuous_usage(self):
        events = [(1, chunk('reasoning fragment', 5, 5, True)),
                  (1.01, chunk('replayed fragment', 5, 5)),
                  (1.1, chunk('answer', 10, 6)),
                  (1.11, {'choices': [], 'usage': {'prompt_tokens': 32768, 'completion_tokens': 10}}),
                  (1.12, '[DONE]')]
        row = probe.measure_events(events, 0, 1.12, minimum_output=10)
        self.assertTrue(row['ok'], row)
        self.assertEqual(row['completion_tokens'], 10)
        self.assertEqual(row['internal_token_occurrences'], 16)
        self.assertTrue(row['internal_occurrences_exceed_usage'])
        self.assertAlmostEqual(row['burst_adjusted_decode_tps'], 50)
        self.assertFalse(row['slo_met'])

    def test_visible_token_ids_without_first_cumulative_usage_cannot_qualify_decode(self):
        events = [(1, chunk('a', ids=2)), (1.01, chunk('b', ids=9)),
                  (1.02, {'choices': [], 'usage': {'prompt_tokens': 2048, 'completion_tokens': 10}}),
                  (1.03, '[DONE]')]
        row = probe.measure_events(events, 0, 1.03, minimum_output=10)
        self.assertTrue(row['ok'], row)
        self.assertIsNone(row['first_event_tokens'])
        self.assertIsNone(row['burst_adjusted_decode_tps'])
        self.assertEqual(row['gate_basis'], 'end-to-end-lower-bound')
        self.assertAlmostEqual(row['gate_tps'], 10/1.03)
        self.assertFalse(row['slo_met'])

    def test_diagnostic_events_exclude_text_and_token_ids_and_are_bounded(self):
        events = [(1, chunk('synthetic private text', 5, 5, True)), (2, '[DONE]')]
        trace = probe.diagnostic_events(events, 0, limit=1)
        self.assertEqual(trace['events'][0]['completion_tokens'], 5)
        self.assertEqual(trace['events'][0]['internal_token_occurrences'], 5)
        self.assertTrue(trace['truncated'])
        self.assertNotIn('synthetic private text', json.dumps(trace))
        self.assertNotIn('token_ids', json.dumps(trace))

    def test_usage_only_stream_uses_conservative_end_to_end_gate(self):
        events = [(1, chunk('a')), (1.05, chunk('b')),
                  (1.06, {'choices': [], 'usage': {'prompt_tokens': 8192, 'completion_tokens': 10}}),
                  (1.07, '[DONE]')]
        row = probe.measure_events(events, 0, 1.07, minimum_output=10)
        self.assertTrue(row['ok'])
        self.assertEqual(row['gate_basis'], 'end-to-end-lower-bound')
        self.assertAlmostEqual(row['gate_tps'], 10/1.07)
        self.assertFalse(row['slo_met'])

    def test_missing_final_usage_is_failure_not_requested_token_fallback(self):
        row = probe.measure_events([(1, chunk('a')), (2, chunk('b')), (3, '[DONE]')], 0, 3, 2)
        self.assertFalse(row['ok'])
        self.assertIn('usage', row['error'])

    def test_truncated_stream_is_failure(self):
        row = probe.measure_events([(1, chunk('a', 1)), (2, chunk('b', 5))], 0, 3, 2)
        self.assertFalse(row['ok'])

    def test_decreasing_usage_is_failure(self):
        row = probe.measure_events([(1, chunk('a', 5)), (2, chunk('b', 4)), (3, '[DONE]')], 0, 3, 2)
        self.assertFalse(row['ok'])
        self.assertIn('decreased', row['error'])

    def test_short_output_does_not_qualify(self):
        row = probe.measure_events([(1, chunk('a', 1)), (1.01, chunk('b', 2)), (1.02, '[DONE]')], 0, 1.02)
        self.assertFalse(row['ok'])
        self.assertIn('too short', row['error'])

    def test_median_stream_must_meet_floor(self):
        def rows(speeds):
            return [{'ok': True, 'slo_met': speed >= 80, 'gate_tps': speed, 'ttft_s': .1,
                     'completion_tokens': 512, 'started_at_monotonic': 0, 'finished_at_monotonic': 5}
                    for speed in speeds]
        summary = probe.summarize(rows([100, 90, 60]), 3, 0, 80)
        self.assertTrue(summary['slo_met'])
        self.assertEqual(summary['gate_tps_min'], 60)
        self.assertEqual(summary['aggregate_output_tps'], 3*512/5)
        self.assertFalse(probe.summarize(rows([100, 79.9, 60]), 3, 0, 80)['slo_met'])

    def test_failed_request_fails_round(self):
        good = {'ok': True, 'slo_met': True, 'gate_tps': 120, 'ttft_s': .1, 'completion_tokens': 512,
                'started_at_monotonic': 0, 'finished_at_monotonic': 5}
        failed = {'ok': False, 'slo_met': False, 'started_at_monotonic': 0, 'finished_at_monotonic': 5}
        self.assertFalse(probe.summarize([good, good, failed], 3, 0, 80)['slo_met'])

    def test_fixture_order_covers_each_length_at_concurrency_one(self):
        fixtures = [{'target_tokens': target, 'id': f'{target}-{i}'}
                    for target in (2048, 8192, 32768) for i in range(4)]
        ordered = probe.interleave_fixtures(fixtures)
        self.assertEqual([f['target_tokens'] for f in ordered[:3]], [2048, 8192, 32768])


class RequestTests(unittest.TestCase):
    def args(self):
        return types.SimpleNamespace(model='test', output_tokens=512, reasoning_effort='max', native_metrics=True,
                                     temperature=1.0, top_p=.95,
                                     ignore_eos=False, base_url='http://127.0.0.1:30000', api_key='hidden',
                                     request_timeout=1, idle_timeout=.1, min_output_tokens=512, floor_tps=80)

    def test_expired_campaign_does_not_open_connection(self):
        with patch.object(probe, 'post_json') as post:
            row = probe.request_once(self.args(), {'id': 'test', 'target_tokens': 2048,
                                     'messages': [{'role': 'user', 'content': 'test'}]}, time.monotonic()-1)
        post.assert_not_called()
        self.assertFalse(row['ok'])
        self.assertIn('deadline', row['error'])

    def test_http_stream_counts_reasoning_and_content_bursts(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                self.server.payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.send_response(200)
                self.send_header('Content-Type', 'text/event-stream')
                self.end_headers()
                for event in [chunk('thinking', 256, 256, True), chunk('answer', 512, 256),
                              {'choices': [], 'usage': {'prompt_tokens': 2057, 'completion_tokens': 512}}]:
                    self.wfile.write(b'data: ' + json.dumps(event).encode() + b'\n\n')
                    self.wfile.flush()
                    time.sleep(.01)
                self.wfile.write(b'data: [DONE]\n\n')

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            args = self.args()
            args.base_url = f'http://127.0.0.1:{server.server_port}'
            row = probe.request_once(args, {'id': 'fixture', 'target_tokens': 2048,
                                     'messages': [{'role': 'user', 'content': 'synthetic'}]}, time.monotonic()+2)
            self.assertTrue(row['ok'], row)
            self.assertEqual(row['prompt_tokens'], 2057)
            self.assertEqual(row['first_event_tokens'], 256)
            self.assertEqual(row['internal_token_occurrences'], 512)
            self.assertEqual(row['stream_events'], 2)
            self.assertTrue(row['slo_met'])
            self.assertTrue(server.payload['stream_options']['include_internal_content'])
            self.assertEqual(server.payload['reasoning_effort'], 'max')
            self.assertEqual(server.payload['temperature'], 1.0)
            self.assertEqual(server.payload['top_p'], .95)
            self.assertNotIn('seed', server.payload)
            self.assertNotIn('hidden', json.dumps(row))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_native_generate_uses_authoritative_engine_counts_and_exact_input_ids(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                self.server.seen = (self.path, payload)
                self.send_response(200)
                self.end_headers()
                for count in (1, 512):
                    event = {'text': 'same cumulative text', 'output_ids': [7] * 1024,
                             'meta_info': {'prompt_tokens': len(payload['input_ids']) + self.server.prompt_delta,
                                           'completion_tokens': count, 'cached_tokens': 2}}
                    self.wfile.write(b'data: ' + json.dumps(event).encode() + b'\n\n')
                    self.wfile.flush()
                    time.sleep(.01)
                self.wfile.write(b'data: [DONE]\n\n')

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            for prompt_delta in (0, 1):
                with self.subTest(prompt_delta=prompt_delta):
                    server.prompt_delta = prompt_delta
                    args = self.args()
                    args.protocol = 'generate'
                    args.base_url = f'http://127.0.0.1:{server.server_port}'
                    fixture = {'id': 'fixture', 'target_tokens': 4, 'messages': [{'role': 'user', 'content': 'text'}],
                               'native_input_ids': [163584, 11, 22, 163600]}
                    row = probe.request_once(args, fixture, time.monotonic()+2)
                    self.assertEqual(row['ok'], prompt_delta == 0, row)
                    if prompt_delta:
                        self.assertIn('exact rendered input IDs', row['error'])
                        self.assertFalse(row['slo_met'])
                        continue
                    self.assertEqual(row['counter_source'], 'native-meta-info')
                    self.assertEqual(row['first_event_tokens'], 1)
                    self.assertEqual(row['completion_tokens'], 512)
                    self.assertEqual(row['usage']['prompt_tokens_details']['cached_tokens'], 2)
                    self.assertEqual(row['gate_basis'], 'counted-first-burst')
                    self.assertIsNone(row['internal_token_occurrences'])
                    self.assertEqual(server.seen[0], '/generate')
                    payload = server.seen[1]
                    self.assertEqual(payload['input_ids'], fixture['native_input_ids'])
                    self.assertEqual(payload['sampling_params'], {'max_new_tokens': 512,
                                     'temperature': 1.0, 'top_p': .95, 'skip_special_tokens': False})
                    self.assertNotIn('messages', payload)
                    self.assertNotIn('reasoning_effort', payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

    def test_native_fixture_uses_kimi_thinking_effort_not_openai_argument_name(self):
        tokenizer = types.SimpleNamespace(apply_chat_template=Mock(return_value=[1, 2, 3]))
        args = types.SimpleNamespace(reasoning_effort='high')
        fixture = {'id': 'fixture', 'target_tokens': 4, 'messages': [{'role': 'user', 'content': 'text'}]}
        result = probe.prepare_native_fixtures(args, [fixture], tokenizer=tokenizer)
        tokenizer.apply_chat_template.assert_called_once_with(fixture['messages'], tokenize=True,
                        add_generation_prompt=True, thinking=True, thinking_effort='high')
        self.assertEqual(result[0]['native_input_ids'], [1, 2, 3])
        for messages in ([{'role': 'system', 'content': 'system'}],
                         [{'role': 'user', 'content': '<|kimi_image_placeholder|>'}],
                         [{'role': 'user', 'content': [{'type': 'image_url'}]}]):
            with self.subTest(messages=messages), self.assertRaisesRegex(ValueError, 'synthetic text-only'):
                probe.prepare_native_fixtures(args, [{**fixture, 'messages': messages}], tokenizer=tokenizer)

    def test_native_missing_engine_metadata_cannot_be_inferred_from_output_ids(self):
        with self.assertRaisesRegex(ValueError, 'meta_info'):
            probe.normalize_native_event({'text': 'output', 'output_ids': [1, 2, 3]})

    def test_greedy_control_forwards_explicit_sampling_and_reasoning(self):
        args = self.args()
        args.temperature, args.top_p, args.reasoning_effort = 0, 1, 'low'
        with patch.object(probe, 'post_json', side_effect=TimeoutError('synthetic stop')) as post:
            probe.request_once(args, {'id': 'fixture', 'target_tokens': 2048,
                               'messages': [{'role': 'user', 'content': 'synthetic'}]}, time.monotonic()+1)
        payload = post.call_args.args[1]
        self.assertEqual((payload['temperature'], payload['top_p'], payload['reasoning_effort']), (0, 1, 'low'))
        self.assertNotIn('seed', payload)

    def test_seed_and_penalties_reach_both_protocols(self):
        args = self.args()
        args.sampling_seed, args.frequency_penalty, args.presence_penalty = 42, .2, .2
        fixture = {'id': 'fixture', 'target_tokens': 2048, 'native_input_ids': [1, 2],
                   'messages': [{'role': 'user', 'content': 'synthetic'}]}
        for protocol, seed_field in (('chat', 'seed'), ('generate', 'sampling_seed')):
            with self.subTest(protocol=protocol):
                args.protocol = protocol
                with patch.object(probe, 'post_json', side_effect=TimeoutError('synthetic stop')) as post:
                    probe.request_once(args, fixture, time.monotonic()+1)
                payload = post.call_args.args[1]
                sampling = payload['sampling_params'] if protocol == 'generate' else payload
                self.assertEqual((sampling[seed_field], sampling['frequency_penalty'], sampling['presence_penalty']),
                                 (42, .2, .2))

    def test_invalid_penalty_is_rejected_before_fixture_loading(self):
        for value in ('nan', 'inf', '2.1', '-2.1'):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, str(Path(probe.__file__)),
                    '--base-url', 'http://127.0.0.1:1', '--label', 'invalid', f'--presence-penalty={value}'],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn('penalties must be finite', result.stderr)

    def test_invalid_sampling_is_rejected_before_fixture_loading(self):
        for flag, value in (('--temperature', 'nan'), ('--temperature', 'inf'),
                            ('--temperature', '-.1'), ('--temperature', '2.1'),
                            ('--top-p', 'nan'), ('--top-p', '-.1'), ('--top-p', '1.1')):
            with self.subTest(flag=flag, value=value):
                result = subprocess.run([sys.executable, str(Path(probe.__file__)),
                    '--base-url', 'http://127.0.0.1:1', '--label', 'invalid', flag, value],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn('temperature must be finite', result.stderr)

    def test_invalid_throughput_floor_is_rejected_before_fixture_loading(self):
        for value in ('nan', 'inf', '-inf', '0', '-1'):
            with self.subTest(value=value):
                result = subprocess.run([sys.executable, str(Path(probe.__file__)),
                    '--base-url', 'http://127.0.0.1:1', '--label', 'invalid', f'--floor-tps={value}'],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn('floor-tps must be finite and positive', result.stderr)

    def test_invalid_sample_counts_and_timeouts_are_rejected_before_fixture_loading(self):
        cases = [(flag, value, 'must be positive') for flag in ('--min-output-tokens', '--fixtures-per-class')
                 for value in ('0', '-1')]
        cases += [('--warmups', '-1', 'must be nonnegative')]
        cases += [(flag, value, 'timeouts must be finite and positive')
                  for flag in ('--request-timeout', '--idle-timeout', '--max-seconds')
                  for value in ('0', '-1', 'nan', 'inf', '-inf')]
        for flag, value, message in cases:
            with self.subTest(flag=flag, value=value):
                result = subprocess.run([sys.executable, str(Path(probe.__file__)),
                    '--base-url', 'http://127.0.0.1:1', '--label', 'invalid', f'{flag}={value}'],
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 2)
                self.assertIn(message, result.stderr)

    def test_http_trickling_comments_cannot_extend_absolute_deadline(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(200)
                self.end_headers()
                try:
                    for _ in range(100):
                        self.wfile.write(b': heartbeat\n\n')
                        self.wfile.flush()
                        time.sleep(.005)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            args = self.args()
            args.base_url = f'http://127.0.0.1:{server.server_port}'
            started = time.monotonic()
            row = probe.request_once(args, {'id': 'fixture', 'target_tokens': 2048,
                                     'messages': [{'role': 'user', 'content': 'synthetic'}]}, started+.04)
            self.assertFalse(row['ok'])
            self.assertLess(time.monotonic()-started, .3)
            self.assertTrue('deadline' in row['error'] or 'timed out' in row['error'], row)
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
