import asyncio
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kev_http', ROOT.parent / 'kev/adapter.py')
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)
sys.path.insert(0, str(ROOT.parent / 'posthog'))
sys.path.insert(0, str(ROOT))
import posthog_common as common  # noqa: E402
import jevk5_prompt as upstream  # noqa: E402

spec = importlib.util.spec_from_file_location('jevk5_service', ROOT / 'service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class Tokenizer:
    """Word-level stand-in for the Qwen tokenizer: a token is a run of non-space characters with the spaces before
    it, so each answer letter is one token."""

    def __init__(self):
        self.vocab = {}

    def encode(self, text, add_special_tokens=False):
        return [self.vocab.setdefault(piece, len(self.vocab)) for piece in re.findall(r'\s*\S+|\s+$', text)]


class HTTPError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.response = type('Response', (), {'status_code': status})()


class SGLang:
    """The engine's client: letter i of a pass has log probability -0.3 i, unless logprobs are given."""

    http_error = HTTPError

    def __init__(self, error=None, logprobs=None):
        self.error, self.fixed = error, logprobs
        self.batches = []
        self.cache_args = []

    def logprobs(self, rows, token_ids, **cache):
        self.cache_args.append(cache)
        if self.error:
            raise self.error
        self.batches.append(len(rows))
        return [list(self.fixed) if self.fixed else [-0.3 * i for i in range(len(ids))] for ids in token_ids]


QUESTIONS = {
    'refund': {'type': 'noul', 'instructions': 'Does the customer ask for money back?'},
    'team': {'type': 'choice', 'instructions': 'Which team handles this?',
             'criteria': {'billing': 'Payments and refunds', 'tech': {'covers': 'Bugs and login'}}},
    'urgency': {'type': 'score', 'instructions': {'rate': 'urgency'}, 'criteria': ['low', {'level': 'mid'}, 'high']},
}


def make(error=None, logprobs=None, alive=True):
    sglang = SGLang(error, logprobs)
    return service.Engine(Tokenizer(), sglang, lambda: alive, 1.22, 0.93), sglang


def ask(engine, questions=QUESTIONS, state='I was billed twice, please refund the duplicate.'):
    return engine.answer({'model': service.MODEL, 'state': state, 'questions': questions})


def letter_distribution(n, temperature=1.22):
    return common.softmax([-0.3 * i / temperature for i in range(n)])


class JevK5Tests(unittest.TestCase):
    def test_sglang_serves_the_checkpoint_through_jevk5_sglang(self):
        command = service.sglang_command('/m', 1)
        override = command[command.index('--json-model-override-args') + 1]
        self.assertEqual(json.loads(override), {'architectures': ['JevK5ForCausalLM']})
        self.assertEqual(command[command.index('--mamba-radix-cache-strategy') + 1], 'extra_buffer')
        self.assertIn('--disable-overlap-schedule', command)
        self.assertEqual(command[command.index('--cuda-graph-backend-prefill') + 1], 'breakable')
        self.assertEqual(service.sglang_environment(Path('/r')),
                         {'SGLANG_EXTERNAL_MODEL_PACKAGE': 'jevk5_sglang', 'PYTHONPATH': '/r'})

    def test_the_model_loads_vision_language_weight_names_and_refuses_gaps(self):
        # A stand-in for SGLang's Qwen3_5ForCausalLM, whose loader takes model.* names.
        import types
        received = []

        class Base:
            def __init__(self, parameters):
                self.parameters = parameters

            def named_parameters(self):
                return [(name, None) for name in self.parameters]

            def load_weights(self, weights):
                received.extend(name for name, _ in weights)
                return set(received)

        modules = {'sglang': types.ModuleType('sglang'), 'sglang.srt': types.ModuleType('sglang.srt'),
                   'sglang.srt.models': types.ModuleType('sglang.srt.models'),
                   'sglang.srt.models.qwen3_5_text': types.ModuleType('sglang.srt.models.qwen3_5_text'),
                   'torch': sys.modules.get('torch') or types.ModuleType('torch')}
        modules['sglang.srt.models.qwen3_5_text'].Qwen3_5ForCausalLM = Base
        modules['torch'].Tensor = getattr(modules['torch'], 'Tensor', object)
        saved = {name: sys.modules.get(name) for name in modules}
        sys.modules.update(modules)
        try:
            spec = importlib.util.spec_from_file_location('jevk5_model', ROOT / 'jevk5_sglang/model.py')
            model = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(model)
            loaded = model.JevK5ForCausalLM(['model.layers.0.mlp.up_proj.weight', 'model.norm.weight']).load_weights(
                [('model.language_model.layers.0.mlp.up_proj.weight', 0), ('model.language_model.norm.weight', 0)])
            self.assertEqual(received, ['model.layers.0.mlp.up_proj.weight', 'model.norm.weight'])
            self.assertEqual(loaded, set(received))
            received.clear()
            with self.assertRaisesRegex(RuntimeError, 'left 1 parameters unloaded'):
                model.JevK5ForCausalLM(['model.layers.0.mlp.up_proj.weight', 'model.norm.weight']).load_weights(
                    [('model.language_model.norm.weight', 0)])
        finally:
            for name, module in saved.items():
                if module is None:
                    sys.modules.pop(name, None)
                else:
                    sys.modules[name] = module

    def test_the_vendored_prompt_is_upstreams(self):
        digest = hashlib.sha256((ROOT / 'jevk5_prompt.py').read_bytes()).hexdigest()
        self.assertEqual(digest, service.UPSTREAM_PROMPT_SHA256)

    def test_answers_have_exactly_the_gateway_fields(self):
        engine, sglang = make()
        result = ask(engine)
        answers = result['answers']
        self.assertEqual(result['model'], 'posthog/jevk5')
        self.assertEqual(set(answers['refund']), {'type', 'noul'})
        self.assertEqual(set(answers['team']), {'type', 'choice', 'confidence', 'probabilities'})
        self.assertEqual(set(answers['urgency']), {'type', 'score', 'legend', 'confidence', 'probabilities'})
        self.assertEqual(answers['urgency']['legend'], {'0': 'low', '1': '{"level": "mid"}', '2': 'high'})
        self.assertEqual(set(result['usage']), {'input_tokens', 'cached_input_tokens', 'output_tokens'})
        self.assertEqual((result['usage']['cached_input_tokens'], result['usage']['output_tokens']), (0, 0))
        self.assertEqual(sglang.batches, [3])
        for key, question in QUESTIONS.items():
            self.assertTrue(common.valid_answer(answers[key], question), key)
        json.dumps(result, allow_nan=False)

    def test_readout_is_the_softmax_of_letter_logits_over_the_temperature(self):
        engine, _ = make()
        answers = ask(engine)['answers']
        # noul options are upstream's (true, false): letter A is true.
        self.assertAlmostEqual(answers['refund']['noul'], letter_distribution(2)[0])
        self.assertEqual(answers['team']['choice'], 'billing')
        self.assertEqual(list(answers['team']['probabilities']), ['billing', 'tech'])
        self.assertAlmostEqual(answers['team']['confidence'], letter_distribution(2)[0])
        levels = letter_distribution(3)
        self.assertAlmostEqual(answers['urgency']['score'], levels[1] + 2 * levels[2])

    def test_usage_counts_every_pass_like_upstream(self):
        engine, _ = make()
        state = 'I was billed twice, please refund the duplicate.'
        result = ask(engine, state=state)
        expected = sum(len(engine.encode(state, q['instructions'], [t for _, t in service.options(q)]))
                       for q in QUESTIONS.values())
        self.assertEqual(result['usage']['input_tokens'], expected)

    def test_more_than_sixteen_options_take_upstreams_knockout(self):
        engine, sglang = make()
        question = {'type': 'choice', 'instructions': 'Which intent?',
                    'criteria': {f'intent_{i}': f'Intent {i}' for i in range(40)}}
        answer = ask(engine, {'intent': question})['answers']['intent']
        texts = [text for _, text in service.options(question)]
        expected = upstream.spread(lambda passed: letter_distribution(len(passed)), texts, 'knockout', 0.93)
        self.assertEqual(sglang.batches, [3, 1])  # three groups, then the final
        for got, want in zip(answer['probabilities'].values(), expected):
            self.assertAlmostEqual(got, want)
        self.assertTrue(common.valid_answer(answer, question))

    def test_later_knockout_passes_are_held_to_the_request_limit(self):
        engine, sglang = make()
        question = {'type': 'choice', 'instructions': 'Which intent?',
                    'criteria': {f'intent_{i}': f'Intent {i}' for i in range(64)}}
        engine._later_tokens = lambda *args: 0  # an estimate that misses the final's cost
        state = 'word ' * 14000
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, {'intent': question}, state=state)
        self.assertEqual(sglang.batches, [1, 3])

    def test_knockout_pass_counts(self):
        self.assertEqual([service.passes(n) for n in (2, 16, 17, 77, 255, 300)], [1, 1, 3, 6, 17, 22])

    def test_single_outcome_questions_need_no_model(self):
        engine, sglang = make()
        result = ask(engine, {'one': {'type': 'choice', 'instructions': 'Pick', 'criteria': {'only': None}},
                              'level': {'type': 'score', 'criteria': [{'label': 'only'}]}})
        self.assertEqual(result['answers']['one'],
                         {'type': 'choice', 'choice': 'only', 'confidence': 1.0, 'probabilities': {'only': 1.0}})
        self.assertEqual(result['answers']['level'], {'type': 'score', 'score': 0.0,
                                                      'legend': {'0': '{"label": "only"}'}, 'confidence': 1.0,
                                                      'probabilities': {'0': 1.0}})
        self.assertEqual(sglang.batches, [])
        self.assertGreater(result['usage']['input_tokens'], 0)

    def test_questions_without_instructions_are_asked_with_none(self):
        engine, _ = make()
        result = ask(engine, {'mood': {'type': 'noul', 'criteria': {'true': 'Angry', 'false': 'Calm'}}})
        self.assertEqual(set(result['answers']['mood']), {'type', 'noul'})

    def test_the_worker_qualification_request_is_answered(self):
        engine, _ = make()
        result = ask(engine, {'category': {'type': 'choice', 'instructions': 'Choose the support department',
                                           'criteria': {'billing': 'Payments and charges',
                                                        'technical': 'Software errors'}}},
                     state={'message': 'I was charged twice. This is a billing problem.', 'verification': 'x'})
        self.assertEqual(result['answers']['category']['type'], 'choice')
        self.assertGreater(result['usage']['input_tokens'], 0)

    def test_cold_multi_pass_primes_with_first_pass_then_batches_and_warm_batches_all(self):
        engine, sglang = make()
        long_state = 'ticket event details ' * 80
        ask(engine, QUESTIONS, state=long_state)
        state_len = len(engine.state_ids(long_state))
        self.assertGreaterEqual(state_len, common.GDN_CHECKPOINT_TOKENS)
        self.assertEqual(sglang.batches, [1, 2])
        self.assertEqual(sglang.cache_args[-1]['custom_params'], {'jevk5_state_tokens': state_len})
        # Warm repeat over the same state batches all 3 questions in one pass.
        sglang.batches.clear()
        ask(engine, QUESTIONS, state=long_state)
        self.assertEqual(sglang.batches, [3])

    def test_short_state_does_not_split_cold_batches_or_send_checkpoint_hint(self):
        engine, sglang = make()
        ask(engine, QUESTIONS, state='short')
        self.assertEqual(sglang.batches, [3])
        self.assertIsNone(sglang.cache_args[-1]['custom_params'])

    def test_state_ids_handles_nested_criterion_keys_structurally(self):
        engine, _ = make()
        state = {'criterion': 'nested', 'payload': 'ticket ' * 80}
        state_ids = engine.state_ids(state)
        row = engine.encode(state, 'outer question', ['A: yes', 'B: no'])
        self.assertEqual(row[:len(state_ids)], state_ids)
        self.assertGreater(len(state_ids), 80)

    def test_inputs_over_the_limits_are_client_errors(self):
        engine, sglang = make()
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, state='word ' * (service.MAX_TOKENS + 1))
        questions = {f'q{i}': QUESTIONS['refund'] for i in range(5)}
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, questions, state='word ' * 15000)
        self.assertEqual(sglang.batches, [])
        self.assertTrue(engine.healthy)

    def test_over_length_is_a_client_error_and_other_engine_errors_need_a_restart(self):
        engine, _ = make(error=HTTPError(400))
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine)
        self.assertTrue(engine.healthy)
        engine, _ = make(error=HTTPError(500))
        with self.assertRaises(RuntimeError):
            ask(engine)
        self.assertFalse(engine.healthy)

    def test_missing_letters_are_never_answered(self):
        engine, _ = make(logprobs=[0.0, None])
        with self.assertRaises(common.InvalidModelOutput):
            ask(engine, {'refund': QUESTIONS['refund']})

    def test_a_dead_engine_fails_health(self):
        engine, _ = make(alive=False)
        app = common.RuntimeApp(engine)
        sent = []

        async def send(message):
            sent.append(message)

        asyncio.run(app({'type': 'http', 'path': '/health', 'method': 'GET', 'headers': []}, None, send))
        self.assertEqual(sent[0]['status'], 503)

    def test_parity_fixture_cases_are_valid_gateway_requests(self):
        cases = json.loads((ROOT / 'reference.json').read_text())['cases']
        self.assertEqual(len(cases), 46)
        sys.path.insert(0, str(ROOT.parent / 'posthog'))
        import parity

        for case in cases:
            request = parity.request('posthog/jevk5', case)
            adapter.validate(request, 'posthog/jevk5')
            engine, _ = make()
            answer = engine.answer(request)['answers']['q']
            self.assertEqual(len(parity.served(answer, case['question'])), len(case['probabilities']))


if __name__ == '__main__':
    unittest.main()
