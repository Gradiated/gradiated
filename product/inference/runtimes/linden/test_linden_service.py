import asyncio
import importlib.util
import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kev_http', ROOT.parent / 'kev/adapter.py')
adapter = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = adapter
spec.loader.exec_module(adapter)
sys.path.insert(0, str(ROOT))
import prompt  # noqa: E402

spec = importlib.util.spec_from_file_location('linden_service', ROOT / 'service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)


class Tokenizer:
    """Word-level stand-in for the Gemma tokenizer: a token is a run of non-space characters with the spaces before
    it, so ' A' after a prompt is one token, as the real label search needs."""

    def __init__(self):
        self.vocab = {}

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=False):
        text = ''.join(f'<{m["role"]}>\n{m["content"]}\n' for m in messages)
        return text + ('<assistant>\n' if add_generation_prompt else '')

    def encode(self, text, add_special_tokens=False):
        return [self.vocab.setdefault(piece, len(self.vocab)) for piece in re.findall(r'\s*\S+|\s+$', text)]

    def decode(self, ids):
        reverse = {v: k for k, v in self.vocab.items()}
        return ''.join(reverse[i] for i in ids)


class HTTPError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.response = type('Response', (), {'status_code': status})()


class Engine:
    """SGLang's client: prompt tokens are prompt words; the first label is favoured."""

    http_error = HTTPError

    def __init__(self, tokenizer, error=None, logprobs=None):
        self.tokenizer, self.error, self.logprobs = tokenizer, error, logprobs
        self.prefills, self.batches = [], []

    def prefill(self, text):
        self.prefills.append(text)
        return len(self.tokenizer.encode(text))

    def score(self, texts, label_ids):
        if self.error:
            raise self.error
        self.batches.append(len(texts))
        return [((self.logprobs or [0.0] + [-1.0] * (len(ids) - 1))[:len(ids)], len(self.tokenizer.encode(text)))
                for text, ids in zip(texts, label_ids)]


QUESTIONS = {
    'late': {'type': 'noul', 'instructions': 'Is it late?', 'criteria': None},
    'desk': {'type': 'choice', 'instructions': 'Which desk?', 'criteria': {'ship': None, 'bill': {'covers': 'Payments'}}},
    'urgency': {'type': 'score', 'instructions': {'rate': 'urgency'}, 'criteria': ['low', {'level': 'mid'}, 'high']},
}


def make(error=None, logprobs=None, alive=True):
    tokenizer = Tokenizer()
    sglang = Engine(tokenizer, error, logprobs)
    return service.Engine(prompt.Renderer(tokenizer), sglang, lambda: alive), sglang


def ask(engine, questions=QUESTIONS, state='The parcel is three days late.'):
    return engine.answer({'model': service.MODEL, 'state': state, 'questions': questions})


class RenderTests(unittest.TestCase):
    def test_the_token_longest_headed_prompt_decides_the_layout(self):
        renderer = prompt.Renderer(Tokenizer())
        state = {'report': 'word ' * 31_000}
        # Short words outweigh one long word in tokens, though not in characters.
        dense = {'type': 'noul', 'instructions': 'a ' * 1000}
        wide = {'type': 'noul', 'instructions': 'x' * 3000}
        rendered = renderer.render(state, {'dense': dense, 'wide': wide})
        self.assertLessEqual(max(renderer.count(text) for text, _ in rendered.prompts.values()),
                             prompt.HEADER_MAX_TOKENS)


class RuntimeTests(unittest.TestCase):
    def test_answers_have_exactly_the_gateway_fields(self):
        engine, _ = make()
        result = ask(engine)
        answers = result['answers']
        self.assertEqual(set(answers['late']), {'type', 'noul'})
        self.assertEqual(set(answers['desk']), {'type', 'choice', 'confidence', 'probabilities'})
        self.assertEqual(set(answers['urgency']), {'type', 'score', 'legend', 'confidence', 'probabilities'})
        self.assertEqual(answers['desk']['choice'], 'ship')
        # Legend values are text, as the gateway requires, even for JSON levels.
        self.assertEqual(answers['urgency']['legend'], {'0': 'low', '1': 'level: mid', '2': 'high'})
        self.assertEqual(set(result['usage']), {'input_tokens', 'cached_input_tokens', 'output_tokens'})
        self.assertEqual(result['usage']['output_tokens'], 0)
        json.dumps(result, allow_nan=False)

    def test_small_requests_take_one_pass_and_count_distinct_tokens(self):
        engine, sglang = make()
        result = ask(engine)
        self.assertEqual((sglang.prefills, sglang.batches), ([], [3]))
        rendered = engine.renderer.render('The parcel is three days late.', QUESTIONS)
        prefix = engine.renderer.count(rendered.prefix)
        distinct = prefix + sum(engine.renderer.count(text) - prefix for text, _ in rendered.prompts.values())
        self.assertEqual(result['usage']['input_tokens'], distinct)

    def test_large_requests_prefill_the_shared_prefix_first(self):
        engine, sglang = make()
        ask(engine, state={'report': 'word ' * 3000})
        self.assertEqual((len(sglang.prefills), sglang.batches), (1, [3]))

    def test_single_option_choice_needs_no_model(self):
        engine, sglang = make()
        result = ask(engine, {'one': {'type': 'choice', 'instructions': 'Pick', 'criteria': {'only': None}}})
        self.assertEqual(result['answers']['one'],
                         {'type': 'choice', 'choice': 'only', 'confidence': 1.0, 'probabilities': {'only': 1.0}})
        self.assertEqual(sglang.batches, [])
        self.assertGreater(result['usage']['input_tokens'], 0)

    def test_questions_answered_without_the_model_count_in_usage(self):
        engine, _ = make()
        one = {'type': 'choice', 'instructions': 'Pick ' + 'word ' * 200, 'criteria': {'only': 'detail ' * 100}}
        alone = ask(engine, {'one': one})['usage']['input_tokens']
        state_only = engine._count('The parcel is three days late.')
        self.assertGreater(alone - state_only, 300)
        mixed = ask(engine, {**QUESTIONS, 'one': one})['usage']['input_tokens']
        self.assertGreater(mixed - ask(engine)['usage']['input_tokens'], 300)

    def test_model_free_requests_keep_the_token_limit(self):
        engine, _ = make()
        one = {'one': {'type': 'choice', 'instructions': 'Pick', 'criteria': {'only': None}}}
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, one, state='word ' * (service.MAX_TOKENS + 1))
        self.assertEqual(ask(engine, one)['answers']['one']['choice'], 'only')
        huge = {'one': {'type': 'choice', 'instructions': 'word ' * (service.MAX_TOKENS + 1), 'criteria': {'only': None}}}
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, {**QUESTIONS, **huge})

    def test_one_level_score_needs_no_model(self):
        engine, sglang = make()
        result = ask(engine, {'one': {'type': 'score', 'instructions': 'Rate', 'criteria': [{'label': 'only'}]}})
        self.assertEqual(result['answers']['one'], {'type': 'score', 'score': 0.0, 'legend': {'0': 'label: only'},
                                                    'confidence': 1.0, 'probabilities': {'0': 1.0}})
        self.assertEqual(sglang.batches, [])

    def test_questions_without_instructions_use_the_default_stem(self):
        # The TypeSafe SDK omits instructions for criteria-only questions.
        engine, _ = make()
        questions = {'mood': {'type': 'noul', 'criteria': {'true': 'Angry', 'false': 'Calm'}},
                     'desk': {'type': 'choice', 'criteria': {'billing': 'Charges', 'access': 'Login'}}}
        result = ask(engine, questions)
        self.assertEqual(set(result['answers']), {'mood', 'desk'})
        rendered = engine.renderer.render('The parcel is three days late.', questions)
        self.assertIn('Question: ' + prompt.DEFAULT_STEM, rendered.prompts['desk'][0])

    def test_media_is_rejected(self):
        engine, _ = make()
        for state in ({'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'x'}}]}]},
                      {'photo': {'type': 'image', 'image': 'x'}}):
            with self.assertRaises(adapter.InvalidRequest):
                ask(engine, state=state)

    def test_business_objects_with_a_media_type_name_are_data(self):
        engine, _ = make()
        state = {'attachment': {'type': 'file', 'status': 'indexed'}, 'kind': {'type': 'image'}}
        self.assertIn('late', ask(engine, state=state)['answers'])

    def test_role_bearing_business_records_are_data(self):
        engine, _ = make()
        state = [{'role': 'owner', 'content': ['approve']}]
        self.assertIn('late', ask(engine, state=state)['answers'])
        rendered = engine.renderer.render(state, {'late': QUESTIONS['late']})
        self.assertIn('owner', rendered.prefix)

    def test_text_chat_states_are_accepted(self):
        engine, _ = make()
        state = {'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': 'Hello'}]}]}
        self.assertIn('late', ask(engine, state=state)['answers'])

    def test_over_length_is_a_client_error_and_other_engine_errors_need_a_restart(self):
        engine, _ = make(error=HTTPError(400))
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine)
        self.assertTrue(engine.healthy)
        engine, _ = make(error=HTTPError(500))
        with self.assertRaises(RuntimeError):
            ask(engine)
        self.assertFalse(engine.healthy)

    def test_no_finite_label_logprob_is_an_engine_fault(self):
        engine, _ = make(logprobs=[float('-inf')] * 5)
        with self.assertRaises(RuntimeError):
            ask(engine)
        self.assertFalse(engine.healthy)

    def test_a_dead_engine_fails_requests_and_health(self):
        engine, _ = make(alive=False)
        with self.assertRaises(RuntimeError):
            ask(engine)
        app = service.RuntimeApp(engine)
        sent = []

        async def receive():
            return {'type': 'http.request'}

        async def send(message):
            sent.append(message)

        asyncio.run(app({'type': 'http', 'path': '/health', 'method': 'GET', 'headers': []}, receive, send))
        self.assertEqual(sent[0]['status'], 503)

    def test_systemone_requests_round_trip_through_the_adapter(self):
        self._round_trip(QUESTIONS)

    def test_instructionless_questions_reach_the_engine_without_instructions(self):
        # The TypeSafe SDK omits them; the shared validator must not fill them in, or the default stem is lost.
        engine, sglang = make()
        questions = {'q': {'type': 'choice', 'criteria': {'a': 'A', 'b': 'B'}}}
        seen = []
        original = sglang.score
        sglang.score = lambda texts, ids: seen.extend(texts) or original(texts, ids)
        self._round_trip(questions, engine)
        self.assertIn(prompt.DEFAULT_STEM, seen[0])

    def _round_trip(self, questions, engine=None):
        engine = engine or make()[0]
        app = service.RuntimeApp(engine)
        body = json.dumps({'model': 'gradiated/linden-1', 'state': {'ticket': 'Charged twice'},
                           'questions': questions}).encode()
        sent = []
        events = [{'type': 'http.request', 'body': body, 'more_body': False}]

        async def receive():
            return events.pop(0)

        async def send(message):
            sent.append(message)

        headers = [(b'content-type', b'application/json'), (b'content-length', str(len(body)).encode())]
        asyncio.run(app({'type': 'http', 'path': '/v1/systemone', 'method': 'POST', 'headers': headers},
                        receive, send))
        self.assertEqual(sent[0]['status'], 200)
        result = json.loads(sent[1]['body'])
        self.assertEqual(result['model'], 'gradiated/linden-1')
        self.assertEqual(set(result['answers']), set(questions))

    def test_slots_bound_concurrent_requests(self):
        slots = service.Slots(2)
        self.assertTrue(slots.acquire(blocking=False))
        self.assertTrue(slots.acquire(blocking=False))
        self.assertTrue(slots.locked())
        self.assertFalse(slots.acquire(blocking=False))
        slots.release()
        self.assertFalse(slots.locked())
        self.assertEqual(service.RuntimeApp(make()[0]).slot.count, service.ACTIVE_REQUESTS)

    def test_engine_command_is_text_only_with_a_supported_precision(self):
        command = service.sglang_command('/m', 1, 'none')
        self.assertIn('--enable-fp32-lm-head', command)
        self.assertEqual(command[command.index('--chunked-prefill-size') + 1], str(service.MAX_TOKENS))
        self.assertEqual(command[command.index('--context-length') + 1], str(service.MAX_TOKENS + 1))
        self.assertEqual(service.sglang_command('/m', 1, 'fp8')[-2:], ['--quantization', 'fp8'])
        with self.assertRaises(RuntimeError):
            service.sglang_command('/m', 1, 'nf4')


if __name__ == '__main__':
    unittest.main()
