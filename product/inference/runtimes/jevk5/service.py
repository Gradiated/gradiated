"""posthog/jevk5 native SystemOne serving: JevK5's prompt and letter readout over a loopback SGLang engine.

JevK5 (alibiserikbay/JevK5, Qwen3.5-4B with a merged distilled LoRA) answers a question with one uppercase letter.
Its decision is the softmax of the answer letters' raw next-token logits divided by the calibration temperature
(1.22, jevk5_config.json). SGLang returns the letters' log probabilities, which differ from the raw logits by one
constant per prompt, so the softmax over the letters is the same. Questions with more than 16 options take the
"knockout" passes of upstream's jevk5.prompt.spread (vendored verbatim as jevk5_prompt.py), sharpened by the
model's knockout temperature (0.93).

The prompts, the option texts and the combination of passes are upstream's code at the pinned commit; the request
and response shapes are the gateway's (product/packages/contracts/src/systemone.ts).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import sys
import time

from kev_http import InvalidRequest, read_token
import posthog_common as common
import jevk5_prompt as upstream

log = logging.getLogger('jevk5.service')

MODEL = 'posthog/jevk5'
CHECKPOINT = 'alibiserikbay/JevK5'
# JevK5 v0.3, Apache-2.0. verify-build.py refuses to package an unpinned runtime.
REVISION = 'c4f7fdb3aeab5582336406e78d3bef11bf98833d'
# The upstream jevk5 package commit whose prompt.py is vendored as jevk5_prompt.py (release 0.3.2).
UPSTREAM_COMMIT = '7b97499c'
UPSTREAM_PROMPT_SHA256 = '322d69ba6abea83602f27b7a5aa0d3e6ab00847fd03ddccd35a28ae5b23acc1a'
# JevK5's own input limit: a pass whose prompt is longer is rejected, never truncated.
MAX_TOKENS = 16384
# About ten seconds of an L4's prompt throughput; a request whose passes sum to more is rejected before it runs.
REQUEST_MAX_TOKENS = 65536
ACTIVE_REQUESTS = 8
# A request's passes share the prompt up to their criterion (template, system prompt and the state). When enough of
# it would be recomputed, it is prefilled once first and the passes start from its cached state.
SHARED_PREFIX_MIN_TOKENS = 128
SHARED_PREFIX_SAVED_TOKENS = 1024
# The pinned Qwen3.5 GatedDeltaNet backend checkpoints recurrent state on 64-token boundaries.
GDN_CHECKPOINT_TOKENS = 64
LONG_SHARED_PREFIX_TOKENS = 2560
SGLANG_FLAGS = [
    '--mem-fraction-static', '0.80', '--max-running-requests', '64',
    # A whole prompt is read in one step; JevK5's limit is the step.
    '--max-prefill-tokens', str(MAX_TOKENS + 1), '--chunked-prefill-size', str(MAX_TOKENS + 1),
    '--enable-fp32-lm-head',
]


class Unread(Exception):
    """A pass upstream's spread asked for that has not been read yet."""


def options(question):
    """Upstream's option ids and texts for a question in the gateway's shape."""
    return upstream.decision_options({**question, 'criteria': question.get('criteria')})


def legend(question):
    """A score question's levels as text, as the gateway requires."""
    return {str(i): level if isinstance(level, str) else json.dumps(level, ensure_ascii=False)
            for i, level in enumerate(question['criteria'])}


def first_reads(n):
    """The option indices of a question's first passes: all of them up to 16, else the knockout's groups."""
    letters = len(upstream.LETTERS)
    return [range(n)] if n <= letters else upstream.groups(n, -(-n // letters))


def passes(n):
    """Passes the knockout reads for n options: its groups, then a final of max(16, groups) options."""
    letters = len(upstream.LETTERS)
    if n <= letters:
        return 1
    runs = -(-n // letters)
    return runs + passes(max(letters, runs))


class Engine:
    model = MODEL

    def __init__(self, tokenizer, sglang, sglang_alive, temperature, knockout_temperature):
        self.tokenizer, self.sglang, self.sglang_alive = tokenizer, sglang, sglang_alive
        self.temperature, self.knockout_temperature = temperature, knockout_temperature
        letters = [tokenizer.encode(letter, add_special_tokens=False) for letter in upstream.LETTERS]
        if any(len(ids) != 1 for ids in letters):
            raise RuntimeError('every answer letter must be one token')
        self.letters = [ids[0] for ids in letters]
        self.healthy = True

    def encode(self, state, instructions, texts):
        return self.tokenizer.encode(upstream.prompt_text(state, instructions, texts), add_special_tokens=False)

    def answer(self, data):
        if not self.healthy or not self.sglang_alive():
            self.healthy = False
            raise RuntimeError('runtime requires restart')
        started = time.perf_counter()
        state, questions = data['state'], data['questions']
        # Questions without instructions (the TypeSafe SDK omits them for criteria-only questions) ask with none.
        instructions = {key: q.get('instructions', '') for key, q in questions.items()}
        texts = {key: [text for _, text in options(q)] for key, q in questions.items()}
        answers, tokens, rows = {}, 0, {}
        for key, question in questions.items():
            if common.single_outcome(question):
                # One outcome is certain, and is answered without the model; its prompt still counts as input.
                ids = self.encode(state, instructions[key], texts[key])
                self._check_length(ids)
                tokens += len(ids)
                answers[key] = common.answer(question, {options(question)[0][0]: 1.0}, legend(question)
                                             if question['type'] == 'score' else None)
                continue
            for run in first_reads(len(texts[key])):
                pass_texts = tuple(texts[key][i] for i in run)
                rows[key, pass_texts] = self.encode(state, instructions[key], list(pass_texts))
                self._check_length(rows[key, pass_texts])
        later = sum(self._later_tokens(state, instructions[key], texts[key]) for key in questions
                    if key not in answers)
        if tokens + sum(map(len, rows.values())) + later > REQUEST_MAX_TOKENS:
            raise InvalidRequest(f'request exceeds {REQUEST_MAX_TOKENS} input tokens')
        known = {key: {} for key in questions if key not in answers}
        try:
            self._share_prefix(list(rows.values()))
            while rows:
                # The estimate above admits the request; the passes the knockout actually asks for are held to the
                # same bound, since an option's characters need not predict its tokens.
                if tokens + sum(map(len, rows.values())) > REQUEST_MAX_TOKENS:
                    raise InvalidRequest(f'request exceeds {REQUEST_MAX_TOKENS} input tokens')
                read = self._read(list(rows), list(rows.values()))
                tokens += sum(map(len, rows.values()))
                for (key, pass_texts), probabilities in read.items():
                    known[key][pass_texts] = probabilities
                rows = {}
                for key in [key for key in known if key not in answers]:
                    done, missing = self._spread(known[key], texts[key])
                    if missing is None:
                        answers[key] = common.answer(questions[key], dict(zip(
                            [option for option, _ in options(questions[key])], done)),
                            legend(questions[key]) if questions[key]['type'] == 'score' else None)
                    else:
                        rows[key, missing] = self.encode(state, instructions[key], list(missing))
                        self._check_length(rows[key, missing])
        except (InvalidRequest, common.InvalidModelOutput):
            raise
        except self.sglang.http_error as exc:
            # SGLang answers 400 for a prompt over the context length; anything else is a failed engine.
            if exc.response is not None and exc.response.status_code == 400:
                raise InvalidRequest(f'input exceeds {MAX_TOKENS} tokens') from None
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        except Exception:
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        answers = {key: answers[key] for key in questions}
        if any(not common.valid_answer(answers[key], question) for key, question in questions.items()):
            raise common.InvalidModelOutput('invalid decision model output')
        # Upstream counts every pass's whole prompt; nothing is reported as cached.
        return {'model': MODEL, 'answers': answers,
                'usage': {'input_tokens': tokens, 'cached_input_tokens': 0, 'output_tokens': 0},
                'latency_ms': round((time.perf_counter() - started) * 1000, 3)}

    def _check_length(self, ids):
        if len(ids) > MAX_TOKENS:
            raise InvalidRequest(f'input is {len(ids)} tokens; the limit is {MAX_TOKENS}')

    def _later_tokens(self, state, instructions, texts):
        """Prompt tokens of the passes after the first ones, each taken to hold the 16 longest options."""
        later = passes(len(texts)) - len(first_reads(len(texts)))
        if not later:
            return 0
        return later * len(self.encode(state, instructions, sorted(texts, key=len)[-len(upstream.LETTERS):]))

    def _share_prefix(self, rows):
        if len(rows) < 2:
            return
        shared = common.common_prefix_length(rows)
        if shared >= SHARED_PREFIX_MIN_TOKENS and shared * (len(rows) - 1) >= SHARED_PREFIX_SAVED_TOKENS:
            # The production L4 uses the full shared prefix outside this measured shape.
            if len(rows) == 3 and shared >= LONG_SHARED_PREFIX_TOKENS:
                shared -= shared % GDN_CHECKPOINT_TOKENS
            self.sglang.prefill(rows[0][:shared])

    def _read(self, keys, rows):
        """One batched engine call: the calibrated letter distribution of every pass."""
        letters = [self.letters[:len(pass_texts)] for _, pass_texts in keys]
        out = {}
        for key, logprobs in zip(keys, self.sglang.logprobs(rows, letters)):
            if any(value is None for value in logprobs):
                raise common.InvalidModelOutput('SGLang did not return every answer letter')
            out[key] = common.softmax([value / self.temperature for value in logprobs])
        return out

    def _spread(self, known, texts):
        """Upstream's spread over the passes read so far: (distribution, None), or (None, the next pass to read)."""
        def read(pass_texts):
            pass_texts = tuple(pass_texts)
            if pass_texts not in known:
                raise Unread(pass_texts)
            return known[pass_texts]

        try:
            return upstream.spread(read, texts, 'knockout', self.knockout_temperature), None
        except Unread as missing:
            return None, missing.args[0]


def sglang_command(checkpoint, port):
    # JevK5ForCausalLM (jevk5_sglang/model.py) loads the checkpoint's vision-language weight names.
    return common.sglang_command(checkpoint, port, MAX_TOKENS, [
        *SGLANG_FLAGS, '--json-model-override-args', json.dumps({'architectures': ['JevK5ForCausalLM']})])


def sglang_environment(root):
    """SGLang imports JevK5ForCausalLM from the bundle's jevk5_sglang package."""
    return {'SGLANG_EXTERNAL_MODEL_PACKAGE': 'jevk5_sglang', 'PYTHONPATH': str(root)}


def load(checkpoint):
    from transformers import AutoTokenizer

    config = json.loads((Path(checkpoint) / 'jevk5_config.json').read_text())
    process, url = common.start_sglang(sglang_command(checkpoint, common.free_port()),
                                       sglang_environment(Path(__file__).resolve().parent))
    return Engine(AutoTokenizer.from_pretrained(checkpoint), common.client(url, ACTIVE_REQUESTS),
                  lambda: process.poll() is None, float(config['temperature']),
                  float(config.get('knockout_temperature', upstream.TEMPERATURES['knockout'])))


def warm(engine):
    started = time.perf_counter()
    questions = {
        'refund': {'type': 'noul', 'instructions': 'Does the customer ask for money back?'},
        'team': {'type': 'choice', 'instructions': 'Which team handles this?',
                 'criteria': {'billing': 'Payments and refunds', 'tech': 'Bugs and login'}},
        'urgency': {'type': 'score', 'instructions': 'Rate urgency.', 'criteria': ['routine', 'urgent', 'critical']},
        'intent': {'type': 'choice', 'instructions': 'Which intent?',
                   'criteria': {f'intent_{i}': f'Intent number {i}' for i in range(20)}}}
    for state in ('I was billed twice, please refund the duplicate.', {'ticket': 'The app crashes at login. ' * 200}):
        engine.answer({'model': MODEL, 'state': state, 'questions': questions})
    log.info('Runtime warmup completed in %.3fs', time.perf_counter() - started)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, required=True)
    parser.add_argument('--token-file', type=Path)
    args = parser.parse_args()
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
    token = read_token(args.token_file) if args.token_file is not None else None
    checkpoint = common.snapshot(CHECKPOINT, REVISION, ['*.json', '*.safetensors', '*.jinja'])
    engine = load(checkpoint)
    warm(engine)
    common.serve(engine, args.port, token, ACTIVE_REQUESTS)


if __name__ == '__main__':
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    main()
