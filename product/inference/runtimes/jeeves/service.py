"""posthog/jeeves native SystemOne serving: Jeeves's pointer head, without thinking, over a loopback SGLang engine.

Jeeves (PostHog/jeeves, Qwen3.5-9B with a merged LoRA and a learned pointer head) scores up to 255 options of a
question in one prefill. jeeves_sglang/model.py computes the head's scores inside SGLang and returns option i's score
as the logit of token id i; this adapter reads them as log probabilities, divides by Jeeves's fitted no-think
temperature (1.522, from the checkpoint's config) and softmaxes. The checkpoint is PostHog/jeeves-fp8's `vllm` branch:
FP8_DYNAMIC weights (llm-compressor, GPTQ-chosen) and the head in fp32, which SGLang loads as compressed-tensors FP8.

The prompt is Jeeves's own (jeeves_prompt.py); the request and response shapes are the gateway's
(product/packages/contracts/src/systemone.ts).
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
import jeeves_prompt as prompt

log = logging.getLogger('jeeves.service')

MODEL = 'posthog/jeeves'
CHECKPOINT = 'PostHog/jeeves-fp8'
# The `vllm` branch of PostHog/jeeves-fp8: FP8 weights of PostHog/jeeves 8622b7d1 for a JeevesForCausalLM config,
# Apache-2.0. verify-build.py refuses to package an unpinned runtime.
REVISION = '718f9c1aea0753b88fd260045a26e8343fa262d8'
# The PostHog/jeeves commit whose prompt format jeeves_prompt.py ports.
UPSTREAM_COMMIT = '954d063d'
MAX_TOKENS = 16384
# About ten seconds of an L4's prompt throughput; a request whose prompts sum to more is rejected before it runs.
REQUEST_MAX_TOKENS = 65536
ACTIVE_REQUESTS = 8
LONG_PROMPT_TOKENS = 2048
PREFILL_STEP_TOKENS = MAX_TOKENS + 1
SGLANG_FLAGS = [
    '--mem-fraction-static', '0.80', '--max-running-requests', '32',
    # The head reads a question's options and <decide> in one forward step: no chunked prefill and no radix cache,
    # whose hits would leave the options out of the step.
    '--chunked-prefill-size', '-1', '--disable-radix-cache', '--max-prefill-tokens', str(PREFILL_STEP_TOKENS),
]


class Engine:
    model = MODEL

    def __init__(self, prompts, sglang, sglang_alive, temperature):
        self.prompts, self.sglang, self.sglang_alive, self.temperature = prompts, sglang, sglang_alive, temperature
        self.healthy = True

    def answer(self, data):
        if not self.healthy or not self.sglang_alive():
            self.healthy = False
            raise RuntimeError('runtime requires restart')
        started = time.perf_counter()
        state, questions = data['state'], data['questions']
        try:
            state_ids = self.prompts.state_ids(state)
            rows = {key: self.prompts.question_ids(state_ids, question) for key, question in questions.items()}
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidRequest(f'invalid decision request: {exc}') from None
        for ids in rows.values():
            if len(ids) > MAX_TOKENS:
                raise InvalidRequest(f'input is {len(ids)} tokens; the limit is {MAX_TOKENS}')
        tokens = sum(map(len, rows.values()))
        if tokens > REQUEST_MAX_TOKENS:
            raise InvalidRequest(f'request exceeds {REQUEST_MAX_TOKENS} input tokens')
        # One outcome is certain and is answered without the model; its prompt still counts as input.
        asked = [key for key, question in questions.items() if not common.single_outcome(question)]
        answers = {key: common.answer(question, {prompt.keys(question)[0]: 1.0}, self.legend(question))
                   for key, question in questions.items() if key not in asked}
        try:
            scores = self._read([rows[key] for key in asked],
                                [list(range(len(prompt.keys(questions[key])))) for key in asked])
        except self.sglang.http_error as exc:
            # SGLang answers 400 for a prompt over the context length; anything else is a failed engine.
            if exc.response is not None and exc.response.status_code == 400:
                raise InvalidRequest(f'input exceeds {MAX_TOKENS} tokens') from None
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        except Exception:
            self.healthy = False
            raise RuntimeError('inference failed; runtime requires restart') from None
        for key, row in zip(asked, scores):
            if any(value is None for value in row):
                raise common.InvalidModelOutput('the pointer head did not read every option in one step')
            question = questions[key]
            distribution = common.softmax([value / self.temperature for value in row])
            answers[key] = common.answer(question, dict(zip(prompt.keys(question), distribution)),
                                         self.legend(question))
        answers = {key: answers[key] for key in questions}
        if any(not common.valid_answer(answers[key], question) for key, question in questions.items()):
            raise common.InvalidModelOutput('invalid decision model output')
        # As PostHog's server reports it: every question's whole prompt, nothing cached.
        return {'model': MODEL, 'answers': answers,
                'usage': {'input_tokens': tokens, 'cached_input_tokens': 0, 'output_tokens': 0},
                'latency_ms': round((time.perf_counter() - started) * 1000, 3)}

    def _read(self, rows, token_ids):
        # On L4, packing long unchunked prefills into a full step costs more than
        # submitting each separately. Other concurrent requests can still co-batch.
        lengths = [len(row) for row in rows]
        if len(rows) >= 4 and sum(lengths) > PREFILL_STEP_TOKENS and min(lengths) >= LONG_PROMPT_TOKENS:
            return [self.sglang.logprobs([row], [ids])[0] for row, ids in zip(rows, token_ids)]
        return self.sglang.logprobs(rows, token_ids)

    @staticmethod
    def legend(question):
        """A score question's levels as Jeeves renders them."""
        if question['type'] != 'score':
            return None
        return dict(zip(prompt.keys(question), prompt.options(question)))


def sglang_command(checkpoint, port):
    return common.sglang_command(checkpoint, port, MAX_TOKENS, SGLANG_FLAGS)


def sglang_environment(root):
    """SGLang imports JeevesForCausalLM from the bundle's jeeves_sglang package."""
    return {'SGLANG_EXTERNAL_MODEL_PACKAGE': 'jeeves_sglang', 'PYTHONPATH': str(root)}


def load(checkpoint):
    from transformers import AutoTokenizer

    config = json.loads((Path(checkpoint) / 'config.json').read_text())
    if config['architectures'] != ['JeevesForCausalLM']:
        raise RuntimeError('the checkpoint must name JeevesForCausalLM')
    process, url = common.start_sglang(sglang_command(checkpoint, common.free_port()),
                                       sglang_environment(Path(__file__).resolve().parent))
    prompts = prompt.Prompts(AutoTokenizer.from_pretrained(checkpoint))
    markers = config['jeeves']
    if (prompts.opt_end_id, prompts.decide_id, prompts.think_end_id) != (
            markers['opt_end_id'], markers['decide_id'], markers['think_end_id']):
        raise RuntimeError('the tokenizer and the checkpoint disagree on Jeeves marker ids')
    return Engine(prompts, common.client(url, ACTIVE_REQUESTS), lambda: process.poll() is None,
                  float(markers['temperature']))


def warm(engine):
    started = time.perf_counter()
    questions = {
        'refund': {'type': 'noul', 'instructions': 'Does the customer ask for money back?'},
        'team': {'type': 'choice', 'instructions': 'Which team handles this?',
                 'criteria': {'billing': 'Payments and refunds', 'tech': 'Bugs and login'}},
        'urgency': {'type': 'score', 'instructions': 'Rate urgency.', 'criteria': ['routine', 'urgent', 'critical']},
        'intent': {'type': 'choice', 'instructions': 'Which intent?',
                   'criteria': {f'intent_{i}': f'Intent number {i}' for i in range(77)}}}
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
    checkpoint = common.snapshot(CHECKPOINT, REVISION, ['*.json', '*.safetensors', '*.jinja', '*.txt'])
    engine = load(checkpoint)
    warm(engine)
    common.serve(engine, args.port, token, ACTIVE_REQUESTS)


if __name__ == '__main__':
    os.environ.setdefault('TOKENIZERS_PARALLELISM', 'false')
    main()
