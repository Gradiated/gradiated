import asyncio
import importlib.util
import math
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kev_http', ROOT.parent / 'kev/adapter.py')
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)
spec = importlib.util.spec_from_file_location('decider_service', ROOT / 'service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class RequestError(ValueError):
    pass


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.decider = Mock()
        self.decider.encoder.encode.return_value = SimpleNamespace(length=100)
        self.decider.decide.return_value = {'answers': {'ok': {'type': 'noul', 'noul': 0.75}},
            'usage': {'input_tokens': 100, 'output_tokens': 0, 'sequences': 1}}
        self.sync = Mock()
        self.engine = service.Engine(self.decider, (RequestError,), self.sync)
        self.data = {'model': service.MODEL, 'state': {'messages': [{'image_url': 'http://example.invalid'}]},
                     'questions': {'ok': {'type': 'noul', 'instructions': {'rule': 'Check'}}}}

    def test_structured_content_stays_text_and_usage_preserves_all_prompt_tokens(self):
        result = self.engine.answer(self.data)
        request = self.decider.decide.call_args.args[0]
        self.assertEqual(set(request), {'state', 'questions'})
        self.assertIsInstance(request['state'], str)
        self.assertEqual(request['questions']['ok']['instructions'], '{"rule": "Check"}')
        self.assertEqual(result['model'], service.MODEL)
        self.assertEqual(result['usage'], {'input_tokens': 100, 'cached_input_tokens': 0, 'output_tokens': 0})
        self.sync.assert_called_once()

    def test_oversized_joint_request_is_rejected_before_any_forward_pass(self):
        self.decider.encoder.encode.return_value.length = 8193
        with self.assertRaises(adapter.InvalidRequest):
            self.engine.answer(self.data)
        self.decider.decide.assert_not_called()
        self.assertTrue(self.engine.healthy)

    def test_schema_failure_is_generic_and_does_not_poison_model(self):
        self.decider.encoder.validate.side_effect = RequestError('private input')
        with self.assertRaisesRegex(adapter.InvalidRequest, 'invalid decision request') as error:
            self.engine.answer(self.data)
        self.assertNotIn('private input', str(error.exception))
        self.assertTrue(self.engine.healthy)

    def test_gpu_failure_closes_health_and_refuses_more_work(self):
        self.decider.decide.side_effect = RuntimeError('private prompt CUDA failure')
        with self.assertRaisesRegex(RuntimeError, 'requires restart'):
            self.engine.answer(self.data)
        self.assertFalse(self.engine.healthy)
        with self.assertRaisesRegex(RuntimeError, 'requires restart'):
            self.engine.answer(self.data)
        self.assertEqual(self.decider.decide.call_count, 1)
        events = []
        async def send(event):
            events.append(event)
        asyncio.run(service.RuntimeApp(self.engine)(
            {'type': 'http', 'path': '/health'}, Mock(), send))
        self.assertEqual(events[0]['status'], 503)

    def test_split_or_invalid_usage_cannot_be_reported_as_one_joint_request(self):
        for usage in [{'input_tokens': 100, 'output_tokens': 0, 'sequences': 2},
                      {'input_tokens': 8193, 'output_tokens': 0, 'sequences': 1},
                      {'input_tokens': True, 'output_tokens': 0, 'sequences': 1}]:
            with self.subTest(usage=usage):
                self.engine.healthy = True
                self.decider.decide.return_value['usage'] = usage
                with self.assertRaisesRegex(RuntimeError, 'invalid decision model output'):
                    self.engine.answer(self.data)
                self.assertFalse(self.engine.healthy)

    def test_choice_and_score_require_the_pinned_formatters_normalized_distribution(self):
        for kind in ['choice', 'score']:
            question = {'type': kind, 'criteria': (
                {'a': None, 'b': None, 'c': None} if kind == 'choice' else ['low', 'medium', 'high'])}
            keys = list(question['criteria']) if kind == 'choice' else ['0', '1', '2']
            answer = {'type': kind, 'probabilities': dict.fromkeys(keys, 1 / 3),
                      **({'choice': 'a'} if kind == 'choice' else {'score': 1.})}
            self.assertTrue(service.valid_answer(answer, question))
            answer['probabilities'] = dict.fromkeys(keys, .33)
            self.assertFalse(service.valid_answer(answer, question))

    def test_nonfinite_or_malformed_answers_fail_health(self):
        for answer in [None, {'type': 'noul', 'noul': math.nan},
                       {'type': 'noul', 'noul': True}, {'type': 'noul', 'noul': 1.1},
                       {'type': 'choice', 'choice': 'unexpected'}]:
            with self.subTest(answer=answer):
                self.engine.healthy = True
                self.decider.decide.return_value['answers']['ok'] = answer
                with self.assertRaisesRegex(RuntimeError, 'invalid decision model output'):
                    self.engine.answer(self.data)
                self.assertFalse(self.engine.healthy)
