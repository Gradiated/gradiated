"""Offline session/protocol tests: synthetic frames, no physical device access."""
import ctypes
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import board_bos


class FakeSession:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.context_count = 0
        self.tokens = []
        self.clears = 0
        self.closed = False

    def step(self, token):
        self.tokens.append(token)
        self.context_count += 1
        return {'logits': next(self.rows), 'context_count': self.context_count,
                'api_result': 0, 'counters': [0, 29281, 320, self.context_count, 0]}

    def clear(self):
        self.clears += 1
        self.context_count = 0
        return {'context_count': 0, 'counters': [0, 29281, 0, 0, 0]}

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.closed = True


class NativeCalls(unittest.TestCase):
    def session(self):
        session = board_bos.NativeSession.__new__(board_bos.NativeSession)
        session.context_count = 0
        session.failed = False
        session.storage = (ctypes.c_uint64 * 64)()
        session.storage_bytes = 512

        def step(storage, size, token, deadline, logits, counters):
            self.assertEqual(deadline, board_bos.CALL_BUDGET_NS)
            for i in range(320):
                logits[i] = i - 160
            counters[:] = [0, 29281, 320, session.context_count + 1, 0]
            return 0

        def clear(storage, size, deadline, counters):
            counters[:] = [0, 29281, 0, 0, 0]
            return 0

        session.lib = SimpleNamespace(board_session_step=Mock(side_effect=step),
                                      board_session_clear=Mock(side_effect=clear))
        return session

    def test_ordered_frames_context_clear_and_bos_requirement(self):
        session = self.session()
        frame = session.step(256)
        self.assertEqual(frame['logits'], list(range(-160, 160)))
        session.step(76)
        self.assertEqual(session.context_count, 2)
        session.clear()
        self.assertEqual(session.context_count, 0)
        with self.assertRaisesRegex(ValueError, 'BOS'):
            session.step(76)
        session.step(256)
        self.assertEqual(session.lib.board_session_step.call_count, 3)
        session.lib.board_session_clear.assert_called_once()

    def test_no_calls_for_invalid_tokens_or_full_context(self):
        session = self.session()
        for token in (True, -1, 320, '256'):
            with self.assertRaises(ValueError):
                session.step(token)
        session.context_count = 256
        with self.assertRaisesRegex(ValueError, 'full'):
            session.step(76)
        session.lib.board_session_step.assert_not_called()

    def test_failure_or_saturation_poison_session_without_retry(self):
        for rc, counters in ((-6, [0, 0, 0, 0, 0]), (0, [0, 29281, 320, 1, 1]),
                             (0, [0, 29281, 319, 1, 0]), (0, [0, 29281, 320, 2, 0])):
            with self.subTest(rc=rc, counters=counters):
                session = self.session()
                def fail(storage, size, token, deadline, values, result):
                    result[:] = counters
                    return rc
                session.lib.board_session_step.side_effect = fail
                with self.assertRaises(RuntimeError):
                    session.step(256)
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    session.step(256)
                with self.assertRaisesRegex(RuntimeError, 'failed'):
                    session.clear()
                session.lib.board_session_step.assert_called_once()
                session.lib.board_session_clear.assert_not_called()


class ReferenceValidation(unittest.TestCase):
    def fixture(self, root):
        cases = [{'name': name, 'tokens': [256] + [76] * (count - 1),
                  'logits': [[0] * 320 for _ in range(count)]}
                 for name, count in [('BOS', 1), ('J01-first16', 16),
                                     ('authored128', 128), ('repeated-J01-256', 256)]]
        (root / 'token-logits.json').write_text(json.dumps({'schema': 1,
            'original_goldens_sha256': board_bos.GOLDENS_SHA, 'cases': cases}))
        return cases

    def test_first16_compares_every_score_and_retains_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            session = FakeSession([[0] * 320 for _ in range(16)])
            with patch.object(board_bos, 'NativeSession', return_value=session):
                result = board_bos.run_validation(root, 'J01-first16')
            self.assertTrue(result['accepted'])
            self.assertEqual(result['cases'][0]['logit_values_checked'], 5120)
            self.assertEqual(result['cases'][0]['logits_sha256'],
                             hashlib.sha256(bytes(16 * 320 * 4)).hexdigest())
            self.assertEqual(session.tokens, [256] + [76] * 15)
            self.assertTrue(session.closed)

    def test_all_cases_clear_context_between_cases_and_reach_256(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            session = FakeSession([[0] * 320 for _ in range(401)])
            with patch.object(board_bos, 'NativeSession', return_value=session):
                result = board_bos.run_validation(root, 'all')
            self.assertEqual([c['context_count'] for c in result['cases']], [1, 16, 128, 256])
            self.assertEqual(session.clears, 3)
            self.assertEqual(result['explicit_context_clears'], 3)

    def test_first_mismatch_stops_without_retry(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.fixture(root)
            bad = [0] * 320
            bad[319] = 1
            session = FakeSession([[0] * 320, bad])
            with patch.object(board_bos, 'NativeSession', return_value=session):
                with self.assertRaisesRegex(RuntimeError, '"position": 1'):
                    board_bos.run_validation(root, 'J01-first16')
            self.assertEqual(len(session.tokens), 2)
            self.assertTrue(session.closed)

    def test_malformed_reference_rejects_before_native_session(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = self.fixture(root)
            cases[1]['logits'][0] = [0] * 319
            (root / 'token-logits.json').write_text(json.dumps({'schema': 1,
                'original_goldens_sha256': board_bos.GOLDENS_SHA, 'cases': cases}))
            with patch.object(board_bos, 'NativeSession') as native:
                with self.assertRaises(ValueError):
                    board_bos.run_validation(root, 'J01-first16')
                native.assert_not_called()


class Streaming(unittest.TestCase):
    def test_step_clear_close_frames_have_ids_checksums_and_raw_scores(self):
        session = FakeSession([list(range(-160, 160)), [0] * 320])
        incoming = io.StringIO(''.join(json.dumps(r) + '\n' for r in [
            {'id': 0, 'op': 'step', 'token': 256}, {'id': 1, 'op': 'clear'},
            {'id': 2, 'op': 'step', 'token': 256}, {'id': 3, 'op': 'close'}]))
        output = io.StringIO()
        with patch.object(board_bos, 'NativeSession', return_value=session):
            self.assertEqual(board_bos.run_stream('.', incoming, output), 0)
        rows = [json.loads(s) for s in output.getvalue().splitlines()]
        self.assertEqual(rows[0]['protocol'], 'fpga-logits-v1')
        self.assertEqual([r['id'] for r in rows[1:]], [0, 1, 2, 3])
        self.assertEqual(rows[1]['logits_sha256'],
                         hashlib.sha256(struct.pack('<320i', *range(-160, 160))).hexdigest())
        self.assertEqual(rows[2]['context_count'], 0)
        self.assertTrue(rows[-1]['closed'])
        self.assertEqual(session.tokens, [256, 256])

    def test_duplicate_id_eof_oversize_and_unknown_operations_abort(self):
        for request in ('', 'x' * 4097, '{"id":1,"op":"step","token":256}\n',
                        '{"id":0,"op":"retry"}\n', '{"id":true,"op":"close"}\n'):
            with self.subTest(request=request[:40]):
                session = FakeSession([])
                with patch.object(board_bos, 'NativeSession', return_value=session):
                    with self.assertRaises(ValueError):
                        board_bos.run_stream('.', io.StringIO(request), io.StringIO())
                self.assertEqual(session.tokens, [])
                self.assertTrue(session.closed)


class Sampling(unittest.TestCase):
    def test_inverse_cdf_boundaries_and_first_index_greedy_tie(self):
        values = [-(1 << 31)] * 320
        values[5] = values[9] = 0
        for draw, expected in ((0, 5), (.499, 5), (.5, 9), (.999, 9)):
            self.assertEqual(board_bos.sample_logits(values, 0, draw), expected)
        self.assertEqual(board_bos.sample_logits(values, 32, None), 5)
        for draw in (-.1, 1, float('nan'), True):
            with self.assertRaises(ValueError):
                board_bos.sample_logits(values, 0, draw)

    def test_generation_retains_all_frames_draws_and_eos_without_feeding_eos(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'sampling-draws.json').write_text(json.dumps({'schema': 1, 'draws': {'47': [.5] * 32}}))
            rows = []
            for token in (65, 319, 257):
                scores = [-(1 << 31)] * 320
                scores[token] = 0
                rows.append(scores)
            session = FakeSession(rows)
            with patch.object(board_bos, 'NativeSession', return_value=session):
                result = board_bos.run_generation(root, 47)
            self.assertTrue(result['hardware_accepted'])
            self.assertFalse(result['sampling_verified'])
            self.assertTrue(result['requires_mac_numpy_audit'])
            self.assertEqual(result['tokens'], [65, 319])  # No mask or byte filtering.
            self.assertIsNone(result['text'])
            self.assertEqual(session.tokens, [256, 65, 319])
            self.assertEqual([f['chosen_token'] for f in result['frames']], [65, 319, 257])
            self.assertEqual(result['uniform_draws'], [.5] * 32)

    def test_bad_or_missing_draws_reject_before_native_session(self):
        for draws in ([], [.5] * 31, [.5] * 31 + [1], [.5] * 31 + [True]):
            with self.subTest(draws=len(draws)), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                (root / 'sampling-draws.json').write_text(json.dumps({'schema': 1, 'draws': {'47': draws}}))
                with patch.object(board_bos, 'NativeSession') as native:
                    with self.assertRaises(ValueError):
                        board_bos.run_generation(root, 47)
                    native.assert_not_called()


class TextCompletion(unittest.TestCase):
    @staticmethod
    def scores(token):
        values = [-100] * 320
        values[token] = 10
        return values

    def test_real_prefix_bytes_last_prefix_scores_and_generated_feedback(self):
        for text in ('Our chocolate-chip RAM', 'fu2p2q', 'Lithography put', '  quote " --flag  '):
            with self.subTest(text=text):
                prefix = [256, *text.encode('utf-8')]
                session = FakeSession([self.scores(319) for _ in prefix[:-1]] +
                                      [self.scores(65), self.scores(257)])
                with patch.object(board_bos, 'NativeSession', return_value=session):
                    result = board_bos.run_completion('.', text, 2)
                self.assertEqual(session.tokens, prefix + [65])
                self.assertEqual(result['prefix_tokens'], prefix)
                self.assertEqual(result['input_tokens'], session.tokens)
                self.assertEqual(result['generated_tokens'], [65])
                self.assertEqual(result['continuation_text'], 'A')
                self.assertEqual([f['phase'] for f in result['frames']],
                                 ['prefix'] * len(prefix) + ['generation'])
                self.assertEqual(result['decisions'][0], {'frame_index': len(prefix) - 1, 'token': 65})
                self.assertEqual(result['decisions'][-1]['token'], 257)
                self.assertTrue(result['eos'])
                self.assertTrue(session.closed)
                for i, frame in enumerate(result['frames']):
                    self.assertEqual(frame['frame_index'], i)
                    self.assertEqual(frame['input_token'], session.tokens[i])
                    self.assertEqual(frame['counters'], [0, 29281, 320, i + 1, 0])
                    self.assertEqual(frame['logits_sha256'], hashlib.sha256(
                        struct.pack('<320i', *frame['logits'])).hexdigest())

    def test_utf8_prefix_and_multibyte_continuation_are_not_character_ids(self):
        text = 'é🙂'
        prefix = [256, *text.encode('utf-8')]
        session = FakeSession([self.scores(319) for _ in prefix[:-1]] +
                              [self.scores(0xc3), self.scores(0xa9), self.scores(257)])
        with patch.object(board_bos, 'NativeSession', return_value=session):
            result = board_bos.run_completion('.', text, 3)
        self.assertEqual(session.tokens, prefix + [0xc3, 0xa9])
        self.assertEqual(result['prefix_utf8_hex'], text.encode('utf-8').hex())
        self.assertEqual(result['continuation_text'], 'é')
        self.assertEqual(result['continuation_bytes_hex'], 'c3a9')

    def test_empty_prefix_is_bos_only_and_first_eos_is_not_fed(self):
        session = FakeSession([self.scores(257)])
        with patch.object(board_bos, 'NativeSession', return_value=session):
            result = board_bos.run_completion('.', '', 128)
        self.assertEqual(session.tokens, [256])
        self.assertEqual(result['generated_tokens'], [])
        self.assertEqual(result['continuation_text'], '')
        self.assertEqual(result['stop_reason'], 'eos')

    def test_maximum_output_length_feeds_final_selected_byte_and_stops(self):
        values = [0] * 320  # First-index argmax must select token0, with no mask.
        session = FakeSession([values, values])
        with patch.object(board_bos, 'NativeSession', return_value=session):
            result = board_bos.run_completion('.', '', 1)
        self.assertEqual(session.tokens, [256, 0])
        self.assertEqual(result['generated_tokens'], [0])
        self.assertEqual(result['continuation_text'], '\0')
        self.assertEqual(result['stop_reason'], 'max_new_tokens')

    def test_context_capacity_never_scores_position257(self):
        for count, emitted in ((254, [65]), (255, [])):
            with self.subTest(prefix_bytes=count):
                session = FakeSession([self.scores(65) for _ in range(256)])
                with patch.object(board_bos, 'NativeSession', return_value=session):
                    result = board_bos.run_completion('.', 'a' * count, 128)
                self.assertEqual(len(session.tokens), 256)
                self.assertEqual(result['context_count'], 256)
                self.assertEqual(result['generated_tokens'], emitted)
                self.assertEqual(result['stop_reason'], 'context_limit')

    def test_oversized_utf8_and_invalid_output_bounds_reject_before_mmio(self):
        for text, limit in [('a' * 256, 1), ('é' * 128, 1), ('\ud800', 1),
                            ('', 0), ('', -1), ('', 256), ('', True)]:
            with self.subTest(prefix_length=len(text), limit=limit), \
                    patch.object(board_bos, 'NativeSession') as native:
                with self.assertRaises(ValueError):
                    board_bos.run_completion('.', text, limit)
                native.assert_not_called()

    def test_nonbyte_output_preserves_id_and_bytes_without_substitution(self):
        session = FakeSession([self.scores(65), self.scores(319)])
        with patch.object(board_bos, 'NativeSession', return_value=session):
            result = board_bos.run_completion('.', '', 4)
        self.assertEqual(session.tokens, [256, 65])
        self.assertEqual(result['generated_tokens'], [65, 319])
        self.assertEqual(result['stop_reason'], 'non_byte_token')
        self.assertFalse(result['valid_utf8_bytes'])
        self.assertIsNone(result['continuation_text'])
        self.assertIsNone(result['continuation_bytes_hex'])
        self.assertEqual(result['byte_prefix_hex'], '41')
        self.assertEqual(result['decisions'][-1]['token'], 319)

    def test_invalid_utf8_bytes_are_reported_without_repair(self):
        session = FakeSession([self.scores(255), self.scores(257)])
        with patch.object(board_bos, 'NativeSession', return_value=session):
            result = board_bos.run_completion('.', '', 3)
        self.assertEqual(result['generated_tokens'], [255])
        self.assertEqual(result['continuation_bytes_hex'], 'ff')
        self.assertIsNone(result['continuation_text'])
        self.assertFalse(result['valid_utf8_bytes'])

    def test_native_error_stops_without_fallback_or_replaying_prefix(self):
        session = FakeSession([self.scores(65)])
        session.step = Mock(side_effect=RuntimeError('native failure'))
        with patch.object(board_bos, 'NativeSession', return_value=session):
            with self.assertRaisesRegex(RuntimeError, 'native failure'):
                board_bos.run_completion('.', 'fu2p2q', 1)
        session.step.assert_called_once_with(256)
        self.assertTrue(session.closed)


class ConditionedInput(unittest.TestCase):
    """Synthetic protocol checks; no conditioned model/package is selected here."""

    def test_exact_hex_prefixes_include_every_byte_and_no_answer_marker(self):
        for text, expected in (
                ('', [256]),
                ('fu2p2q', [256, 278, 294, 279, 293, 275, 290, 279, 288, 275, 290, 279, 289]),
                ('hello', [256, 278, 296, 278, 293, 278, 300, 278, 300, 278, 303]),
                ('é', [256, 284, 291, 282, 297]),
                ('\0 \n', [256, 272, 288, 274, 288, 272, 298])):
            with self.subTest(text=text):
                raw, tokens = board_bos.completion_prefix(text, 255, encoding='hex')
                self.assertEqual(raw, text.encode('utf-8'))
                self.assertEqual(tokens, expected)

    def test_limit_is_48_utf8_bytes_and_rejects_before_native_session(self):
        raw, tokens = board_bos.completion_prefix('é' * 24, 255, encoding='hex')
        self.assertEqual(len(raw), 48)
        self.assertEqual(tokens, [256] + [284, 291, 282, 297] * 24)
        for text, limit, encoding in (('x' * 49, 255, 'hex'), ('é' * 25, 255, 'hex'),
                                      ('\ud800', 255, 'hex'), ('', 0, 'hex'),
                                      ('', 256, 'hex'), ('', 255, 'unknown')):
            with self.subTest(text=repr(text), limit=limit, encoding=encoding), \
                    patch.object(board_bos, 'NativeSession') as native:
                with self.assertRaises(ValueError):
                    board_bos.run_completion('.', text, limit, encoding=encoding)
                native.assert_not_called()

    def test_final_nibble_predicts_first_output_then_raw_bytes_feed_back(self):
        prefix = [256, 284, 291, 282, 297]
        for _ in range(2):  # Each identical request opens a fresh session.
            session = FakeSession([TextCompletion.scores(319) for _ in prefix[:-1]] +
                                  [TextCompletion.scores(0xc3), TextCompletion.scores(0xa9),
                                   TextCompletion.scores(257)])
            with patch.object(board_bos, 'NativeSession', return_value=session) as native:
                result = board_bos.run_completion('.', 'é', 255, encoding='hex')
            native.assert_called_once_with('.')
            self.assertEqual(session.tokens, prefix + [0xc3, 0xa9])
            self.assertEqual(result['prefix_tokens'], prefix)
            self.assertEqual(result['generated_tokens'], [0xc3, 0xa9])
            self.assertEqual(result['continuation_text'], 'é')
            self.assertEqual(result['input_encoding'], 'hex')
            self.assertFalse(result['answer_marker'])
            self.assertEqual(result['decisions'][0], {'frame_index': 4, 'token': 0xc3})
            self.assertTrue(result['eos'])
            self.assertTrue(session.closed)

    def test_context_budget_matches_mac_without_scoring_final_output_byte(self):
        for text, prefix_count, outputs in (('', 1, 255), ('x' * 48, 97, 159)):
            with self.subTest(prefix_count=prefix_count):
                session = FakeSession([TextCompletion.scores(65)] * 255)
                with patch.object(board_bos, 'NativeSession', return_value=session):
                    result = board_bos.run_completion('.', text, 255, encoding='hex')
                self.assertEqual(len(result['prefix_tokens']), prefix_count)
                self.assertEqual(result['generated_tokens'], [65] * outputs)
                self.assertEqual(len(result['decisions']), outputs)
                self.assertEqual(len(session.tokens), 255)
                self.assertEqual(result['context_count'], 255)
                self.assertEqual(result['stop_reason'], 'context_limit')
                self.assertEqual(len(result['frames']), 255)

    def test_explicit_cap_does_not_score_last_byte_and_ties_use_first_index(self):
        session = FakeSession([[0] * 320])
        with patch.object(board_bos, 'NativeSession', return_value=session):
            result = board_bos.run_completion('.', '', 1, encoding='hex')
        self.assertEqual(session.tokens, [256])
        self.assertEqual(result['generated_tokens'], [0])
        self.assertEqual(result['stop_reason'], 'max_new_tokens')

    def test_eos_reserved_tokens_and_invalid_utf8_are_never_masked_or_repaired(self):
        for chosen, generated, stop, valid in ((257, [], 'eos', True),
                (272, [272], 'non_byte_token', False), (319, [319], 'non_byte_token', False),
                (255, [255], 'max_new_tokens', False)):
            with self.subTest(chosen=chosen):
                session = FakeSession([TextCompletion.scores(chosen)])
                with patch.object(board_bos, 'NativeSession', return_value=session):
                    result = board_bos.run_completion('.', '', 1, encoding='hex')
                self.assertEqual(session.tokens, [256])
                self.assertEqual(result['generated_tokens'], generated)
                self.assertEqual(result['stop_reason'], stop)
                self.assertEqual(result['valid_utf8_bytes'], valid)
                self.assertEqual(result['decisions'], [{'frame_index': 0, 'token': chosen}])

    def test_cli_cannot_select_hex_without_a_verified_conditioned_package(self):
        with patch.object(board_bos.sys, 'argv', ['board_bos.py', '--complete=hello', '--encoding=hex']), \
                patch.object(board_bos, 'NativeSession') as native, \
                patch('sys.stderr', new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as raised:
                board_bos.main()
        self.assertEqual(raised.exception.code, 2)
        native.assert_not_called()


class TextInterface(unittest.TestCase):
    @staticmethod
    def reply(text='suffix'):
        return {'hardware_accepted': True, 'continuation_text': text,
                'generated_tokens': list(text.encode()), 'valid_utf8_bytes': True,
                'eos': True, 'stop_reason': 'eos', 'byte_prefix_hex': text.encode().hex()}

    def test_parent_pipes_exact_text_and_enforces_one_180_second_child(self):
        text = '--flags \0é\n spaces '
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(self.reply()), stderr='')
        with patch.object(board_bos.subprocess, 'run', return_value=completed) as run:
            result = board_bos.completion_request('.', text, 8)
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs['timeout'], 180)
        self.assertEqual(json.loads(run.call_args.kwargs['input']), {'text': text})
        self.assertNotIn(text, run.call_args.args[0])
        self.assertEqual(result, self.reply())

    def test_interactive_waits_in_parent_and_starts_fresh_child_for_each_line(self):
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(self.reply()), stderr='')
        class Lines:
            def __init__(self): self.index = 0
            def readline(self, *args):
                self_outer.assertEqual(run.call_count, self.index)
                result = ['Our chocolate-chip RAM\n', 'fu2p2q\n', ''][self.index]
                self.index += 1
                return result
        self_outer = self
        output = io.StringIO()
        with patch.object(board_bos.subprocess, 'run', return_value=completed) as run, \
                patch.object(board_bos, 'NativeSession') as native:
            self.assertEqual(board_bos.run_interactive('.', 8, Lines(), output), 0)
        self.assertEqual(run.call_count, 2)
        self.assertEqual([json.loads(c.kwargs['input'])['text'] for c in run.call_args_list],
                         ['Our chocolate-chip RAM', 'fu2p2q'])
        self.assertTrue(all(c.kwargs['timeout'] == 180 for c in run.call_args_list))
        native.assert_not_called()
        self.assertIn('suffix', output.getvalue())

    def test_interactive_rejects_long_line_without_truncation_then_accepts_empty(self):
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(self.reply()), stderr='')
        with patch.object(board_bos.subprocess, 'run', return_value=completed) as run:
            result = board_bos.run_interactive('.', 1, io.StringIO('a' * 500 + '\n\n'), io.StringIO())
        self.assertEqual(result, 0)
        run.assert_called_once()
        self.assertEqual(json.loads(run.call_args.kwargs['input']), {'text': ''})

    def test_interactive_timeout_stops_without_retry_or_second_request(self):
        with patch.object(board_bos.subprocess, 'run', side_effect=subprocess.TimeoutExpired('child', 180)) as run:
            result = board_bos.run_interactive('.', 1, io.StringIO('first\nsecond\n'), io.StringIO())
        self.assertEqual(result, 1)
        run.assert_called_once()

    def test_interactive_nonbyte_diagnostic_keeps_the_actual_token_id(self):
        response = self.reply()
        response.update(continuation_text=None, generated_tokens=[319], valid_utf8_bytes=False,
                        stop_reason='non_byte_token', eos=False, byte_prefix_hex='')
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(response), stderr='')
        output = io.StringIO()
        with patch.object(board_bos.subprocess, 'run', return_value=completed):
            self.assertEqual(board_bos.run_interactive('.', 1, io.StringIO('x\n'), output), 0)
        self.assertIn('319', output.getvalue())
        self.assertIn('non-byte', output.getvalue().lower())

    def test_failed_or_malformed_child_result_is_fatal_without_retry(self):
        for completed in (SimpleNamespace(returncode=1, stdout='failed', stderr='native'),
                          SimpleNamespace(returncode=0, stdout='not JSON', stderr='')):
            with self.subTest(returncode=completed.returncode), \
                    patch.object(board_bos.subprocess, 'run', return_value=completed) as run:
                with self.assertRaises(RuntimeError):
                    board_bos.completion_request('.', 'fu2p2q', 1)
                run.assert_called_once()

    def test_cli_complete_routes_exact_text_and_default_length(self):
        text = 'Our chocolate-chip RAM'
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], board_bos.package_profile({}))), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--complete', text]), \
                patch.object(board_bos, 'completion_request', return_value=self.reply()) as request, \
                patch.object(board_bos, 'run_generation') as old_generation, \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(board_bos.main(), 0)
        request.assert_called_once_with(Path(board_bos.__file__).resolve().parent, text, 128, encoding='bytes')
        old_generation.assert_not_called()
        self.assertTrue(json.loads(output.getvalue())['hardware_accepted'])

    def test_completion_child_reads_exact_json_prefix_without_nested_child(self):
        text = '\0é\n  fu2p2q '
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], board_bos.package_profile({}))), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--complete=', '--child', '--max-new-tokens', '1']), \
                patch('sys.stdin', io.StringIO(json.dumps({'text': text}))), \
                patch.object(board_bos, 'run_completion', return_value=self.reply()) as complete, \
                patch.object(board_bos.subprocess, 'run') as nested, \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(board_bos.main(), 0)
        complete.assert_called_once_with(Path(board_bos.__file__).resolve().parent, text, 1, encoding='bytes')
        nested.assert_not_called()

    def test_cli_interactive_keeps_input_in_parent_and_text_watchdog_fixed(self):
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], board_bos.package_profile({}))), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--interactive']), \
                patch.object(board_bos, 'run_interactive', return_value=0) as interactive:
            self.assertEqual(board_bos.main(), 0)
        interactive.assert_called_once_with(Path(board_bos.__file__).resolve().parent, 128, encoding='bytes')
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], board_bos.package_profile({}))), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--complete=hello', '--watchdog-seconds', '600']), \
                patch.object(board_bos, 'completion_request') as request, \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(board_bos.main(), 1)
        request.assert_not_called()


class ConditionedInterface(unittest.TestCase):
    def profile(self):
        return board_bos.package_profile({'model_profile': board_bos.CONDITIONED_PROFILE})

    def test_cli_uses_package_codec_and_full_default_output_budget(self):
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], self.profile())), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--complete=hello']), \
                patch.object(board_bos, 'completion_request', return_value=TextInterface.reply()) as request, \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(board_bos.main(), 0)
        request.assert_called_once_with(Path(board_bos.__file__).resolve().parent, 'hello', 255, encoding='hex')
        self.assertEqual(json.loads(output.getvalue())['model_profile'], board_bos.CONDITIONED_PROFILE)

    def test_child_uses_its_verified_package_profile_without_a_codec_argument(self):
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], self.profile())), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--complete=', '--child']), \
                patch('sys.stdin', io.StringIO(json.dumps({'text': 'é'}))), \
                patch.object(board_bos, 'run_completion', return_value=TextInterface.reply()) as request, \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(board_bos.main(), 0)
        request.assert_called_once_with(Path(board_bos.__file__).resolve().parent, 'é', 255, encoding='hex')

    def test_seed_mode_is_rejected_before_a_child_or_device(self):
        with patch.object(board_bos, 'checked_bundle', return_value=(b'', [], self.profile())), \
                patch.object(board_bos.sys, 'argv', ['board_bos.py', '--generate', '47']), \
                patch.object(board_bos.subprocess, 'run') as child, \
                patch.object(board_bos, 'NativeSession') as native, \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(board_bos.main(), 1)
        child.assert_not_called()
        native.assert_not_called()

    def test_parent_rejects_49_bytes_before_child_and_refuses_wrong_child_codec(self):
        with patch.object(board_bos.subprocess, 'run') as child:
            with self.assertRaises(ValueError):
                board_bos.completion_request('.', 'x' * 49, 255, encoding='hex')
            child.assert_not_called()
        wrong = dict(TextInterface.reply(), input_encoding='bytes')
        with patch.object(board_bos.subprocess, 'run', return_value=SimpleNamespace(
                returncode=0, stdout=json.dumps(wrong), stderr='')) as child:
            with self.assertRaisesRegex(RuntimeError, 'Invalid completion child'):
                board_bos.completion_request('.', 'hello', 255, encoding='hex')
            child.assert_called_once()

    def test_interactive_rejects_oversized_utf8_without_losing_the_next_line(self):
        reply = dict(TextInterface.reply(), input_encoding='hex')
        completed = SimpleNamespace(returncode=0, stdout=json.dumps(reply), stderr='')
        with patch.object(board_bos.subprocess, 'run', return_value=completed) as child:
            self.assertEqual(board_bos.run_interactive('.', 255, io.StringIO('é' * 25 + '\nhello\n'),
                                                     io.StringIO(), encoding='hex'), 0)
        child.assert_called_once()
        self.assertEqual(json.loads(child.call_args.kwargs['input']), {'text': 'hello'})

    def test_all_seven_reference_cases_clear_context_and_check_every_logit(self):
        profile = self.profile()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cases = [{'name': name, 'tokens': [256] + [0] * (count - 1),
                      'logits': [[0] * 320] * count} for name, count in profile['cases'].items()]
            (root / 'token-logits.json').write_text(json.dumps({'schema': 1,
                'model_profile': profile['name'], 'original_goldens_sha256': profile['reference_sha256'],
                'cases': cases}))
            session = FakeSession([[0] * 320] * 522)
            with patch.object(board_bos, 'NativeSession', return_value=session):
                result = board_bos.run_validation(root, 'all')
        self.assertEqual(result['explicit_context_clears'], 6)
        self.assertEqual(sum(c['logit_values_checked'] for c in result['cases']), 167040)
        self.assertEqual(len(session.tokens), 522)


class Watchdog(unittest.TestCase):
    def test_parent_uses_absolute_timeout_and_does_not_retry_child(self):
        for mode in (['--validate', 'J01-first16'], ['--generate', '47'], ['--stream']):
            with self.subTest(mode=mode), patch.object(board_bos, 'checked_bundle', return_value=(b'', [], board_bos.package_profile({}))), \
                    patch.object(board_bos.sys, 'argv', ['board_bos.py', *mode]), \
                    patch.object(board_bos.subprocess, 'run', side_effect=subprocess.TimeoutExpired('child', 180)) as run, \
                    patch('sys.stdout', new_callable=io.StringIO):
                self.assertEqual(board_bos.main(), 1)
                run.assert_called_once()
                self.assertEqual(run.call_args.kwargs['timeout'], 180)


if __name__ == '__main__':
    unittest.main()
