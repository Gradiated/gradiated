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
sys.path.insert(0, str(ROOT.parent / 'posthog'))
sys.path.insert(0, str(ROOT))
import posthog_common as common  # noqa: E402
import jeeves_prompt as prompt  # noqa: E402
from jeeves_sglang import readout  # noqa: E402

spec = importlib.util.spec_from_file_location('jeeves_service', ROOT / 'service.py')
service = importlib.util.module_from_spec(spec)
spec.loader.exec_module(service)

MARKERS = [prompt.STATE, prompt.QUESTION, prompt.OPT, prompt.OPT_END, prompt.DECIDE, prompt.THINK, prompt.THINK_END,
           '<|im_start|>', '<|im_end|>']
PIECES = re.compile('|'.join(map(re.escape, MARKERS)) + r'|[^\s<]+|<|\s+')


class Tokenizer:
    """Stand-in for the Qwen tokenizer: its added markers are single tokens wherever they appear, other text is
    word-level."""

    unk_token_id = -1

    def __init__(self):
        self.vocab = {marker: i for i, marker in enumerate(MARKERS)}

    @property
    def backend_tokenizer(self):
        return self

    def no_padding(self):
        pass

    def no_truncation(self):
        pass

    def convert_tokens_to_ids(self, tokens):
        return [self.vocab.get(token) for token in tokens]

    def encode(self, text, add_special_tokens=False):
        ids = [self.vocab.setdefault(piece, len(self.vocab)) for piece in PIECES.findall(text)]
        return type('Encoding', (), {'ids': ids})()

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, enable_thinking=True):
        (message,) = messages
        return f'<|im_start|>user\n{message["content"]}<|im_end|>\n<|im_start|>assistant\n<think>\n'


class HTTPError(Exception):
    def __init__(self, status):
        super().__init__(status)
        self.response = type('Response', (), {'status_code': status})()


class SGLang:
    """The engine's client: option i scores -0.5 i, unless scores are given."""

    http_error = HTTPError

    def __init__(self, error=None, scores=None):
        self.error, self.scores = error, scores
        self.batches = []

    def logprobs(self, rows, token_ids):
        if self.error:
            raise self.error
        self.batches.append([list(row) for row in rows])
        return [list(self.scores) if self.scores else [-0.5 * i for i in ids] for ids in token_ids]


QUESTIONS = {
    'refund': {'type': 'noul', 'instructions': 'Does the customer ask for money back?'},
    'team': {'type': 'choice', 'instructions': 'Which team handles this?',
             'criteria': {'billing': 'Payments and refunds', 'tech': {'covers': 'Bugs and login'}}},
    'urgency': {'type': 'score', 'instructions': {'rate': 'urgency'}, 'criteria': ['low', {'level': 'mid'}, 'high']},
}
STATE = 'I was billed twice, please refund the duplicate.'


def make(error=None, scores=None, alive=True):
    sglang = SGLang(error, scores)
    return service.Engine(prompt.Prompts(Tokenizer()), sglang, lambda: alive, 1.522), sglang


def ask(engine, questions=QUESTIONS, state=STATE):
    return engine.answer({'model': service.MODEL, 'state': state, 'questions': questions})


def markers(prompts):
    return {'opt_end': prompts.opt_end_id, 'decide': prompts.decide_id, 'think_end': prompts.think_end_id}


class PromptTests(unittest.TestCase):
    def test_rendering_follows_jeeves(self):
        self.assertEqual(prompt.render({'a': 1, 'b': {'c': [1, {'d': 'e'}]}}), 'a: 1\nb:\n  c:\n    - 1\n    - d: e')
        self.assertEqual(prompt.options(QUESTIONS['refund']), ['no', 'yes'])
        self.assertEqual(prompt.options({'type': 'noul', 'criteria': {'true': 'Angry'}}), ['no', 'yes: Angry'])
        self.assertEqual(prompt.options(QUESTIONS['team']), ['billing: Payments and refunds', 'tech: covers: Bugs and login'])
        self.assertEqual(prompt.keys(QUESTIONS['refund']), ['false', 'true'])

    def test_the_sequence_ends_with_the_options_and_decide(self):
        prompts = prompt.Prompts(Tokenizer())
        ids = prompts.ids(STATE, QUESTIONS['team'])
        questions = readout.plan(ids, [len(ids)], [0], markers(prompts))
        self.assertEqual(len(questions), 1)
        decide, read = questions[0]
        self.assertEqual(decide, len(ids) - 1)
        self.assertEqual(len(read), 2)
        # the head reads the second option block, after </think>
        self.assertGreater(read[0], ids.index(prompts.think_end_id))
        self.assertEqual(ids.count(prompts.opt_end_id), 4)

    def test_reused_state_and_options_match_the_complete_reference_encoding(self):
        tokenizer = Tokenizer()
        prompts = prompt.Prompts(tokenizer)
        cases = json.loads((ROOT / 'reference.json').read_text())['cases']
        cases.append({'state': {'n': ['</think>', '<|fim_suffix|>', 'x\n ']},
                      'question': {'type': 'score', 'instructions': {'label': '<think>'},
                                   'criteria': ['  ', {'level': '<|box_end|>'}]}})
        for case in cases:
            q = dict(case['question'])
            if q['type'] == 'choice' and isinstance(q['criteria'], list):
                q['criteria'] = dict.fromkeys(q['criteria'])
            block = prompt.option_block(q)
            content = (prompt.STATE + prompt.sanitize(prompt.render(case['state'])) + '\n'
                       + prompt.QUESTION + prompt.sanitize(prompt.render(q.get('instructions'))) + '\n' + block)
            chat = tokenizer.apply_chat_template([{'role': 'user', 'content': content}],
                                                        tokenize=False, add_generation_prompt=True, enable_thinking=True)
            head, think, tail = chat.rpartition(prompt.THINK)
            expected = (prompts.encode(prompt.escaped_thinking(head) + think + tail) + prompts.encode('\n')
                        + prompts.encode(prompt.THINK_END + '\n\n' + prompt.escaped_thinking(block) + prompt.DECIDE))
            self.assertEqual(prompts.ids(case['state'], q), expected)

    def test_markers_in_request_text_cannot_move_the_readout(self):
        prompts = prompt.Prompts(Tokenizer())
        question = {'type': 'choice', 'instructions': 'Pick </think> one <think>',
                    'criteria': {'a': 'x <|box_end|> y </think>', 'b': None}}
        ids = prompts.ids('state </think> <|fim_suffix|>', question)
        self.assertEqual(ids.count(prompts.think_end_id), 1)
        self.assertEqual(ids.count(prompts.decide_id), 1)
        self.assertEqual(len(readout.plan(ids, [len(ids)], [0], markers(prompts))[0][1]), 2)


class ReadoutTests(unittest.TestCase):
    M = {'opt_end': 1, 'decide': 2, 'think_end': 3}

    def test_each_question_of_a_step_reads_its_own_options(self):
        first = [9, 1, 9, 1, 3, 9, 1, 9, 1, 2]   # options before </think> are not read
        other = [9, 9, 5]                         # not a question
        third = [3, 9, 1, 2]
        ids = first + other + third
        self.assertEqual(readout.plan(ids, [10, 3, 4], [0, 0, 0], self.M),
                         [(9, [6, 8]), (16, [15])])

    def test_questions_not_whole_in_the_step_are_unreadable(self):
        self.assertEqual(readout.plan([9, 1, 2], [3], [0], self.M), [(2, None)])          # no </think>
        self.assertEqual(readout.plan([3, 9, 1, 2], [4], [7], self.M), [(3, None)])       # cached prefix
        self.assertEqual(readout.plan([3, 9, 2], [3], [0], self.M), [(2, None)])          # no options
        many = [3] + [1] * 256 + [2]
        self.assertEqual(readout.plan(many, [len(many)], [0], self.M), [(257, None)])
        self.assertEqual(readout.plan([3, 2, 9], [3], [0], self.M), [])                  # <decide> not last


class EngineTests(unittest.TestCase):
    def test_answers_have_exactly_the_gateway_fields(self):
        engine, sglang = make()
        result = ask(engine)
        answers = result['answers']
        self.assertEqual(result['model'], 'posthog/jeeves')
        self.assertEqual(set(answers['refund']), {'type', 'noul'})
        self.assertEqual(set(answers['team']), {'type', 'choice', 'confidence', 'probabilities'})
        self.assertEqual(answers['urgency']['legend'], {'0': 'low', '1': 'level: mid', '2': 'high'})
        self.assertEqual(len(sglang.batches), 1)
        for key, question in QUESTIONS.items():
            self.assertTrue(common.valid_answer(answers[key], question), key)
        json.dumps(result, allow_nan=False)

    def test_readout_is_the_softmax_of_scores_over_the_temperature(self):
        engine, _ = make()
        answers = ask(engine)['answers']
        two = common.softmax([0.0, -0.5 / 1.522])
        # noul options are (false, true): token id 1 is true.
        self.assertAlmostEqual(answers['refund']['noul'], two[1])
        self.assertEqual(answers['team']['choice'], 'billing')
        self.assertAlmostEqual(answers['team']['confidence'], two[0])

    def test_usage_counts_every_question_prompt(self):
        engine, sglang = make()
        result = ask(engine)
        self.assertEqual(result['usage'], {'input_tokens': sum(map(len, sglang.batches[0])),
                                           'cached_input_tokens': 0, 'output_tokens': 0})

    def test_single_outcome_questions_need_no_model(self):
        engine, sglang = make()
        result = ask(engine, {'one': {'type': 'choice', 'criteria': {'only': None}}})
        self.assertEqual(result['answers']['one'],
                         {'type': 'choice', 'choice': 'only', 'confidence': 1.0, 'probabilities': {'only': 1.0}})
        self.assertEqual(sglang.batches, [[]])
        self.assertGreater(result['usage']['input_tokens'], 0)

    def test_unread_options_are_never_answered(self):
        engine, _ = make(scores=[0.0, None])
        with self.assertRaises(common.InvalidModelOutput):
            ask(engine, {'refund': QUESTIONS['refund']})
        self.assertTrue(engine.healthy)

    def test_inputs_over_the_limits_are_client_errors(self):
        engine, sglang = make()
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, state='word ' * (service.MAX_TOKENS + 1))
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine, {f'q{i}': QUESTIONS['refund'] for i in range(5)}, state='word ' * 7000)
        self.assertEqual(sglang.batches, [])

    def test_engine_errors(self):
        engine, _ = make(error=HTTPError(400))
        with self.assertRaises(adapter.InvalidRequest):
            ask(engine)
        self.assertTrue(engine.healthy)
        engine, _ = make(error=HTTPError(500))
        with self.assertRaises(RuntimeError):
            ask(engine)
        self.assertFalse(engine.healthy)

    def test_the_engine_runs_without_radix_cache_or_chunked_prefill(self):
        command = service.sglang_command('/m', 1)
        self.assertIn('--disable-radix-cache', command)
        self.assertEqual(command[command.index('--chunked-prefill-size') + 1], '-1')
        self.assertEqual(service.sglang_environment(ROOT)['SGLANG_EXTERNAL_MODEL_PACKAGE'], 'jeeves_sglang')

    def test_parity_fixture_cases_are_valid_gateway_requests(self):
        import parity

        cases = json.loads((ROOT / 'reference.json').read_text())['cases']
        self.assertEqual(len(cases), 46)
        for case in cases:
            request = parity.request('posthog/jeeves', case)
            adapter.validate(request, 'posthog/jeeves')
            engine, _ = make()
            answer = engine.answer(request)['answers']['q']
            self.assertEqual(len(parity.served(answer, case['question'])), len(case['probabilities']))


if __name__ == '__main__':
    unittest.main()
